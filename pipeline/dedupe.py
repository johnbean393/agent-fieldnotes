"""Stream private event exports, drop duplicates, and report coverage."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path

from sources import cleaned_input, timestamp


def signature(row, stamp):
    app, kind, sid = row['app'], row['kind'], row['conversation']
    # Full timestamps and native IDs keep parallel events distinct; only exact replays dedupe.
    moment = stamp.isoformat()
    if kind == 'prompt':
        digest = hashlib.sha256(row['text'].strip().encode()).hexdigest()
        return app, kind, sid, moment, row['id'], digest
    if kind == 'response':
        return (app, kind, sid, moment, row['id'], row.get('input_tokens'),
                row.get('cache_read'), row.get('output_tokens'), row.get('trigger'))
    if kind == 'turn':
        return app, kind, sid, moment, row['id'], row.get('end')
    return app, kind, sid, moment, row['id'], row.get('measure'), row.get('failed')


def run(paths, out, coverage_path):
    dropped = Counter()
    seen = set()
    # Streaming frames share a response ID but carry cumulative token and trigger updates.
    # Keep distinct frames and turn updates for normalize() to merge.
    responses = {}
    # A terminal tool snapshot may supersede an earlier provisional row with the same ID.
    terminal_tools = set()
    coverage = defaultdict(lambda: defaultdict(lambda: Counter(prompts=0, responses=0, turns=0,
                                                                tools=0, threads=set(), with_tokens=0)))
    kept = 0
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(out, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        for path in paths:
            with path.open() as source:
                for line in source:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        dropped['invalid_json'] += 1
                        continue
                    kind = row.get('kind')
                    if kind not in {'prompt', 'response', 'turn', 'tool'}:
                        dropped['invalid_kind'] += 1
                        continue
                    stamp = timestamp(row.get('time'))
                    if not stamp or not row.get('app') or not row.get('conversation') or not row.get('id'):
                        dropped['invalid_event'] += 1
                        continue
                    if kind == 'prompt':
                        text = cleaned_input(row['app'], row.get('text', ''))
                        if not text:
                            dropped['automation'] += 1
                            continue
                        row['text'] = text
                    primary = (row['app'], kind, row['id'])
                    secondary = signature(row, stamp)
                    if secondary in seen:
                        dropped['duplicate'] += 1
                        continue
                    terminal_tool = kind == 'tool' and type(row.get('failed')) is bool
                    if primary in seen and kind not in {'response', 'turn'}:
                        if not terminal_tool or primary in terminal_tools:
                            dropped['duplicate'] += 1
                            continue
                    if terminal_tool:
                        terminal_tools.add(primary)
                    if kind == 'response':
                        available = {key for key in ('input_tokens', 'output_tokens')
                                     if isinstance(row.get(key), int)}
                        state = responses.get(primary)
                        if state is None:
                            responses[primary] = [stamp, available, row['conversation']]
                        else:
                            state[0] = max(state[0], stamp)
                            state[1].update(available)
                    elif primary not in seen:
                        seen.add(primary)
                        cell = coverage[row['app']][stamp.strftime('%Y-%m')]
                        cell['prompts' if kind == 'prompt' else kind + 's'] += 1
                        cell['threads'].add(row['conversation'])
                    seen.add(secondary)
                    stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                    kept += 1
    for (app, _, _), (stamp, available, conversation) in responses.items():
        cell = coverage[app][stamp.strftime('%Y-%m')]
        cell['responses'] += 1
        cell['threads'].add(conversation)
        if len(available) == 2:
            cell['with_tokens'] += 1
    coverage_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    summary = {app: {month: dict(prompts=cell['prompts'], responses=cell['responses'], turns=cell['turns'],
                                 tools=cell['tools'], threads=len(cell['threads']), with_tokens=cell['with_tokens'])
                     for month, cell in sorted(months.items())} for app, months in sorted(coverage.items())}
    coverage_path.write_text(json.dumps({'dropped': dict(dropped), 'coverage': summary}, indent=2) + '\n')
    print(f'Kept {kept} events; dropped {dict(dropped)}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--coverage', type=Path, required=True)
    options = parser.parse_args()
    run(options.input, options.out, options.coverage)


if __name__ == '__main__':
    main()
