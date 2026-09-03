---
name: lumen-flashcards
description: Create or revise an importable Lumen flashcard deck from a paper, reMarkable annotations, notes, quiz gaps, or a Lumen learning report. Use when asked to make flashcards for Lumen, export review cards, or improve cards using Lumen feedback.
---

# Lumen flashcards

Create a small, high-quality deck that imports directly into the Lumen iPhone web app.

Read [references/deck-format.md](references/deck-format.md) before writing a deck.

## Card quality

- Test one retrievable idea per card. Split lists or compound questions unless the whole set must be recalled together.
- Make the front unambiguous without relying on surrounding conversation.
- Keep the answer concise, then put explanation or caveats in `notes`.
- Prefer recall, comparison, mechanism, and application prompts over recognition or yes/no questions.
- Preserve useful provenance in `source`; do not invent citations or claims absent from the source.
- When quiz feedback exists, prioritise corrected misunderstandings and prerequisite knowledge. Do not turn every highlighted sentence into a card.

## Create a deck

1. Draft 5–20 cards by default, or use the number the user requests.
2. Write one `*.lumen.json` file following the reference schema.
3. Prefer `~/Library/Mobile Documents/com~apple~CloudDocs/Lumen Inbox/` when that iCloud Drive location exists; otherwise use `~/Downloads/`. Create only the `Lumen Inbox` subfolder if needed.
4. Validate the finished file:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_lumen_deck.py <path-to-deck.lumen.json>
   ```

5. Fix and revalidate any reported problem. Then tell the user the exact path and: **On iPhone, open Lumen → Add → Import → Choose a deck file.**

## Paper-review integration

For a completed paper review, build the deck from active `atomic_cards` when present. Otherwise use the paper’s key insights plus misconceptions revealed by the quiz. Include the paper title in `source` and use the paper title as the deck title.

## Revise from a learning report

When given a `lumen-learning-report.md` file, diagnose repeatedly missed cards. Revise only ambiguous, overloaded, or context-poor cards. Preserve each existing card `id` when updating it so Lumen retains its scheduling history on re-import.
