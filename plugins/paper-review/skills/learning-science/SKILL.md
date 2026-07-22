---
name: learning-science
description: "Learning science techniques for paper review: Bloom's taxonomy question generation, Feynman technique, spaced repetition, and corrective feedback"
---

# Learning Science Techniques for Paper Review

## Bloom's Taxonomy — Progressive Question Generation

Generate questions at progressively higher cognitive levels. Start at Remember/Understand and only progress when the user demonstrates mastery (≥50% correct at each level).

See `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md` for question stem templates at each level.

### Difficulty Calibration
- 6 questions total: 2 Remember/Understand + 2 Apply/Analyze + 2 Evaluate/Create
- No adaptive difficulty — weak levels are tracked and revisited during spaced repetition (Stage 4)
- Brief 1-2 sentence feedback per answer

## Feynman Technique

1. Pick 2 key concepts from the paper's highlights
2. Ask the user: "Explain [concept] as if teaching someone who has never encountered it"
3. Listen for:
   - Vague hand-waving ("it basically just...")
   - Circular definitions (using the term to define itself)
   - Missing mechanism (what, but not how or why)
4. Provide corrective feedback:
   - Affirm what they got right: "You correctly identified that..."
   - Gently point to gaps: "One thing to consider is..."
   - Reference the paper: "The authors specifically address this on page X where they say..."

## Spaced Repetition (SM-2 Algorithm)

Per-paper state: `easiness_factor` (EF, default 2.5), `interval_days`, `repetition_number`, `quality_history`.

### Quality mapping from quiz percentage

| Score | Quality (q) | Meaning |
|-------|------------|---------|
| 90-100% | 5 | Perfect |
| 70-89% | 4 | Correct with hesitation |
| 50-69% | 3 | Correct with difficulty |
| 30-49% | 2 | Failed |
| 10-29% | 1 | Failed, vaguely remembered |
| 0-9% | 0 | Blackout |

### Update rules

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

### SR priority function (for ordering papers in Stage 4)

```
quality_urgency  = (5 - avg_recent_quality) / 5
overdue_urgency  = min(days_overdue / 30, 1.0)
recency_factor   = min(days_since_review / 90, 1.0)

priority = 0.4 * quality_urgency + 0.35 * overdue_urgency + 0.25 * recency_factor
```

Computed by `${CLAUDE_PLUGIN_ROOT}/scripts/sr_priority.py`.

## Corrective Feedback Patterns

After each quiz answer:

### Correct answer
- Brief affirmation: "Exactly right."
- Optionally add depth: "And to build on that, the paper also notes..."

### Partially correct
- Affirm correct parts: "You're right that [X]."
- Fill gaps: "However, the paper also emphasizes [Y], which is important because..."

### Incorrect
- Don't say "wrong" — say "Not quite" or "Let me clarify"
- Explain the correct answer with reference to specific paper content
- If the misconception is common, briefly explain why it's a natural mistake

## Progressive Summarization (Forte)

The 4-layer distillation happens naturally across the review:
1. **Layer 1**: Full paper text (the PDF itself)
2. **Layer 2**: Highlights from reMarkable (what caught the reader's eye)
3. **Layer 3**: Quiz results and Feynman explanations (tested understanding)
4. **Layer 4**: Key insights in the review summary (distilled knowledge)
