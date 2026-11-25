# Agent Fieldnotes

A static dashboard for coding-agent activity across the harnesses you use: conversation patterns, work volume, and token usage. This source-only release contains the dashboard frontend and a portable local pipeline.

[Copy the recreation prompt](RECREATE.md)

## Run the synthetic demo

Requires Python 3.10 or newer. The demo has no Python package dependencies.

```sh
python3 pipeline/fieldnotes.py build --demo
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

Open `http://127.0.0.1:8765/`. The demo generates its fixture events in memory and writes a local static build.

## Import from your agents and harnesses

The pipeline separates private collection from the public build. A source adapter reads one local store read-only and emits the [normalized event format](FORMAT.md) as UTF-8 JSON Lines. The build consumes one or more JSONL files and does not need to know which product produced them. Adapters are optional: any coding agent, harness, or script that can write the format can feed the dashboard.

Inventory each agent or harness you actually use, including its local history, date coverage, human prompts, conversations, model responses, and token counters. Write or choose an adapter for every source with readable history, and leave unsupported sources out of the input. Storage formats change between versions, so verify a sample export before trusting the whole history.

Bundled adapters are examples for common local stores. They are read-only and write normalized events; run `python3 pipeline/fieldnotes.py collect --help` to see the inputs available in this release.

```sh
python3 pipeline/fieldnotes.py collect \
  --codex "$HOME/.codex" \
  --claude "$HOME/.claude/projects" \
  --cursor "$CURSOR_STATE_DB" \
  --out .fieldnotes/events.jsonl
```

Point each flag at the store on your machine; the bundled Cursor adapter reads its local state database. Install `zstd` if a bundled adapter reads compressed rollouts. `FORMAT.md` is the extension boundary. A source without a bundled adapter needs only a read-only adapter that emits `FORMAT.md` JSONL; pass that output as additional `--input` files. The build normalizes all inputs by stable IDs: it keeps one row per `app`, `kind`, and `id`, merges repeated streaming frames for a response ID, and rejects prompt IDs that still collide after normalization. Namespace prompt IDs by source. The build cannot recognize the same history exported twice under different IDs, so deduplicate copied history yourself before building and record which sources and date ranges each export covers.

Collection refuses to overwrite an existing output path. The build writes to a fresh output directory or replaces one it generated, and keeps private state in `.fieldnotes` by default; pass `--private` to use another path.

Build from the normalized exports:

```sh
python3 pipeline/fieldnotes.py build \
  --input .fieldnotes/events.jsonl \
  --timezone America/New_York
```

Pass additional `--input` files when you keep sources separate. Every view shows only telemetry the supplied events support. A prompt-only adapter supplies prompt activity; response, iteration, token, tool, and elapsed-time views remain unavailable. Token counters, cache reads, tool outcomes, and linked responses remain unavailable unless the source records them. Unsupported optional fields stay absent rather than estimated. Iteration counts describe distinct recorded model responses. Elapsed time uses observed timestamps and can include waiting.

Coverage is a property of the inputs, not a number the build can invent. Keep a private note for each harness covering its readable date range, whether human prompts and responses are recorded, token and cache counters, tool outcomes, and verified delegated links. The Method view reports the snapshot and retained totals from the build itself, so it reflects only the supplied events. Review that inventory before interpreting a trend, and leave a source out rather than estimating its missing telemetry.

### Credit delegated work (optional)

When one harness launches another, a response is credited to the human prompt that caused it only through a verified link. Generic adapters can set `trigger` on a response directly. The bundled review linker handles one specific launch-recording layout:

```sh
python3 pipeline/link_reviews.py --input .fieldnotes/events.jsonl \
  --codex "$HOME/.codex" --claude "$HOME/.claude/projects" \
  --out .fieldnotes/reviews.jsonl
```

By default the linker checks session IDs in launch results. It can also inspect literal local stdout paths referenced by launch commands with `--read-launch-logs`. Add `--match-launch-time` to consider uniquely attributable working-directory and launch-time matches. Review additional matches before using them for a comparison, then pass the private review file as another `--input` to the build. Keep ambiguous links uncredited so coverage gaps remain visible.

## Redaction and Jev

Prompt labeling requires local redaction: pass `--pii-model` to the build. The redaction stage runs a credential gate and withholds prompts that still contain credential-like material; the Jev labeler also refuses such payloads.

Install `gliner2` in a virtual environment to enable the local PII pass. Download the model in an environment where your raw transcripts stay local.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install gliner2
```

Set `TYPESAFE_API_KEY` in your local environment and let the build redact and label in one pass:

```sh
.venv/bin/python pipeline/fieldnotes.py build \
  --input .fieldnotes/events.jsonl \
  --timezone America/New_York \
  --pii-model fastino/gliner2-privacy-filter-PII-multi \
  --jev
```

The credential is read from the environment only. Keep it, the private state directory, and any generated build out of this repository.

Optionally set `JEV_MODEL`. Jev receives scrubbed prompt text and structured questions. Labeling results are cached locally by payload, model, and rubric in the private state directory, so reruns do not resend matching payloads. Keep the same labeler model setting across reruns so cached answers remain reusable, and review the labels and your source inventory before interpreting a trend.

## Publish a reviewed build

The generated `dist/` is the static site. Host it at the root of a domain on your own static host, or use a hosting project you control. The source release contains no hosting identity. Before publishing, verify that the generated files contain only telemetry and derived labels.

The Method view reports the snapshot and retained prompt totals from the build itself. It cannot show telemetry or sources that were never supplied, so keep your source-coverage inventory with the private state rather than inventing a public summary. Keep prompt text local.

The frontend shows views supported by the supplied data. Missing telemetry remains unavailable. Iteration counts describe distinct recorded model responses. Elapsed time uses observed timestamps and can include waiting.
