# Lumen deck format

Lumen accepts UTF-8 JSON with this shape:

```json
{
  "format": "lumen-deck",
  "version": 1,
  "createdAt": "2026-09-03T12:00:00Z",
  "deck": {
    "title": "Paper or topic title",
    "description": "Optional one-sentence scope",
    "cards": [
      {
        "front": "A self-contained retrieval prompt",
        "back": "A concise answer",
        "notes": "Optional explanation, caveat, or mnemonic",
        "tags": ["paper", "topic"],
        "source": "Paper title, page 7"
      }
    ]
  }
}
```

## Required fields

- Root: `format` exactly `lumen-deck`; `version` exactly `1`; one `deck` object.
- Deck: non-empty `title`; non-empty `cards` array.
- Card: non-empty string `front` and `back`.

## Optional fields

- Root: ISO-8601 `createdAt`.
- Deck: `description`, CSS hex `color`, stable `id`.
- Card: `notes`, string-array `tags`, `source`, stable `id`.

Lumen matches cards by `id` when present, then by a case-insensitive normalized `front` within the same deck. Preserve IDs in revisions. Do not add scheduling fields: Lumen owns the FSRS state on the device.
