#!/usr/bin/env python3
"""Validate a Lumen deck exchange file without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"]
    if data.get("format") != "lumen-deck":
        errors.append("format must be exactly 'lumen-deck'")
    if data.get("version") != 1:
        errors.append("version must be exactly 1")
    deck = data.get("deck")
    if not isinstance(deck, dict):
        return errors + ["deck must be an object"]
    if not nonempty_string(deck.get("title")):
        errors.append("deck.title must be a non-empty string")
    if "description" in deck and not isinstance(deck["description"], str):
        errors.append("deck.description must be a string")
    if "color" in deck and (not isinstance(deck["color"], str) or not HEX_COLOR.fullmatch(deck["color"])):
        errors.append("deck.color must be a six-digit CSS hex colour")
    cards = deck.get("cards")
    if not isinstance(cards, list) or not cards:
        return errors + ["deck.cards must be a non-empty array"]
    seen_ids: set[str] = set()
    for index, card in enumerate(cards, start=1):
        prefix = f"card {index}"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("front", "back"):
            if not nonempty_string(card.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string")
        for field in ("notes", "source"):
            if field in card and not isinstance(card[field], str):
                errors.append(f"{prefix}.{field} must be a string")
        tags = card.get("tags", [])
        if not isinstance(tags, list) or any(not nonempty_string(tag) for tag in tags):
            errors.append(f"{prefix}.tags must be an array of non-empty strings")
        card_id = card.get("id")
        if card_id is not None:
            if not nonempty_string(card_id):
                errors.append(f"{prefix}.id must be a non-empty string")
            elif card_id in seen_ids:
                errors.append(f"{prefix}.id duplicates an earlier card id")
            else:
                seen_ids.add(card_id)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        with args.path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Valid Lumen deck: {len(data['deck']['cards'])} cards in {data['deck']['title']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
