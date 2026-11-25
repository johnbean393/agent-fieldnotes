# Additional local sources

For OpenCode, Mimocode, or Oh My Pi, run `python3 pipeline/collect_extra.py --help`. Pass each private export to the build with an additional `--input`.

## OpenRouter labeling

For OpenRouter Decisions labeling, use the same model configuration throughout. Keep the pending payloads, auth export, and cache under private local state.

```sh
PII_MODEL=fastino/gliner2-privacy-filter-PII-multi
.venv/bin/python pipeline/prepare_labels.py --input .fieldnotes/events.jsonl \
  --out .fieldnotes/pending.json --pii-model "$PII_MODEL"
.venv/bin/python pipeline/label_direct.py --pending .fieldnotes/pending.json \
  --out .fieldnotes/openrouter-labels.json --key-file "$OPENROUTER_AUTH_EXPORT" \
  --pii-model "$PII_MODEL"
JEV_LABEL_CACHE=.fieldnotes/openrouter-labels.json \
  .venv/bin/python pipeline/fieldnotes.py build --input .fieldnotes/events.jsonl \
  --pii-model "$PII_MODEL" --jev
```
