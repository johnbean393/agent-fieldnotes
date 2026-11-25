# Prompt to recreate Agent Fieldnotes

Copy the text below into your coding agent.

```text
Build my own Agent Fieldnotes dashboard from https://github.com/johnbean393/agent-fieldnotes. Clone the repository and read its README and FORMAT. Use the included site and local pipeline as the starting point. Run the synthetic demo first to verify the build.

Inspect the coding agents I actually use and inventory the available history, date coverage, human prompts, conversations, model responses and token counters. Use the bundled adapters where they fit. Add a read-only adapter that emits the documented JSONL format for other agents. Keep missing telemetry explicit.

Deduplicate repeated response IDs and copied history. Count human-authored inputs as prompts and keep work cycles, responses and tool calls distinct. Credit verifiably linked delegated responses to the human prompt that launched them. Preserve coverage gaps when the links are ambiguous.

Build the aggregate dashboard locally first. Run local PII redaction and a credential check before using my Jev access to label prompt purpose, intent, feedback, and steering. Use my environment-provided TypeSafe credential. Deduplicate and cache labels. Put model development and fine-tuning in their own use-case bucket.

Keep the compact sidebar layout, Usage, Patterns, Insights, and Method views. Use my local timezone for the weekly activity grid. Keep the iteration-weighted work-per-prompt chart and the thread follow-through chart where the source supports them. Combine comparable agents by default and show app-specific series when definitions differ.

Show me the populated local preview and source coverage. Keep raw logs, keys, intermediate results and generated exports out of Git. Publish only telemetry and derived labels. Keep all prompt text local. Publish my reviewed build to my own ChatGPT Site when I ask.
```
