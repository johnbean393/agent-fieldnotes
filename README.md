# Agent Fieldnotes

A static dashboard for coding-agent activity and conversation patterns. This source-only release includes the dashboard frontend and a portable local pipeline.

[Copy the recreation prompt](RECREATE.md) · [Additional sources and OpenRouter labeling](EXTRA_SOURCES.md)

## Run the synthetic demo

Requires Python 3.10 or newer. The demo has no Python package dependencies.

```sh
python3 pipeline/fieldnotes.py build --demo
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

Open `http://127.0.0.1:8765/`. The demo generates its fixture events in memory and writes a local static build.

## Import your own history

Run `collect --help` to see the available inputs. Agents use different storage formats, and formats can change between versions. The bundled read-only adapters accept a Codex home directory, a Claude projects directory, and a Cursor database. Give the command only the sources that exist on your machine. Install `zstd` for compressed Codex rollouts.

```sh
python3 pipeline/fieldnotes.py collect \
  --codex "$HOME/.codex" --claude "$HOME/.claude/projects" \
  --out .fieldnotes/events.jsonl

python3 pipeline/fieldnotes.py build --input .fieldnotes/events.jsonl --timezone America/New_York
```

The default build includes aggregate activity. Use the generated site's Usage and Method views to check what the sources support. Cursor's adapter currently reports prompt activity only. Codex and Claude adapters report observed response IDs when available. Claude's native importer uses root conversations. Add new agents through the [event format](FORMAT.md) and supply multiple `--input` files to combine them. Each build writes its own agent-by-month coverage table into the Method view.

To add Codex reviews launched by Claude, run the optional linkage stage and pass its private result as a second input.

```sh
python3 pipeline/link_reviews.py --input .fieldnotes/events.jsonl \
  --codex "$HOME/.codex" --claude "$HOME/.claude/projects" \
  --out .fieldnotes/reviews.jsonl
```

By default the linker checks session IDs in launch results. It can also inspect literal local stdout paths referenced by launch commands with `--read-launch-logs`. Add `--match-launch-time` to consider uniquely attributable working-directory and launch-time matches. Review the additional matches before using them for a comparison. Codex's parent turn metadata links the CLI job to its reviewer.

## Redaction and Jev

Install `gliner2` in a virtual environment to enable the local PII pass. The previous dashboard used the GLiNER2 multilingual privacy filter. Download the model in an environment where your raw transcripts stay local.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install gliner2
.venv/bin/python pipeline/fieldnotes.py build \
  --input .fieldnotes/events.jsonl --timezone America/New_York \
  --pii-model fastino/gliner2-privacy-filter-PII-multi --jev
```

Set `TYPESAFE_API_KEY` in your local environment before enabling `--jev`. Optionally set `JEV_MODEL`. Jev receives scrubbed prompt text and structured questions. Labeling results are cached locally by payload, model and rubric. Review the labels and source coverage before interpreting a trend.

## Publish a reviewed build

The generated `dist/` is the static site. Host it at the root of a domain or use ChatGPT Sites with your own hosting project. The source release contains no hosting identity. Publish only telemetry and derived labels. Keep prompt text, raw inputs, and private state outside the site and out of Git.

The frontend shows views supported by the supplied data. Missing telemetry remains unavailable. Iteration counts describe distinct recorded model responses. Elapsed time uses observed timestamps and can include waiting.
