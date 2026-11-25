"""Label redacted payloads with TypeSafe Jev through OpenRouter Decisions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import jev
from privacy import load_model, redact

ENDPOINT = 'https://openrouter.ai/api/alpha/decisions'


def credential(path):
    data = json.loads(Path(path).read_text())
    for entry in data.get('credentials', []):
        if entry.get('provider') == 'openrouter':
            value = entry.get('credential', {})
            key = value.get('key') or value.get('apiKey') or value.get('token')
            if key:
                return key
    raise RuntimeError('No OpenRouter credential in the private auth export')


def validated_payload(kind, cache_key, item, model, is_scrubbed):
    questions = {'prompt': jev.PROMPT, 'thread': jev.THREAD}[kind]
    messages = item['state']['human_messages']
    if not isinstance(messages, list) or not 1 <= len(messages) <= 20 or any(
        not isinstance(message, str) or len(message) > 3500 for message in messages
    ):
        raise ValueError('Invalid pending human messages')
    jev.check_credentials(messages)
    if any(not is_scrubbed(message) for message in messages):
        raise ValueError('Pending payload failed local PII recheck')
    if jev.Labeler.cache_key(messages, questions, model) != cache_key:
        raise ValueError('Pending payload does not match its cache key')
    return messages, questions


def label(messages, questions, key, model):
    jev.check_credentials(messages)
    body = jev.Labeler.body(messages, questions, model)
    request = Request(ENDPOINT, data=body, headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
            return jev.read_choices(result, questions)
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise RuntimeError(f'Jev HTTP {error.code}') from None
        except (URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError('Jev request failed') from None
        time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pending', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pii-model', required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--limit', type=int)
    options = parser.parse_args()
    pending = json.loads(options.pending.read_text())
    items = [(kind, key, value) for kind, group in pending.items() for key, value in group.items()]
    if options.limit:
        items = items[:options.limit]
    model = jev.model_name()
    labels = json.loads(options.out.read_text()) if options.out.exists() else {}
    detector = load_model(options.pii_model)

    @lru_cache(maxsize=4096)
    def is_scrubbed(message):
        return redact(message, detector) == message

    todo = [(cache_key, validated_payload(kind, cache_key, value, model, is_scrubbed))
            for kind, cache_key, value in items if cache_key not in labels]
    key = credential(options.key_file)
    failed = {}
    started = time.time()
    with ThreadPoolExecutor(max_workers=options.workers) as pool:
        futures = {pool.submit(label, messages, questions, key, model): cache_key
                   for cache_key, (messages, questions) in todo}
        for done, future in enumerate(as_completed(futures), 1):
            cache_key = futures[future]
            try:
                labels[cache_key] = future.result()
            except Exception as error:
                failed[cache_key] = str(error)[:120]
            if done % 1000 == 0:
                print(f'labeled {done}/{len(todo)}', flush=True)
    options.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = options.out.with_suffix('.tmp')
    with open(tmp, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(labels, stream, separators=(',', ':'))
    os.replace(tmp, options.out)
    print(f'Labeled {len(todo) - len(failed)} payloads in {time.time() - started:.0f}s; '
          f'failed {len(failed)}; total cached {len(labels)}.')
    if failed:
        print('first failures:', list(failed.items())[:3])


if __name__ == '__main__':
    main()
