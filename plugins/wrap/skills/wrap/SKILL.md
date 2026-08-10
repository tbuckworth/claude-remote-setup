---
name: wrap
description: Run the user's prompt in a subagent and return only the distilled, high-altitude answer, flagging anything that looks wrong or overclaimed. Use when asked to "wrap this", "use the wrap on it", "wrap that prompt", "give me the wrapped version", "keep it high level and check it", or /wrap — and for any request to delegate work and get back the core insight instead of a long report.
---

Read `../../commands/wrap.md` completely and follow it as the canonical workflow.

Treat everything the user said after the trigger as `{{argument}}`, ignore the Claude-only
frontmatter, and ask conversationally where the document says to ask.

The output contract is `../../references/rubric.md`. Read it before writing the answer, and
follow it exactly — it is the point of the whole workflow, not a style suggestion.

Codex specifics:

- `CLAUDE_PLUGIN_ROOT` is supplied for plugin compatibility; if it is unset, resolve paths
  from the plugin directory containing this skill (`../../references/rubric.md`,
  `../../agents/`).
- **Subagents.** Codex subagent support is conditional. If you can start subagents, follow
  the workflow as written, using `../../agents/wrap-worker.md`, `../../agents/wrap-editor.md`
  and `../../agents/wrap-checker.md` as the system prompts for each role.
- **If you cannot start subagents**, use the in-thread fallback:
  1. Write the brief exactly as step 3 describes — the voice-dictation repair and the
     context capture matter just as much without isolation.
  2. Do the work in-thread, applying `../../agents/wrap-worker.md`, and write the full
     detail to `<run dir>/report.md`. Write the digest into that file too.
  3. Then **clear your working notes from the answer**: re-read only `report.md` and
     `../../references/rubric.md`, and write the block from those two documents alone.
     Isolation is what normally stops the answer sprawling, so reconstructing it this way is
     the whole fallback — do not compose the block from what is still in your head.
  4. Apply step 6's suspicion check and step 7's verbatim emission unchanged.
- Follow Codex approval and filesystem rules when the workflow requests writes, shell
  commands, or edits. Creating the run dir under `$TMPDIR` needs no repo write access.
