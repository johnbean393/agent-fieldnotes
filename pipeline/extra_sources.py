"""Read-only adapters for OpenCode, Mimocode and Oh My Pi stats databases.

The generators return normalized event dictionaries in the format described by
FORMAT.md. They never write to the source databases and never print prompt text.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import time

from prompt_origin import human_prompt

KINDS = {'prompt', 'response', 'turn', 'tool'}

_CONTEXT_TAGS = ('system-reminder', 'environment_context', 'external_codex_apps_open_page')
_HARNESS_TAGS = (
    'teammate-message', 'task-notification', 'agent-message', 'inter-agent-message',
    'system_notification', 'system-notification', 'automation', 'harness-notification',
    'cross-session-message', 'job-notification', 'side-sessions-event', 'ci-monitor-event',
)


def _now_ms():
    return int(time.time() * 1000)


def _establishment(path, default):
    path = Path(path).expanduser()
    return path / default if path.is_dir() else path


def _connect(path, default):
    return sqlite3.connect(_establishment(path, default).as_uri() + '?mode=ro', uri=True)


def _iso(milliseconds):
    if not isinstance(milliseconds, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _leading(text, tag):
    return re.match(rf'<{tag}(?:\s[^>]*|)>(.*?)</{tag}>\s*', text, re.S)


def human_text(app, body):
    """Strip harness envelopes and return the human-authored remainder."""
    if not isinstance(body, str):
        return ''
    value = body.strip()
    for tag in _CONTEXT_TAGS:
        value = re.sub(rf'<{tag}\b[^>]*>.*?</{tag}>', '', value, flags=re.S)
    value = re.sub(r'^\s*<user_query>\s*(.*?)\s*</user_query>\s*$', r'\1', value, flags=re.S)
    while value:
        wrapper = next((match for tag in _CONTEXT_TAGS if (match := _leading(value, tag))), None)
        if not wrapper:
            break
        value = value[wrapper.end():].strip()
    if not value:
        return ''
    if any(_leading(value, tag) for tag in _HARNESS_TAGS):
        return ''
    if re.match(r'^\s*\[(?:notification|automation|system|harness)(?:\]|:)', value, re.I):
        return ''
    return human_prompt(app, value)[0].strip()


def _tokens(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _response_counters(tokens):
    if not isinstance(tokens, dict):
        return {}
    input_tokens = _token_count(tokens.get('input'))
    cache = tokens.get('cache') if isinstance(tokens.get('cache'), dict) else {}
    cache_read = _token_count(cache.get('read'))
    cache_write = _token_count(cache.get('write'))
    output_tokens = _token_count(tokens.get('output'))
    result = {}
    if input_tokens is not None:
        result['input_tokens'] = input_tokens + (cache_read or 0) + (cache_write or 0)
    if cache_read is not None:
        result['cache_read'] = cache_read
    if output_tokens is not None:
        result['output_tokens'] = output_tokens
    return result


def _event(app, kind, uid, conversation, stamp, **data):
    if not uid or not conversation or not stamp:
        return None
    row = dict(app=app, kind=kind, id=f'{app}:{uid}', conversation=str(conversation), time=stamp)
    row.update({key: value for key, value in data.items() if value is not None})
    return row


def _opencode_like(app, path, default):
    """Shared projector for the OpenCode and Mimocode SQLite layout."""
    cutoff = _now_ms()
    with _connect(path, default) as db:
        db.execute('pragma query_only=1')
        children = {sid for sid, parent in db.execute('select id,parent_id from session')
                    if parent}
        messages = {}
        for mid, sid, created, role, parent, begun, completed, tokens in db.execute(
                "select id,session_id,time_created,json_extract(data,'$.role'),"
                "json_extract(data,'$.parentID'),json_extract(data,'$.time.created'),"
                "json_extract(data,'$.time.completed'),json_extract(data,'$.tokens') "
                "from message where time_created<=?", (cutoff,)):
            messages[mid] = {
                'session': sid, 'role': role, 'parent': parent,
                'created': begun if isinstance(begun, int) else created,
                'completed': completed if isinstance(completed, int) else None,
                'tokens': _tokens(tokens),
            }

        prompt_ids = {}
        prompt_rows = []
        tool_rows = []
        user_text = defaultdict(list)
        seen_parts = set()
        # One scan keeps the multi-gigabyte stores from being opened twice.
        for mid, pid, created, kind, body, tool, status, start, synthetic in db.execute(
                "select message_id,id,time_created,json_extract(data,'$.type'),"
                "json_extract(data,'$.text'),json_extract(data,'$.tool'),"
                "json_extract(data,'$.state.status'),"
                "json_extract(data,'$.state.time.start'),"
                "json_extract(data,'$.synthetic') from part where time_created<=?",
                (cutoff,)):
            if pid in seen_parts or mid not in messages:
                continue
            seen_parts.add(pid)
            message = messages[mid]
            if kind == 'text' and message['role'] == 'user' and not synthetic and isinstance(body, str):
                if body.strip():
                    user_text[mid].append(body)
            elif kind == 'tool':
                stamp = _iso(start if isinstance(start, int) else created)
                state = status.lower() if isinstance(status, str) else ''
                failed = None
                if any(word in state for word in ('error', 'fail')):
                    failed = True
                elif state in {'completed', 'complete', 'done', 'success'}:
                    failed = False
                if failed is None:
                    continue
                row = _event(app, 'tool', pid, message['session'], stamp,
                             failed=failed, measure=tool or 'tool')
                if row:
                    tool_rows.append(row)
            if len(tool_rows) >= 5000:
                yield from tool_rows
                tool_rows.clear()

        for mid, parts in user_text.items():
            message = messages[mid]
            # A child session's first user turn is delegated agent input, not human input.
            if message['session'] in children:
                continue
            cleaned = human_text(app, '\n'.join(parts))
            if not cleaned:
                continue
            row = _event(app, 'prompt', mid, message['session'],
                         _iso(message['created']), text=cleaned)
            if row:
                prompt_rows.append(row)
                prompt_ids[mid] = row['id']

        def trigger(mid):
            seen = set()
            parent = messages[mid]['parent']
            while parent and parent not in seen:
                seen.add(parent)
                ancestor = messages.get(parent)
                if not ancestor:
                    return None
                if ancestor['role'] == 'user' and parent in prompt_ids:
                    return parent
                parent = ancestor['parent']
            return None

        response_rows = []
        turn_rows = []
        cycles = {}
        for mid, message in messages.items():
            if message['role'] != 'assistant':
                continue
            start = _iso(message['created'])
            end = _iso(message['completed'])
            if not start or not end:
                continue
            linked = trigger(mid)
            response = _event(app, 'response', mid, message['session'], end,
                              trigger=prompt_ids.get(linked), **_response_counters(message['tokens']))
            if response:
                response_rows.append(response)
            if linked and isinstance(message['completed'], int):
                cycle = cycles.get(linked)
                cycles[linked] = max(cycle, message['completed']) if cycle else message['completed']

        for mid, end_ms in cycles.items():
            turn = _event(app, 'turn', f'{mid}:cycle', messages[mid]['session'],
                          _iso(messages[mid]['created']), end=_iso(end_ms))
            if turn:
                turn_rows.append(turn)

    yield from prompt_rows
    yield from response_rows
    yield from turn_rows
    yield from tool_rows


def opencode(path):
    """Human prompts, completed responses, turns and tools from OpenCode."""
    yield from _opencode_like('opencode', path, 'opencode.db')


def mimocode(path):
    """Human prompts, completed responses, turns and tools from Mimocode."""
    yield from _opencode_like('mimocode', path, 'mimocode.db')


def omp(path):
    """Human prompts and linked model/tool activity from the OMP stats database."""
    cutoff = _now_ms()
    with _connect(path, 'stats.db') as db:
        db.execute('pragma query_only=1')
        boundaries = defaultdict(list)
        prompt_rows = []
        prompt_ids = {}
        seen_prompts = set()
        for entry, session, stamp, prose in db.execute(
                "select entry_id,session_file,timestamp,prose from user_messages "
                "where timestamp<=? order by session_file,timestamp,entry_id", (cutoff,)):
            key = (session, entry)
            if key in seen_prompts:
                continue
            seen_prompts.add(key)
            iso = _iso(stamp)
            if not iso:
                continue
            cleaned = human_text('omp', prose)
            if not cleaned:
                # Automation still ends the preceding human prompt's attribution window.
                boundaries[session].append((stamp, None))
                continue
            row = _event('omp', 'prompt', f'{session}:{entry}', session, iso, text=cleaned)
            if row:
                prompt_rows.append(row)
                prompt_ids[(session, entry)] = row['id']
                boundaries[session].append((stamp, (session, entry)))

        response_rows = []
        turn_rows = []
        cycles = {}
        seen_responses = set()
        for entry, session, stamp, duration, input_tokens, output_tokens, cache_read, cache_write in db.execute(
                "select entry_id,session_file,timestamp,duration,input_tokens,output_tokens,"
                "cache_read_tokens,cache_write_tokens from messages where timestamp<=? "
                "order by session_file,timestamp,entry_id", (cutoff,)):
            key = (session, entry)
            if key in seen_responses:
                continue
            seen_responses.add(key)
            start = _iso(stamp)
            if not start:
                continue
            end = None
            end_ms = None
            if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
                end_ms = stamp + duration * 1000
                end = _iso(end_ms)
            bounds = boundaries.get(session, [])
            index = bisect_right(bounds, stamp, key=lambda item: item[0])
            lead = bounds[index - 1] if index else None
            lead_key = lead[1] if lead else None
            raw = _token_count(input_tokens)
            read = _token_count(cache_read)
            written = _token_count(cache_write)
            output = _token_count(output_tokens)
            counters = {}
            if raw is not None:
                counters['input_tokens'] = raw + (read or 0) + (written or 0)
            if read is not None:
                counters['cache_read'] = read
            if output is not None:
                counters['output_tokens'] = output
            row = _event('omp', 'response', f'{session}:{entry}', session, end or start,
                         trigger=prompt_ids.get(lead_key), **counters)
            if row:
                response_rows.append(row)
            if end_ms is not None and lead_key:
                cycle = cycles.get(lead_key)
                cycles[lead_key] = [lead[0], max(cycle[1], end_ms)] if cycle else [lead[0], end_ms]

        for (session, entry), (start_ms, end_ms) in cycles.items():
            turn = _event('omp', 'turn', f'{session}:{entry}:cycle', session,
                          _iso(start_ms), end=_iso(end_ms))
            if turn:
                turn_rows.append(turn)

        tool_rows = []
        seen_tools = set()
        for tool_id, entry, session, name, stamp, is_error in db.execute(
                "select tool_call_id,entry_id,session_file,tool_name,timestamp,is_error "
                "from tool_calls where timestamp<=? order by session_file,timestamp,tool_call_id",
                (cutoff,)):
            key = (session, tool_id)
            if key in seen_tools:
                continue
            seen_tools.add(key)
            row = _event('omp', 'tool', f'{session}:{tool_id}', session, _iso(stamp),
                         failed=bool(is_error), measure=name or 'tool')
            if row:
                tool_rows.append(row)

    yield from prompt_rows
    yield from response_rows
    yield from turn_rows
    yield from tool_rows
