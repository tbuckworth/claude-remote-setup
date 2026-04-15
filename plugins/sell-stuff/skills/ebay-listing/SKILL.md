---
name: ebay-listing
description: This skill should be used when generating an eBay listing for an item being sold. Provides title optimization, description templates, pricing strategy, and UK-specific defaults.
version: 1.0.0
---

# eBay Listing Optimization

## Title Rules (max 80 characters)
- Lead with **Brand + Model** (e.g. "Microsoft Surface Book 3 15-inch")
- Include key specs: RAM, storage, GPU, screen size
- Add condition keywords: "Excellent", "Mint", "Like New"
- Use abbreviations to save space: GB, SSD, i7, FHD
- No filler words ("amazing", "wow", "look", "L@@K")
- No ALL CAPS except model numbers

## Description Template

Structure as clean HTML with these sections:

1. **Item Description** — 2-3 sentence overview of what the item is and why someone would want it
2. **Specifications** — table format with key specs
3. **Condition** — honest, specific condition notes. Mention any defects with photos referenced
4. **What's Included** — bullet list of everything in the box/package
5. **Shipping** — Royal Mail method, dispatch timeframe
6. **Returns** — 30-day returns accepted (eBay standard, improves search ranking)

## Pricing Strategy
- **Buy It Now + Best Offer** for items over £50 — set BIN 10-15% above sold median to leave negotiation room
- **7-day Auction** for items with uncertain value or high demand variance
- **Free P&P** if item is small/light — improves search ranking. Factor shipping cost into price
- End auctions on **Sunday evening** (highest traffic)

## Condition Mapping (eBay condition IDs)
- New: 1000
- New other (no original packaging): 1500
- Refurbished: 2500
- Used: 3000
- For parts or not working: 7000

## Common Category IDs (eBay UK)
- Laptops & Netbooks: 175672
- Keyboards & Keypads: 33963
- Men's T-Shirts: 15687
- Men's Casual Shirts: 57990

## UK Defaults
- Site: ebay.co.uk
- Currency: GBP
- Shipping: Royal Mail 2nd Class (items under 2kg), Evri/DPD for larger
- Location: United Kingdom
- Returns: 30-day buyer-paid returns
- Item location: get from user or default to "London, United Kingdom"

## Photo Guidance
- First photo = hero shot on clean background showing full item
- Photo 2-3 = different angles
- Close-ups of any defects (mandatory for Used condition)
- Include accessories laid out
- Max 12 photos on eBay — use at least 3
