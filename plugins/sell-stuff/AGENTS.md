# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Personal project for listing and selling items with minimal effort. This repo is also a Claude Code plugin (`sell-stuff@custom-plugins`).

## Item Inventory

Source of truth: `gh issue list --repo tbuckworth/tasks --label "list:to-sell"`

## Architecture

This repo doubles as a Claude Code plugin. Key directories:

- `commands/sell.md` — the `/sell` command (5-phase flow: identify, research, generate, post, update)
- `skills/ebay-listing/` — eBay listing optimization knowledge (title rules, pricing, categories)
- `docs/EBAY_FORM.md` — eBay sell form field mappings (populated from Playwright spike)
- `items/<slug>/` — per-item records with `listing.json` (state) and `photos/`
- `browser-data/` — Playwright persistent browser state for eBay login (gitignored)

## Playwright MCP

Configured in `.mcp.json`. Uses persistent `browser-data/` directory to keep eBay login cookies across sessions. The `/sell` command checks `docs/EBAY_FORM.md` for a "VIABLE" verdict before attempting browser automation — otherwise falls back to generating listing text for manual copy-paste.

## State Recovery

Each item's `items/<slug>/listing.json` tracks which phase of the sell flow has been completed. The `/sell` command checks for existing state and offers to resume interrupted sessions.
