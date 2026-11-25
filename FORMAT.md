# Normalized event format

Any coding agent, harness, or script can feed Agent Fieldnotes by emitting UTF-8 JSON Lines in this format. An adapter is optional: it is only the code that translates one local source store into these lines. Each line is one JSON object, and line order does not matter.

The build accepts any number of these files as `--input` and normalizes all rows together by `app`, `kind`, and `id`. A custom adapter therefore needs no registration or frontend change: write the format, pass the file as another `--input`, and keep stable IDs. Repeated copies of the same event key are normalized, but the same history exported twice under different IDs is not detectable; remove those copies before building.

| Field | Meaning |
|---|---|
| `app` | Lowercase source slug, such as `codex`, `my_harness`, or `editor_plugin`. Start with a letter; use only lowercase letters, digits, `_`, and `-`. Unknown slugs are title-cased for display, so a new adapter needs no frontend change. |
| `kind` | `prompt`, `response`, `turn`, or `tool` |
| `id` | Stable source event ID, unique within its `app` and `kind`. Prompt IDs must be globally unique across all adapters so `trigger` resolves. |
| `conversation` | Stable source conversation or thread ID, emitted as a string |
| `time` | Event time as ISO 8601 with an offset, or Unix epoch seconds or milliseconds |
| `text` | Human prompt text for a `prompt` event |
| `trigger` | Optional initiating prompt ID for a `response`, possibly from a different app |
| `input_tokens`, `output_tokens` | Optional integer response counters. Normalize input to include cache reads and writes. |
| `cache_read` | Optional nonnegative subset of input tokens |
| `end` | Optional timestamp of a completed `turn`, used to measure overlapping work |
| `failed` | Optional boolean source-reported tool failure signal |
| `measure` | Optional public-safe tool result label, such as `shell result` |

## What to emit

Emit human-authored inputs as prompts. Every prompt event needs nonempty `text`; other kinds do not use it. System notices, delegated-agent inputs, and tool results have separate roles; exclude them from prompt events instead of counting them as human text. When a harness stores its own envelopes around a real prompt, strip those envelopes and keep the remainder.

Use times with an explicit offset or Unix epoch; events without one are skipped. The build normalizes accepted times to UTC.

Emit each completed model response using its native ID. If streaming frames repeat a response ID, a single response is enough; repeated partials are merged. Do not synthesize responses or split one native response into several.

Use a verified causal link to set `trigger`. If the initiating prompt is ambiguous, leave `trigger` absent so the response stays uncredited rather than inflating a prompt's work.

For turns, use source timestamps and set `end` when the source records completion. For tools, set `failed` and `measure` only when the source reports them. Keep `measure` free of private paths, commands, arguments, and output.

Leave unsupported optional fields absent. Missing token counters, cache reads, tool outcomes, or linked responses remain unavailable; do not estimate them or substitute zero. Every view shows only the telemetry the supplied events support.

Use identifiers, timestamps, and raw content in the private input. The static build contains telemetry and derived labels. Conversation IDs are keyed and prompt text stays private.

Avoid the reserved slugs `all`, `constructor`, and `prototype`; `all` is a combined-series filter in the dashboard. Labels are produced by the pipeline from redacted text during labeling, so do not include label fields in a source export.
