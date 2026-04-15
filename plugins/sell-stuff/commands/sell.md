---
description: Sell an item on eBay — research prices, generate listing, optionally post via browser automation
argument-hint: "[item name or 'list' to see all items]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion, Agent]
model: opus
---

# /sell — Sell an Item

You are helping the user sell an item on eBay with minimal effort. Follow the 5 phases below sequentially. After each phase, write state to `items/<slug>/listing.json` so the session can be resumed if interrupted.

## State Recovery

Before starting, check if `items/*/listing.json` exists for this item. If found and not `status: "complete"`, offer to resume from the last completed phase.

## Phase 1: Identify the Item

1. If `{{argument}}` is empty or "list":
   - Run `gh issue list --repo tbuckworth/tasks --label "list:to-sell" --json number,title,body,labels`
   - Present the list and ask which item to sell
2. Otherwise, fuzzy-match `{{argument}}` against issue titles
3. If ambiguous, ask the user to clarify
4. Generate a slug (lowercase, hyphenated) from the item name
5. Create `items/<slug>/` directory
6. Write initial state:
   ```json
   {"issue_number": <N>, "slug": "<slug>", "status": "identifying", "title": "<issue title>"}
   ```

## Phase 2: Research and Gather Details

1. Ask the user (in a single AskUserQuestion with all questions):
   - Exact item description (model, specs — help them with what you know)
   - Condition: New / Like New / Very Good / Good / Acceptable
   - Accessories included?
   - Any defects to disclose?
   - Photos ready? (path to folder, or they'll add to `items/<slug>/photos/` later)
   - Battery health if applicable (they may have run `powercfg /batteryreport`)

2. Research pricing with WebSearch:
   - Search: `"<item>" sold site:ebay.co.uk`
   - Search: `"<item>" price UK 2026`
   - Extract price range (low / median / high)

3. Present findings and recommend:
   - Price range from sold listings
   - Recommended listing price with rationale
   - Auction vs Buy It Now recommendation
   - Let user confirm or adjust

4. Update `listing.json` with status `"researched"` and all gathered data

## Phase 3: Generate Listing

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/ebay-listing/SKILL.md` for formatting rules
2. Generate:
   - **Title** (max 80 chars, keyword-optimized per skill rules)
   - **Description** (structured HTML per skill template)
   - **Category** (best match from skill's category list, or research if not listed)
   - **Condition** (mapped to eBay condition values)
   - **Price** and format (BIN / Auction)
   - **Item specifics** (brand, model, key specs)
3. Present the complete draft to the user for approval
4. On approval, copy listing title + description to clipboard:
   ```bash
   echo "<title>" | pbcopy
   ```
5. Save the full listing to `items/<slug>/listing.md`
6. Update `listing.json` with status `"draft_approved"` and all listing fields

## Phase 4: Post to eBay (Conditional)

Check if `${CLAUDE_PLUGIN_ROOT}/docs/EBAY_FORM.md` contains validated form field mappings (look for "VIABLE" in the Verdict section). If not, skip to Phase 5 with message:

> "Listing text saved to `items/<slug>/listing.md` and copied to clipboard. Open ebay.co.uk/sell/create and paste. Run `/sell` again after the Playwright spike to enable automated posting."

If the form doc confirms viability:
1. Use Playwright MCP tools to navigate to `https://www.ebay.co.uk/sell/create`
2. Take a snapshot to check login state. If not logged in, alert user to log in manually in the browser window and wait
3. Follow field mappings from `docs/EBAY_FORM.md` to fill the form
4. After each major section, take a screenshot to verify
5. Upload photos if available in `items/<slug>/photos/`
6. Before final submission: take screenshot and ask user for explicit confirmation
7. On approval: submit and capture the listing URL
8. Update `listing.json` with status `"listed"`, eBay URL, and timestamp

## Phase 5: Update GitHub Issue

1. Comment on the issue with listing details:
   ```bash
   gh issue comment <number> --repo tbuckworth/tasks --body "Listed on eBay: <url or 'draft ready'>\nPrice: £<price>\nFormat: <BIN/Auction>"
   ```
2. Add appropriate label:
   - If posted: `gh issue edit <number> --repo tbuckworth/tasks --add-label "status:listed"`
   - If draft only: `gh issue edit <number> --repo tbuckworth/tasks --add-label "status:draft-ready"`
3. Update `listing.json` with status `"complete"`
4. Confirm to the user with a summary of what was done
