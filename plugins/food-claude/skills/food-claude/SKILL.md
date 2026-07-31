---
name: food-claude
description: Choose and add editable Just Eat Business meal selections from natural-language preferences with the Food Claude Playwright workflow. Use when the user asks to fill, choose, change, or review upcoming Just Eat Business meal slots.
---

# Food Claude

Use the upstream Food Claude checkout as the canonical site procedure. Resolve it from
`$FOOD_CLAUDE_SOURCE_DIR` when set, otherwise `~/pyg/food-claude`. Before browsing,
read both of these files completely:

- `commands/order.md`
- `skills/just-eat-ordering/SKILL.md`

Use this plugin's Playwright MCP tools. If no browser is installed, the upstream launcher
may download Playwright Chromium once.

## Guardrails

- Never type or request login credentials. Ask the user to log in in the opened browser.
- Treat the user's explicit request to fill meal slots as authorization to click the editable
  `CONFIRM CHOICE` action described upstream. If the request is exploratory or ambiguous,
  show the proposed days first and ask once before changing selections.
- Choose only one of the two restaurant alternatives for each day unless the user explicitly
  asks for two meals.
- Skip days that already contain a selection unless the user asks to change them.
- Trust the live subsidy balance. Do not exceed it unless the user explicitly approves a
  personal charge.
- Never click actions labelled `Place order`, `Pay`, or `Submit order`.
- Stop and ask when the layout, selection state, deadline, allergen information, or financial
  effect is unclear.

After making selections, report each day, restaurant, dishes, price, remaining subsidy,
and any notable choices. Remind the user that selections remain editable until their deadlines.
