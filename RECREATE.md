# Prompt to recreate Agent Fieldnotes

Copy the text below into your coding agent.

```text
Build my own Agent Fieldnotes dashboard from https://github.com/johnbean393/agent-fieldnotes. Clone the repository and read its README and FORMAT. Use the included site and local pipeline as the starting point. Run the synthetic demo first to verify the build.

Inventory the coding agents, harnesses, editors, terminal tools, and custom workflows I actually use. Do not assume particular products; discover what is installed or configured on this machine. For each source, inspect the available history, date coverage, human prompts, conversations, model responses, token counters, and tool outcomes. Use any bundled adapter that fits. For every source without one, write a read-only adapter that emits the documented normalized event JSONL. Adapters may be modules or standalone scripts in any language, must not modify the source stores, and must expose only fields the source actually records. Pass each export as an additional `--input` file; keep prompt IDs globally unique and let the build normalize repeated event IDs. Keep missing telemetry explicit.

Deduplicate copied history under differing IDs before building, and let the build merge repeated response IDs and streaming frames. Count human-authored inputs as prompts and keep work cycles, responses, and tool calls distinct. Credit verifiably linked delegated responses to the human prompt that launched them. Preserve coverage gaps when the links are ambiguous.

Build the aggregate dashboard locally first. Run local PII redaction and a credential check before sending only scrubbed text to my Jev/TypeSafe-compatible labeling access. Use my environment-provided TypeSafe credential, and keep the credential and the local label cache private. Label prompt purpose, intent, feedback, and steering. Reuse the local label cache keyed by payload, model, and rubric, so reruns do not resend labeled payloads. Put model development and fine-tuning in their own use-case bucket.

Keep the compact sidebar layout, Usage, Patterns, Insights, and Method views. Use my local timezone for the weekly activity grid. Keep the iteration-weighted work-per-prompt chart and the thread follow-through chart where the source supports them. Combine comparable agents by default and show app-specific series when definitions differ.

Show me the populated local preview and source coverage. Keep raw logs, keys, intermediate results, and generated exports out of Git. Publish only telemetry and derived labels. Keep all prompt text local. Publish my reviewed build to a static host I choose when I ask.
```
