# eBay Sell Form Reference

> **Status**: SPIKE COMPLETE — 2026-04-14

## Form URL

Start at: `https://www.ebay.co.uk/sl/prelist/suggest`

This is the pre-listing flow. The full listing editor is at `/sl/list` but requires login.

## Navigation Flow

### Step 1: Item Search (no login required)
- URL: `/sl/prelist/suggest`
- Textbox: `"Tell us what you're selling"` — type item keywords
- eBay shows autocomplete suggestions in a listbox
- Click "Search" button to proceed

### Step 2: Product Match (no login required)
- URL: `/sl/prelist/identify?title=...`
- eBay auto-selects category (e.g. `Computers/Tablets & Networking > Laptops & Netbooks > PC Laptops & Netbooks`)
- Filter chips available: Brand, Screen Size, Processor, Model, Operating System, Storage Type, Features, SSD Capacity
- Shows "Top picks from the product library" — click a matching product
- Also shows "Related listings from other sellers" — use these if no catalogue match
- "Continue without match" button available if no product fits

### Step 3: Condition Selection (no login required)
- A dialog "Confirm details" appears after selecting a product
- Shows product details pre-filled
- Radio buttons for condition:
  - New
  - Opened – never used
  - Seller refurbished
  - Used
  - For parts or not working
- "Continue to listing" button (disabled until condition selected)

### Step 4: Login Gate
- Clicking "Continue to listing" redirects to `signin.ebay.co.uk`
- Standard eBay login form — email/password, no CAPTCHA observed
- After login, redirects to `/sl/list` with all pre-listing data preserved in URL params
- **Login persists** via `browser-data/` directory cookies between sessions

### Step 5: Full Listing Editor
- URL: `/sl/list?title=...&condition=3000&categoryId=177&...`
- **NOT YET DOCUMENTED** — requires completing login first
- This is where title, description, photos, price, shipping, etc. are set
- TODO: Log in once, then snapshot this page to document all fields

## Login Detection

Check page URL after navigation:
- If URL contains `signin.ebay.co.uk` → not logged in
- If URL contains `/sl/list` → logged in, on listing editor
- Take a snapshot and look for "Sign in" text in the header

## Anti-Bot Measures

- **None observed** during the spike
- No CAPTCHA on the pre-listing flow
- No CAPTCHA on the login page
- Playwright with `--browser chrome` (not headless) was not blocked
- eBay's accessibility tree is well-structured with proper ARIA roles

## Key Element Patterns

Elements can be found by role + name:
- Textbox: `role=textbox, name="Tell us what you're selling"`
- Search button: `role=button, name="Search"`
- Product matches: `role=button` with product description text
- Condition radios: `role=radio, name="Used"` (etc.)
- Continue button: `role=button, name="Continue to listing"`

## Condition ID Mapping

| Condition | eBay ID (in URL param) |
|---|---|
| New | 1000 |
| Opened – never used | 1500 |
| Seller refurbished | 2500 |
| Used | 3000 |
| For parts or not working | 7000 |

## Verdict

**VIABLE** — with caveats:

1. Pre-listing flow (steps 1-3) works perfectly via Playwright without login
2. Login required once — user logs in manually, cookies persisted in `browser-data/`
3. Full listing editor (step 5) not yet documented — need to complete login and snapshot
4. No anti-bot measures detected
5. Accessibility tree is excellent — clean roles and labels for all interactive elements

### Next Steps
1. User logs into eBay once in the Playwright browser
2. Navigate to the full listing editor and snapshot all fields
3. Update this document with field mappings for the listing editor
4. Then the `/sell` command can automate the full flow
