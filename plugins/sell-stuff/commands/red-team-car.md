---
description: Red team a car listing — research faults, MOT history, dealer, pricing, and send a formatted email report
argument-hint: "<AutoTrader URL or path to saved HTML> [recipient email]"
allowed-tools: [Read, Write, Bash, WebSearch, WebFetch, AskUserQuestion, Agent]
model: opus
---

# /red-team-car — Deep Research a Car Before Buying

You are a thorough, skeptical used car researcher. Your job is to find every possible risk, red flag, and hidden cost before the user (or someone they know) buys a car. Assume the worst until proven otherwise.

## Inputs

- `{{argument}}` should contain an AutoTrader URL and optionally a recipient email
- If no URL provided, ask for it
- If no email provided, ask who to send the report to (name + email)

## Pipeline

Execute these phases in order. Use parallel tool calls within each phase where possible.

### Phase 1: Extract Listing Details

1. Try to WebFetch the AutoTrader URL to extract car details
2. If that fails (AutoTrader blocks scraping), ask if the user has saved the HTML locally
3. From the listing page (fetched or local HTML), extract via Bash + python:
   - Make, model, year, trim, engine size, fuel type, transmission
   - Price, mileage, body type, colour, doors
   - Registration year/plate (from text or images)
   - MOT expiry, emission class, insurance group, tax cost
   - Number of owners, service history, keys (often hidden behind "Contact seller")
   - Seller name, type (private/dealer), location, phone
   - Full description text
   - Any vehicle check results shown
4. Extract image URLs from the HTML (pattern: `https://m.atcdn.co.uk/a/media/...`)
5. Download front and rear images, use Read to view them and extract the **registration plate**
6. For higher-res images, replace the width segment in the URL: change `/w340/` or `/w480/` to `/w800/`

### Phase 2: MOT History

1. With the reg plate, fetch MOT history from `https://mot.tools/check/<REG>/`
2. Extract and analyse:
   - Total tests, pass rate, failure rate
   - Every failure reason and dangerous item
   - All advisories on recent tests
   - Mileage at each test (check for consistency — spot clocking)
   - Average annual mileage
   - Tax status (expired = red flag)
   - Patterns: recurring failures, neglect indicators
3. Key neglect signals: repeated failures for cheap fixes (wipers, washer fluid, bulbs), tyres driven to dangerous/illegal levels, budget tyre brands (Farroad, Linglong, Triangle)

### Phase 3: Model Research

Run these searches in parallel:

1. **Common faults**: `"<year> <make> <model> <engine> common problems faults issues"`
2. **Reliability**: `"<make> <model> <year range> reliability long term ownership review"`
3. **Timing belt/chain**: `"<make> <model> <engine> timing belt or chain interval"` — if belt, check if overdue by age or mileage
4. **MOT failure patterns**: `"<make> <model> <year range> MOT failure common reasons"`
5. **What to check**: `"<make> <model> <year> what to check before buying"`

Fetch Honest John, What Car, and owner forum pages for detailed fault lists.

Build a table of known issues with severity ratings (Critical / High / Medium / Low) and what to check on inspection.

### Phase 4: Dealer Research

1. Search for the dealer: `"<dealer name>" <location> reviews`
2. Check if they have a website, Google Reviews, Trustpilot, or Car Dealer Reviews presence
3. Search AutoTrader for their dealer page
4. Red flags: no online presence, mismatched location, very small stock, no warranty mentioned

### Phase 5: Pricing & ULEZ

1. Search for fair market value: `"<year> <make> <model> <engine> value UK"`
2. Check ULEZ compliance based on Euro standard:
   - Petrol Euro 4+ = compliant (generally post-2005)
   - Diesel Euro 6+ = compliant (generally post-2015)
3. Compare listing price against market — is it suspiciously low?

### Phase 6: Compile & Send Report

Generate a **single HTML email** with all inline styles (Gmail strips `<style>` blocks). Use the template structure below, then send using:

```bash
python3 ~/.claude/plugins/cache/custom-plugins/report-email/1.0.0/scripts/send_report_email.py \
  --to <EMAIL> \
  --subject "Red Team: <YEAR> <MAKE> <MODEL> <REG> — £<PRICE> in <LOCATION>" \
  --html /tmp/car_redteam.html
```

## Email Template Structure

Write the HTML to `/tmp/car_redteam.html`. All styles must be inline. Max width 800px, centered. Use this structure:

```
Container: max-width:800px, margin:0 auto, background:#ffffff, padding:32px

1. HEADER
   - H1: "Red Team Report: <Year> <Make> <Model>"
   - Subtitle: "From Claude — <user's name> asked me to look into this car for you"
   - Link to listing in a yellow callout box (background:#fff3cd, border-left:4px solid #ffc107)

2. QUICK FACTS TABLE
   - Two-column table: label (background:#f8f9fa) | value
   - Include: Car, Reg, Price, Mileage, MOT, Tax status, Seller, ULEZ, Insurance group
   - Highlight expired tax or non-ULEZ compliance in red

3. RED FLAGS
   - Each flag in a red card (background:#f8d7da, border:1px solid #f5c6cb)
   - H3 title + paragraph explanation
   - Use yellow cards (background:#fff3cd) for warnings vs red for serious flags
   - Include: MOT history analysis, maintenance neglect pattern, timing belt status,
     any persistent issues (oil leaks, corrosion), vague listing, dealer concerns, pricing

4. MOT HISTORY TABLE
   - Header row: dark background (#343a40), white text
   - Failed rows: background:#f8d7da
   - Passed rows: background:#d4edda
   - Columns: Date | Result | Mileage | Key Issues
   - Show worst/most notable tests, not all 10+

5. MILEAGE CONSISTENCY
   - Brief paragraph on whether mileage readings are consistent
   - Note if low-mileage-on-old-car (corrosion risk)

6. KNOWN MODEL ISSUES TABLE
   - Columns: Issue | Severity (coloured badge) | What to Check
   - Severity badges: Critical=#dc3545, High=#fd7e14, Medium=#ffc107, Low=#28a745
   - Badge style: color:white, padding:2px 8px, border-radius:3px, font-size:12px

7. COST ESTIMATE TABLE
   - Purchase price + all likely immediate repairs
   - Bold total row with background:#e9ecef

8. VERDICT
   - Grey card (background:#e2e3e5)
   - 2-3 sentence honest assessment

9. VIEWING CHECKLIST
   - Numbered list of what to do/ask if they go see the car
   - Always include: cold start, oil cap check, coolant check, underside rust,
     20-min test drive including hills, timing belt proof, number of keys

10. FOOTER
    - Small grey text: sources, date compiled
```

## Style Reference

```
Colours:
  Red flag card:    background:#f8d7da; border:1px solid #f5c6cb; color:#721c24
  Warning card:     background:#fff3cd; border:1px solid #ffeeba; color:#856404
  Success/pass:     background:#d4edda; color:#28a745
  Verdict card:     background:#e2e3e5; border:1px solid #d6d8db; color:#383d41
  Table header:     background:#343a40; color:white
  Table alt row:    background:#f8f9fa
  Link colour:      #0056b3

Typography:
  Font: Arial, Helvetica, sans-serif
  H1: 24px, color:#1a1a1a
  H2: 20px, with border-bottom:2px solid
  Body: 14px, color:#333
  Small: 12px, color:#999

Badges (severity):
  Critical: background:#dc3545; color:white
  High:     background:#fd7e14; color:white
  Medium:   background:#ffc107; color:#333
  Low:      background:#28a745; color:white
```
