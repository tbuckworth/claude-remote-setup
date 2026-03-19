---
description: Spaced repetition review of previously studied papers (SM-2 priority queue)
argument-hint: "[paper-slug (optional)]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
model: claude-opus-4-6
---

# Spaced Repetition Review

You run a focused spaced repetition session on papers the user has already reviewed. No paper acquisition, no initial quiz — just targeted recall questions on due papers, SM-2 updates, and a commit.

## Constants

- **Data repo**: `/Users/titus/pyg/paper-review`
- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}`
- **Database**: `/Users/titus/pyg/paper-review/database.json`
- **Reviews dir**: `/Users/titus/pyg/paper-review/reviews/`
- **SR priority script**: `uv run --python 3.12 ${CLAUDE_PLUGIN_ROOT}/scripts/sr_priority.py /Users/titus/pyg/paper-review/database.json`
- **Bloom's taxonomy stems**: `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md`

## Step 1: Get the Priority Queue

Parse `{{argument}}`:

### No argument (default)
1. Run the SR priority script to get papers where `next_review <= today`
2. Parse the JSON output — array of papers sorted by priority score
3. If empty: "No papers due for review today. Next review: [earliest next_review from database]." — stop here.

### Paper slug provided
1. Look up the slug in `database.json`
2. If found and `status: "reviewed"`: use that paper (even if not technically due)
3. If not found or not reviewed: show error and fall back to the full priority queue

### Present the queue
Show a table:
```
| # | Paper | Days overdue | Last score | Weak levels |
```
Then proceed to Step 2.

## Step 2: Review Each Paper

For each paper in priority order:

### Context
1. Show paper metadata header:
   ```
   **<Full Paper Title>**
   <Lead authors (first 2-3)> (<org>) | <year>
   Also by these authors: <other database papers by the same lead/senior authors, if any>
   Last score: X/Y | Days since review: N | Weak: [levels]
   ```
   Build this from `database.json` only (no API calls). Match authors by last name + first initial to handle format variations.
2. Read the paper's review file from `reviews/YYYY-MM-DD-<slug>.md` to refresh key insights
3. If no review file exists, use `summary` and `key_insights` from `database.json`

### Metadata Warm-up (1 MCQ)
4. Before content questions, ask **1 metadata MCQ** via `AskUserQuestion`. Pick one at random:
   - "What year was this paper published?" — 4 year choices (correct + 3 plausible nearby years from other database papers)
   - "Which organization led this paper?" — 4 org choices (correct + 3 orgs from other database papers)
   - "Who is a lead author of this paper?" — 4 author choices (correct + 3 lead authors from other database papers)
   Present as standard MCQ with 4 options.
   **Scoring**: Track metadata MCQ result separately — do NOT blend into the SM-2 percentage. Record as `metadata_correct: true/false` in the quiz results, but compute pct and quality score from content questions only. Mention the result in the mini-summary but it does not affect scheduling.

### Questions
5. Load question stems from `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md`
6. Ask **3-5 targeted questions** via `AskUserQuestion`:
   - **Focus on weak Bloom's levels** from previous quiz (e.g., if "analyze" was <60%, ask analyze-level questions)
   - If no previous quiz data, ask a spread: 1 understand, 1 apply, 1 analyze
   - Draw from: key insights, review highlights, connections to other papers in the database
   - Include "Done for today" as an option on each question. If selected, save progress immediately and jump to Step 3
7. For each answer:
   - Evaluate: correct / incorrect / partial credit
   - Brief 1-2 sentence corrective feedback (affirm correct parts, gently correct gaps)

### Score and Update SM-2
8. Compute quiz percentage from content questions only (exclude metadata MCQ): `pct = total_correct / total_asked * 100`
9. Map to SM-2 quality:
   - 90-100% -> q=5, 70-89% -> q=4, 50-69% -> q=3, 30-49% -> q=2, 10-29% -> q=1, 0-9% -> q=0
10. Update SM-2 state:
    ```
    EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    EF  = max(EF', 1.3)

    if q >= 3:  # pass
      rep 0 -> interval = 1
      rep 1 -> interval = 6
      rep n -> interval = round(prev_interval * EF)
      repetition_number += 1
    else:        # fail
      repetition_number = 0
      interval = 1

    next_review = today + interval days
    ```
11. Update the paper entry in `database.json` **immediately** (not batched):
    - Append today to `review_dates`
    - Update `easiness_factor`, `interval_days`, `repetition_number`
    - Append quality score to `quality_history`
    - Set `next_review`
    - Update `quiz_results` with new totals (merge with existing if present)
12. Mini-summary: `"Paper X: 3/4 (75%) → quality 4, next review in 6 days | Metadata: ✓/✗"`

Repeat for next paper, or stop if user selected "Done for today".

## Step 3: Session Summary & Commit

1. Show session summary:
   ```
   SR Session Complete:
   - Paper A: 4/5 (80%) → next review Mar 12
   - Paper B: 2/4 (50%) → next review Mar 7
   ```
2. If any papers were reviewed, git commit:
   ```
   cd /Users/titus/pyg/paper-review && git add database.json && git commit -m "SR session: <N> papers reviewed"
   ```
3. Show next upcoming review date from database.
