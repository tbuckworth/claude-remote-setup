# wrap

A layer between you and the working agents.

```
/wrap why is the p99 latency spiking on the auth service
```

The prompt does not run in your main context. It goes to a subagent, which does the work and
writes everything it found to a report file. A second agent — whose context contains only
the brief and that report — turns it into the answer you read. The main thread relays that
block verbatim.

## Why it is built this way

Telling a model to be concise does not work; the instruction loses to the model's
disposition. Three structural things do work, and this uses all three:

1. **The editor has nothing to narrate.** It did not do the work and cannot see the
   conversation, so there is no process to recount and no context to recap. This is what
   produces brevity without a word limit.
2. **A deletion test, then hard section limits.** Every line must survive *"if I cut this,
   would Titus decide differently or believe something wrong?"* — and when more survives
   than fits, the editor ranks and drops rather than stretching. The limits exist because
   the deletion test alone lost to rich material.
3. **Verbatim relay.** The main thread emits the block and stops, which removes its last
   chance to re-narrate.

## What you get back

Claim first, in bold. Then only what changes a decision. Then flags, if there are any. Then
an `Ask for:` line naming what was cut — that line is why cutting is safe.

The full contract is [`references/rubric.md`](references/rubric.md).

## Being lied to

The main thread holds context the workers don't. When something comes back that can't be
true given what you already established — or matches a known agent failure (tests "passing"
with no output, a number that appears only in prose, a scope that narrowed while the verdict
improved, a fix written but never run) — it flags it. If the doubt is specific and
checkable, it dispatches `wrap-checker` in the background and tells you, then reports the
verdict in one line when it lands.

This is exception handling, not a standing audit. Most wraps produce no flag at all. Vague
unease earns one line at most; a background check needs both a specific claim and a concrete
reason to doubt it.

## Follow-ups

After a wrap you stay wrapped. "Expand on the second point" reads the saved report and
answers in the same register — **no new subagent**, because the detail is already on disk.
A fresh worker spawns only when you ask for something the report does not contain.

`/wrap off` (or "back to normal") ends it.

## Voice dictation

Prompts are assumed to be dictated and possibly mis-transcribed. The brief-writing step
repairs near-homophones and mangled names against the project context silently — "codecs" →
Codex, "plot code" → Claude Code, "safe floor" → saved file — and only asks when the repair
is ambiguous *and* changes the work.

## Knobs

The block is capped by default: one bold claim, at most 5 one-sentence bullets, at most 2
flags, one `Ask for:` line — roughly one screen. Identifiers (arXiv IDs, author-year, file
paths) are cut from the body by default; they are lookup keys, not insight.

`/wrap --full <prompt>` drops those limits. The deletion test, ban list, altitude rule and
compression floor still apply.

The caps are not the original design — the first version relied on the deletion test alone
and produced a 689-word answer on a rich literature question. On a dense topic almost
everything passes that test marginally, so ranking and stopping had to be made explicit.

## Layout

| Path | What it is |
|---|---|
| `commands/wrap.md` | The canonical workflow. Single source for both platforms. |
| `references/rubric.md` | The output contract. |
| `agents/wrap-worker.md` | Does the work, writes the report, returns an evidence-marked digest. |
| `agents/wrap-editor.md` | Rubric only, `Read` only. Produces what you see. |
| `agents/wrap-checker.md` | Background check of one suspect claim. Refutes by default. |
| `skills/wrap/SKILL.md` | Natural-language trigger, and the Codex shim. |
| `tests/test_wrap_plugin.py` | Static validation. Run after editing anything here. |

On Codex, if subagents are unavailable the skill falls back to doing the work in-thread,
writing the report, then reconstructing the answer from **only** the report and the rubric —
degraded isolation, identical output contract.
