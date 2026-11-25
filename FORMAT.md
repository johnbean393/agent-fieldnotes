# Adapter format

Supply private UTF-8 JSON Lines in chronological or arbitrary order. Each line is an event object. Use explicit source timestamps with a timezone or a Unix timestamp.

| Field | Meaning |
|---|---|
| `app` | Lowercase agent slug, such as `codex` or `my_agent` |
| `kind` | `prompt`, `response`, `turn`, or `tool` |
| `id` | Stable source event ID. Namespace prompt IDs by app so `trigger` resolves globally. |
| `conversation` | Stable source conversation ID |
| `time` | Event time as ISO 8601 with offset or Unix epoch seconds or milliseconds |
| `text` | Human prompt text for a `prompt` event |
| `trigger` | Optional initiating prompt ID for a `response`, possibly from a different app |
| `input_tokens`, `output_tokens` | Optional integer response counters. Normalize input to include cache reads and writes. |
| `cache_read` | Optional nonnegative subset of input tokens |
| `end` | Optional timestamp of a completed `turn`, used to measure overlapping work |
| `failed` | Optional boolean source-reported tool failure, emitted only for a recorded terminal result |
| `measure` | Optional public-safe tool result label, such as `shell result` |

Emit human-authored inputs as prompts. System notices, delegated agent inputs and tool results have separate roles. Emit each completed model response using its native ID. Use a verified causal link to set `trigger`. Leave unsupported optional fields absent. Keep IDs, timestamps, and raw content in the private input. The static build contains telemetry and derived labels. Conversation IDs are keyed and prompt text stays private.
