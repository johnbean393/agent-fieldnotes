#!/usr/bin/env python3
"""Collect private events from OpenCode, Mimocode and Oh My Pi stats stores."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extra_sources import KINDS, mimocode, omp, opencode  # noqa: E402

APP = re.compile(r'[a-z][a-z0-9_-]*')


def validate(row):
    """Reject rows that do not satisfy the published event format."""
    if not isinstance(row, dict):
        raise ValueError('event is not an object')
    app, kind = row.get('app'), row.get('kind')
    if not isinstance(app, str) or not APP.fullmatch(app) or app in {'all', 'constructor', 'prototype'}:
        raise ValueError('invalid app slug')
    if kind not in KINDS:
        raise ValueError('invalid event kind')
    for key in ('id', 'conversation'):
        if not isinstance(row.get(key), str) or not row[key]:
            raise ValueError(f'event lacks {key}')
    if not isinstance(row.get('time'), str) or not row['time']:
        raise ValueError('event lacks time')
    try:
        stamp = datetime.fromisoformat(row['time'].replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('invalid event time') from error
    if stamp.tzinfo is None:
        raise ValueError('event time lacks an offset')
    if kind == 'prompt' and (not isinstance(row.get('text'), str) or not row['text'].strip()):
        raise ValueError('prompt lacks text')
    for key in ('input_tokens', 'output_tokens', 'cache_read'):
        if key in row and (type(row[key]) is not int or row[key] < 0):
            raise ValueError(f'invalid {key}')
    if 'failed' in row and type(row['failed']) is not bool:
        raise ValueError('invalid failed flag')
    if 'measure' in row and (not isinstance(row['measure'], str) or not row['measure']):
        raise ValueError('invalid measure')
    if 'trigger' in row and (not isinstance(row['trigger'], str) or not row['trigger']):
        raise ValueError('invalid trigger')
    if 'end' in row:
        try:
            end = datetime.fromisoformat(row['end'].replace('Z', '+00:00'))
        except (TypeError, ValueError) as error:
            raise ValueError('invalid end time') from error
        if end.tzinfo is None:
            raise ValueError('end time lacks an offset')


def collect(options):
    sources = options.opencode, options.mimocode, options.omp
    if not any(sources):
        raise ValueError('Specify at least one source path')
    target = options.out.resolve()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        raise ValueError('Select a fresh path for the private export')

    counts = Counter()
    dates = defaultdict(set)
    with open(target, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        for adapter, source in zip((opencode, mimocode, omp), sources):
            if not source:
                continue
            for row in adapter(source.resolve()):
                if not row:
                    continue
                validate(row)
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                counts[row['app'], row['kind']] += 1
                dates[row['app']].add(row['time'][:10])

    print(f'Collected {sum(counts.values())} private events.')
    for app in sorted(dates):
        parts = [f'{kind}={counts[app,kind]}' for kind in ('prompt', 'response', 'turn', 'tool')
                 if counts[app,kind]]
        days = sorted(dates[app])
        print(f'{app}: {", ".join(parts)}; dates {days[0]} to {days[-1]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opencode', type=Path, help='OpenCode database or its directory')
    parser.add_argument('--mimocode', type=Path, help='Mimocode database or its directory')
    parser.add_argument('--omp', type=Path, help='OMP stats database or its directory')
    parser.add_argument('--out', type=Path, required=True, help='new private JSON Lines path')
    collect(parser.parse_args())


if __name__ == '__main__':
    main()
