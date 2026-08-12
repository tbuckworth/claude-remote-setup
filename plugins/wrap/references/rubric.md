# The wrap output contract

This is the single source for how a wrapped answer is written. The `wrap-editor` agent
follows it, the Codex in-thread fallback follows it, and follow-up answers during a sticky
wrap follow it. Nothing else about the answer is negotiable.

The reader is an academic who values truth above blame, reads fast, and is trying to hold a
problem at a high level. He has already been given the low-level detail by other agents and
found it counterproductive. He can ask for anything he wants back, and the full report is on
disk, so nothing you cut is lost.

**By default the whole block fits on one screen — roughly 200 words.** If it does not, it is
wrong, no matter how good the material is. Everything below serves that.

The one exception is `--full`, defined at the end of this document. It is the only thing that
relaxes any limit here, and the reader has to ask for it explicitly.

---

## Sections and their limits

The limits are hard. They apply by default, not only under a flag.

| Section | Limit |
|---|---|
| 1. Bottom line | **One** bold claim + at most **2** sentences of support |
| 2. What follows | **At most 5 bullets, one sentence each** — or one table of at most 5 rows |
| 3. Flags | **At most 2**, one line each. Omit entirely when there is nothing |
| 4. `Ask for:` | One line |

Sections 3 and 4 appear only when they have content. Never emit an empty heading.

### 1. Bottom line

The answer itself, as a claim, in bold, as the **first characters of the response**.

- Good: `**Retry logic is the bottleneck, not the DB.**`
- Bad: `I investigated the latency issue and found that the retry logic...`
- Bad: `Here's what I found:`

For a question, this is the answer. For work that was executed, this is what now works and
what does not — not a narration of the steps taken to get there.

**One claim, always.** If the prompt asked two things, the bottom line answers the one that
matters more and the second becomes a bullet. Two bold claims stacked at the top is the most
common way this format degrades into an essay.

### 2. What follows

Only material that changes a decision or corrects a belief. **One sentence per bullet.** A
bullet that needs a second sentence is two bullets, or it is one bullet plus something for
the `Ask for:` line.

Use a **table** instead of bullets when the content is genuinely tabular — three or more
items compared on two or more real attributes. Not in addition to bullets. Cap it at 5 rows;
a longer comparison belongs in the report with its topic named on the `Ask for:` line.

Use a fenced code block only when the exact text matters and is short — a command to run, a
signature. Never to illustrate.

### 3. Flags

Only when there is something to say. One line each, `⚠` prefix, at most two. Cover:

- A claim that is shaky, or assumed rather than established.
- Something that contradicts what was already established in the conversation.
- A known agent failure pattern spotted in the report (see below).

If there are more than two, flag the two that would most change what the reader does, and
put "other caveats" on the `Ask for:` line. A wall of warnings reads as noise and trains the
reader to skip the section — which defeats the one part of this that cannot be recovered by
asking.

If a background check has been dispatched for a flag, say so on the same line:
`⚠ It reports "all tests pass" with no test output. Checking — I'll update you.`

### 4. Ask for:

A single line naming the threads that exist in the full report but were cut, separated by
`·`. This is the drill-down menu and the reason cutting is safe. Name the thread by what it
answers, not by its section title.

`Ask for: the repro · why the backoff compounds · the load-test plan`

Omit only when nothing was cut, which is rare.

---

## The three rules that produce the cut

### The deletion test

Apply to every line:

> If I deleted this line, would the reader make a different decision, or hold a belief that
> is now wrong?

If no — delete it. Not shorten it. Delete it.

### The ranking rule

The deletion test alone is too weak, because on a rich topic almost everything passes it
marginally. So: **when more than five points survive the test, keep the five that change the
decision most and name the rest on the `Ask for:` line.** Ranking, not inclusion, is the job.

Cutting a true and interesting point is correct behaviour here, not a loss. It is on disk
and one question away.

### The compression floor

**The block must be shorter than the digest it came from.** If your output is longer than
your input, you have expanded rather than distilled, and you must cut again before emitting.
This is the check that catches the failure mode where rich source material quietly licenses
a long answer.

## Ban list

Absolute. These are the failure modes that produce the walls of text this exists to prevent.

- **No preamble and no sign-off.** The first character is the bottom line. The last line is
  `Ask for:`. Nothing before, nothing after.
- **No process narration.** "I read `pool.py`, then ran the repro, then checked..." is
  banned unless the process *is* the finding.
- **No restating the question.** The reader wrote it.
- **No recap sentences.** A sentence whose only content is a summary of bullets already
  present is deleted.
- **No filler hedges**: "it's worth noting", "importantly", "as you may know",
  "interestingly".
- **No thoroughness display.** Detail included to show the work was done, rather than because
  the reader needs it, is deleted. This is the single most common violation.
- **No offering further help** beyond the `Ask for:` line.
- **No apology or self-assessment** about the answer's own length or quality.

## Altitude rule

Report at the level of consequences and decisions. Drop to mechanism only when the mechanism
is what changes the decision.

- High altitude: "The fix is a config change, not a migration."
- Low altitude, cut: "`backoff.py:44` sets `base=2.0` and multiplies by `attempt**2` inside
  the retry loop, called from `pool.acquire()` at line 118."

**Identifiers are low altitude and are cut by default.** No arXiv numbers, author-year
strings, venue names, version numbers, file paths or line numbers in the body — they are
lookup keys, not insight, and they are what makes a short answer read as dense. Keep an
identifier only when it *is* the answer ("the bug is in `backoff.py`"). Otherwise say what
the work showed and let the reader ask for the citation.

Say "someone already published the exact combination in offline RL", not "EDAC (An et al.,
NeurIPS 2021, arXiv:2110.01548)". The second one is the report's job.

## Evidence discipline

The worker's digest marks each claim `[verified]`, `[inferred]` or `[assumed]`.

- Do not carry those markers into the output — they are noise.
- Do carry the *distinction*: never state an `[assumed]` claim in the same flat register as a
  `[verified]` one. Either attribute it, flag it, or cut it.
- A number that appears only in the report's prose and never in captured output is not a
  measurement. Treat it as `[assumed]` no matter how it was labelled.

## Known agent failure patterns

Worth a flag when the report shows one:

| Pattern | What it looks like |
|---|---|
| Phantom pass | "All tests pass" with no test output, or output showing skips |
| Prose-only numbers | A benchmark figure that never appears in captured stdout |
| Silent narrowing | The scope shrank while the verdict improved |
| Asserted fix | The change was written but never executed |
| Fabricated surface | An API, flag or file cited that was never actually read |
| Fixture leakage | Expected values read from the same file that defines them |

Flag the *pattern*, not a demand. One line. Do not lecture.

---

## `--full`

Use it only when the reader has explicitly asked for the long version.

**Dropped under `--full`:**

- the one-screen / ~200-word target,
- every section limit in the table (bullet count, sentence-per-bullet, flag count, one claim),
- the ranking rule — everything that survives the deletion test may be included,
- the identifier ban — cite arXiv IDs, authors, versions, file paths freely.

**Still binding under `--full`:**

- the deletion test — a line that changes nothing is still deleted,
- the ban list — no preamble, no process narration, no recap, no sign-off,
- the altitude rule — still lead with consequences, even when the mechanism follows,
- the compression floor — the block is still shorter than the digest it came from,
- the bottom line still comes first, and the `Ask for:` line still comes last.

`--full` means "show me everything that matters", not "show me everything".

Nothing other than `--full` relaxes anything above. Rich source material is not a licence to
exceed the limits — it is the reason they exist.

## Worked example

```
**The idea is not novel, and the weaker half is the one you thought was stronger.**
Worst-case aggregation over a reward ensemble is the standard anti-overoptimization move,
and decorrelation penalties in reward-model training already exist.

- The exact combination of both halves was published in offline RL five years ago
- Whether worst-case beats the mean is genuinely contested, and nobody has reconciled it —
  that gap is the cheapest defensible paper here
- Jointly-trained diversity is roughly half illusory: members collude to look diverse
- One slot is open: decorrelating over failure modes found under optimisation pressure

⚠ The closest paper on the decorrelation half was never actually retrieved — CAPTCHAs.
⚠ The claim that your combination is already taken rests on secondary sources. Checking now.

Ask for: the paper list · why worst-case is contested · the open slot in detail · the
practical trap with uncentered ensembles
```

That is the same material as a 689-word answer that failed. Everything cut is in the report.
