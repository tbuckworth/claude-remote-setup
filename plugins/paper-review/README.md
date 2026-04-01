# Paper Review Plugin for Claude Code

Interactive paper review workflow with reMarkable annotation extraction, Bloom's taxonomy quizzing, SM-2 spaced repetition, and GitHub Issues integration.

**What you'll get:** Three slash commands in Claude Code that turn paper reading into active learning — quiz yourself with Bloom's taxonomy questions, track your retention with spaced repetition, and build a searchable review database over time.

## What It Does

| Command | Purpose | Time |
|---------|---------|------|
| `/paper-review [name-or-URL]` | Full 5-stage review: extract annotations from reMarkable, quiz on the paper (Bloom's taxonomy), resolve citations, create action items as GitHub issues, update spaced repetition, commit to git | ~20 min |
| `/sr-review` | Standalone spaced repetition session. Reviews papers due today using targeted questions on weak areas, updates SM-2 scheduling | 5-15 min |
| `/web2pdf <url>` | Convert a web article to clean PDF and send to reMarkable | ~30 sec |

The 5 stages of `/paper-review`:

1. **Understanding** (~5 min) — Your reMarkable highlights grouped by theme, handwritten notes transcribed, Feynman technique on 2 key concepts
2. **Quiz** (~8 min) — 6 free-response questions across Bloom's taxonomy (Remember → Create), with carry-forward feedback
3. **Wrap Up** (~3 min) — Resolve top citations, create GitHub issues for action items, write review markdown, compute SM-2 score, archive on reMarkable, git commit
4. **Spaced Repetition** (5-15 min) — Review previously studied papers due today, targeted questions on weak areas
5. **Plan Tomorrow** (~1 min) — Suggest next paper based on citation overlap and queue age

---

## Setup Guide (Start Here)

This guide assumes you have a **MacBook** and optionally a **reMarkable tablet**. Total setup time: ~15 minutes.

### Step 0: Install Claude Code

Claude Code is a CLI tool that runs in your terminal. Install it with npm:

```bash
# Install Node.js if you don't have it
brew install node

# Install Claude Code globally
npm install -g @anthropic-ai/claude-code
```

Verify it works:
```bash
claude --version
```

### Step 1: Authenticate Claude Code

You have two options — both work identically for plugins, skills, and all features.

#### Option A: Claude Max Subscription ($100-200/month, fixed)

If you have a Claude Max subscription at [claude.ai](https://claude.ai):

```bash
claude
# First launch opens your browser — log in with your Claude account
# That's it. Credentials are stored securely in macOS Keychain.
```

This is the simplest option if you already pay for Claude. Your subscription covers all Claude Code usage including plugins.

#### Option B: Anthropic API Key (pay-per-use)

If you'd rather pay per token instead of a monthly subscription:

1. Create an account at [console.anthropic.com](https://console.anthropic.com)
2. Go to **API Keys** → **Create Key** — copy the key (starts with `sk-ant-api03-`)
3. Go to **Billing** → **Add credits** (minimum $5 — this will last many sessions)
4. Set the key in your shell:

```bash
# Add to your shell profile so it persists across sessions
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

That's it — Claude Code detects the API key automatically. No browser login needed.

> **Heads up:** If you have both a subscription AND an API key set, the API key takes precedence and you'll be billed per-token instead of using your subscription. To switch back: `unset ANTHROPIC_API_KEY`.

**Verify authentication works:**
```bash
claude auth status
```

**Rough costs per session (API key):**

| Command | Opus cost | Sonnet cost |
|---------|-----------|-------------|
| `/paper-review` (full 5-stage) | ~$1-2 | ~$0.20-0.40 |
| `/sr-review` (3 papers) | ~$0.60-1.20 | ~$0.10-0.20 |
| `/web2pdf` | ~$0.10 | ~$0.02 |

The plugin defaults to Opus (best feedback quality). To use Sonnet instead, see [Changing the model](#changing-the-model).

### Step 2: Install the Plugin

The plugin is distributed via a custom marketplace backed by a GitHub repo.

```bash
# Clone the plugin repository
git clone https://github.com/tbuckworth/claude-remote-setup.git ~/claude-remote-setup

# Register it as a Claude Code marketplace
claude plugin marketplace add ~/claude-remote-setup

# Install the paper-review plugin
claude plugin install paper-review@custom-plugins
```

To update later:
```bash
cd ~/claude-remote-setup && git pull
claude plugin marketplace update custom-plugins
claude plugin update paper-review@custom-plugins
```

### Step 3: Create Your Data Repo

The plugin stores reviews, paper metadata, and spaced repetition state in a **separate git repo**. This keeps your review history versioned independently.

```bash
mkdir -p ~/paper-review/{reviews,papers}
cd ~/paper-review
git init

# Create the database file
cat > database.json << 'EOF'
{
  "version": 1,
  "papers": []
}
EOF

# Create the project CLAUDE.md (tells Claude about this repo's conventions)
cat > CLAUDE.md << 'CLAUDEEOF'
# Paper Review Data Repo

This repo stores paper reviews, metadata, and the spaced repetition database.

## Structure

- `reviews/` — Markdown review files (`YYYY-MM-DD-paper-slug.md`)
- `papers/` — Downloaded PDFs and extracted data (gitignored)
- `database.json` — Paper database with metadata, quiz results, and spaced repetition scheduling

## Conventions

- Paper slugs are lowercase-hyphenated titles (e.g., `ai-control-improving-safety`)
- Each review file contains: highlights, quiz results, key insights, and action items
- `database.json` is the source of truth for spaced repetition state

## SM-2 Spaced Repetition Fields (per paper in database.json)

- `easiness_factor` (float, default 2.5) — SM-2 EF, minimum 1.3
- `interval_days` (int, default 0) — current interval between reviews
- `repetition_number` (int, default 0) — consecutive successful reviews
- `quality_history` (array of int) — SM-2 quality scores (0-5) from each review session
- `next_review` (ISO date) — computed from last review + interval_days
CLAUDEEOF

# Gitignore large binary files
cat > .gitignore << 'EOF'
papers/**/*.pdf
papers/**/*.zip
papers/**/*.rm
papers/**/*.png
papers/**/*.rmdoc
papers/**/*.content
papers/**/*.metadata
papers/**/*.pagedata
.DS_Store
__pycache__/
*.pyc
.current-review-state.json
.claude/
node_modules/
EOF

touch reviews/.gitkeep
git add -A
git commit -m "Initial paper-review data repo"
```

Optionally push to GitHub:
```bash
gh repo create paper-review --private --source=. --push
```

### Step 4: Configure Paths (Required)

The plugin has hardcoded paths that must be updated to point to your data repo.

```bash
# Get your absolute data repo path
DATA_REPO="$HOME/paper-review"

# Find the installed plugin directory
PLUGIN_DIR="$HOME/.claude/plugins/cache/custom-plugins/paper-review"
# It'll be under a version subdirectory — find it:
PLUGIN_DIR=$(ls -d "$PLUGIN_DIR"/*/  | head -1)
echo "Plugin at: $PLUGIN_DIR"

# Replace all path references
sed -i '' "s|/Users/titus/pyg/paper-review|$DATA_REPO|g" \
  "${PLUGIN_DIR}CLAUDE.md" \
  "${PLUGIN_DIR}commands/paper-review.md" \
  "${PLUGIN_DIR}commands/sr-review.md"

echo "Updated paths in 3 files"
```

**Verify** — this should return nothing (no remaining references to the old path):
```bash
grep -r "titus" "${PLUGIN_DIR}commands/" "${PLUGIN_DIR}CLAUDE.md" || echo "All paths updated!"
```

### Step 5: Install Dependencies

#### uv (Python script runner) — required

The plugin runs Python scripts using [uv](https://docs.astral.sh/uv/), which auto-manages Python 3.12 and per-script dependencies. No virtualenvs to create.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc  # or restart your terminal
uv --version     # verify
```

#### Google Chrome — required for /web2pdf

The `/web2pdf` command uses headless Chrome to render PDFs. If Chrome is installed at the default macOS location (`/Applications/Google Chrome.app`), it's detected automatically. If you have Chromium or Chrome elsewhere, edit `scripts/web2pdf.py` line ~20.

#### gh (GitHub CLI) — optional, for action items

```bash
brew install gh
gh auth login  # follow the browser auth flow
```

The plugin creates GitHub issues for action items extracted from papers. If you skip this, everything else still works.

If you install `gh`, create a repo for your tasks:
```bash
gh repo create tasks --private
```

Then in `commands/paper-review.md`, find `tbuckworth/tasks` and replace with `yourusername/tasks`.

#### rmapi (reMarkable Cloud API) — optional but recommended

[rmapi](https://github.com/ddvk/rmapi) lets the plugin download your annotated documents from reMarkable Cloud and upload new PDFs.

**Install:**
```bash
# Option 1: Via Go
brew install go
go install github.com/ddvk/rmapi@latest
echo 'export PATH="$HOME/go/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Option 2: Pre-built binary (Apple Silicon)
mkdir -p ~/go/bin
curl -L "https://github.com/ddvk/rmapi/releases/latest/download/rmapi-macos-aarch64.zip" -o /tmp/rmapi.zip
unzip /tmp/rmapi.zip -d ~/go/bin/
chmod +x ~/go/bin/rmapi
echo 'export PATH="$HOME/go/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**Authenticate with reMarkable Cloud:**
```bash
rmapi
```

First run will:
1. Print a one-time code
2. Tell you to visit [my.remarkable.com/device/desktop/connect](https://my.remarkable.com/device/desktop/connect)
3. Enter the code there
4. Credentials saved to `~/.config/rmapi/rmapi.conf` — you won't need to do this again

Test it:
```bash
rmapi ls /
```

**Set up reMarkable folders:**
```bash
rmapi mkdir "To Quiz"     # Put papers here when ready to review
rmapi mkdir "Archive"     # Reviewed papers get moved here automatically
```

The plugin looks for papers in `To Quiz` by default. You can customize the folder names in `commands/paper-review.md` (search for `"To Quiz"`).

#### rmapi-mv (move workaround) — recommended if using rmapi

`rmapi mv` is broken due to a sync protocol issue. The plugin uses a workaround script called `rmapi-mv` that does download → re-upload → delete instead. This is used to archive papers after review.

Create the script:
```bash
mkdir -p ~/bin
cat > ~/bin/rmapi-mv << 'SCRIPT'
#!/bin/bash
# rmapi-mv: Move a document on reMarkable cloud via get+put+rm
# Workaround for rmapi mv being broken (sync:fox protocol issue)
# Usage: rmapi-mv "Source/Folder/Document Name" "Dest/Folder"
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: rmapi-mv \"Source/Path/DocName\" \"Dest/Folder\"" >&2
    exit 1
fi

SRC="$1"
DEST="$2"
DOC_NAME="$(basename "$SRC")"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# Download
echo "Downloading: $SRC"
cd "$TMPDIR"
rmapi get "$SRC" >/dev/null

# Extract PDF from rmdoc
RMDOC="$(ls *.rmdoc 2>/dev/null || true)"
if [ -z "$RMDOC" ]; then
    echo "Error: no .rmdoc file downloaded" >&2
    exit 1
fi
unzip -q "$RMDOC" "*.pdf" -d .
PDF="$(ls *.pdf 2>/dev/null | head -1)"
if [ -z "$PDF" ]; then
    echo "Error: no PDF found in rmdoc" >&2
    exit 1
fi
mv "$PDF" "${DOC_NAME}.pdf"

# Upload to destination
echo "Uploading to: $DEST"
rmapi put "${DOC_NAME}.pdf" "$DEST/" >/dev/null

# Delete original
echo "Deleting original: $SRC"
rmapi rm "$SRC" >/dev/null

echo "Moved: $DOC_NAME -> $DEST"
SCRIPT
chmod +x ~/bin/rmapi-mv

# Add ~/bin to PATH if not already there
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

> **Note:** This workaround loses annotations on the moved copy (it re-uploads just the PDF). That's fine for archiving already-reviewed papers since the annotations have already been extracted.

> **No reMarkable?** That's fine — you can review papers from URLs directly. Use `/paper-review https://arxiv.org/abs/2412.04984` and the plugin works with web content (skipping annotation extraction and archiving).

### Step 6: Verify Everything Works

```bash
# Start Claude Code in your data repo directory
cd ~/paper-review
claude

# Try a URL-based review (doesn't need rmapi):
/paper-review https://arxiv.org/abs/2412.04984
```

This should:
1. Fetch the paper content
2. Quiz you with 6 Bloom's taxonomy questions
3. Resolve citations
4. Ask for action items
5. Write a review to `reviews/`
6. Update `database.json` with SM-2 state
7. Git commit

If you have rmapi set up, also try:
```bash
# List what's on your reMarkable
/paper-review
# Should show documents in your "To Quiz" folder
```

---

## Usage

### Review a Paper from reMarkable

```
# Shows available documents on your reMarkable
/paper-review

# Specific document by name
/paper-review Sleeper Agents
```

**Workflow:** Read and annotate the paper on your reMarkable first — highlight key passages, write margin notes, mark questions with "?". Then run `/paper-review` — the plugin extracts your annotations, groups highlights by theme, transcribes handwritten notes, and uses all of this to generate targeted quiz questions.

### Review a Paper from a URL

```
# arXiv paper
/paper-review https://arxiv.org/abs/2412.04984

# Blog post or web article
/paper-review https://www.anthropic.com/research/alignment-faking
```

No reMarkable needed — the plugin fetches the web content directly.

### Run a Spaced Repetition Session

```
# Review all papers due today (SM-2 priority queue)
/sr-review

# Review a specific paper (even if not due)
/sr-review sleeper-agents
```

Run this regularly (daily or every few days) to maintain retention. The priority queue surfaces the most urgent papers first.

### Send a Web Article to reMarkable

```
/web2pdf https://www.lesswrong.com/posts/interesting-article
```

Extracts article content using Mozilla Readability, renders a clean PDF (14pt Georgia, tight margins, no ads), and uploads to your reMarkable.

---

## How the Spaced Repetition Works

The plugin uses the [SM-2 algorithm](https://en.wikipedia.org/wiki/SuperMemo#SM-2_algorithm) to schedule reviews:

| Your Quiz Score | SM-2 Quality | What Happens |
|----------------|--------------|-------------|
| 90-100% | 5 (perfect) | Interval grows: 1d → 6d → 6d × EF → ... |
| 70-89% | 4 (good) | Interval grows, EF decreases slightly |
| 50-69% | 3 (pass) | Interval grows, EF decreases more |
| 30-49% | 2 (fail) | Reset to 1-day interval, start over |
| 10-29% | 1 (bad fail) | Reset to 1-day interval |
| 0-9% | 0 (blackout) | Reset to 1-day interval |

**Easiness Factor (EF)** starts at 2.5 and adjusts each review. Higher EF = longer intervals. Minimum 1.3.

**Example progression** (scoring ~80% each time): review → 1 day → review → 6 days → review → 15 days → review → 37 days → ...

---

## Customization

### Changing the Model

The plugin defaults to `claude-opus-4-6` (best quality feedback and questions). To use a cheaper/faster model, edit the frontmatter in the command files:

```bash
PLUGIN_DIR=$(ls -d "$HOME/.claude/plugins/cache/custom-plugins/paper-review"/*/  | head -1)

# Change from Opus to Sonnet in both command files:
sed -i '' 's/model: claude-opus-4-6/model: claude-sonnet-4-6/g' \
  "${PLUGIN_DIR}commands/paper-review.md" \
  "${PLUGIN_DIR}commands/sr-review.md"
```

Sonnet is ~10x cheaper than Opus and still generates good quiz questions, though Opus gives richer corrective feedback.

### Changing reMarkable Folders

Search for `"To Quiz"` in `commands/paper-review.md` and replace with your preferred folder name. The plugin also references an `"Archive"` folder — change that too if needed.

### Disabling GitHub Issues

If you don't want action item tracking, you don't need to change anything — just say "no action items" when prompted during Stage 3.

---

## Data Model

### database.json

Each paper entry:

```json
{
  "id": "paper-slug",
  "title": "Paper Title",
  "authors": ["Author 1"],
  "url": "https://arxiv.org/abs/...",
  "arxiv_id": "2412.04984",
  "type": "paper",
  "status": "reviewed",
  "date_added": "2026-03-12",
  "date_read": "2026-03-12",
  "summary": "One-paragraph summary",
  "key_insights": ["Insight 1", "Insight 2"],
  "tags": ["alignment", "scheming"],
  "quiz_results": {
    "total_asked": 6,
    "total_correct": 4,
    "by_level": {
      "remember": [1, 1],
      "understand": [1, 0.5],
      "apply": [1, 1],
      "analyze": [1, 0.5],
      "evaluate": [1, 1],
      "create": [1, 0]
    }
  },
  "review_dates": ["2026-03-12"],
  "easiness_factor": 2.5,
  "interval_days": 1,
  "repetition_number": 1,
  "quality_history": [4],
  "next_review": "2026-03-13",
  "review_file": "reviews/2026-03-12-paper-slug.md",
  "remarkable_path": "To Quiz/Paper Title",
  "linked_papers": [
    {"id": "other-paper", "relationship": "cites"}
  ]
}
```

### Review files

Markdown files in `reviews/YYYY-MM-DD-<slug>.md` with: key highlights grouped by theme, Bloom's taxonomy quiz results, questions & answers, follow-up reading, and action items.

---

## File Structure

```
plugin/                              # Installed by Claude Code (~/.claude/plugins/cache/...)
  .claude-plugin/plugin.json         # Plugin manifest
  CLAUDE.md                          # Plugin architecture (read by Claude)
  README.md                          # This file
  commands/
    paper-review.md                  # Main 5-stage review command
    sr-review.md                     # Standalone SR session command
    web2pdf.md                       # Web-to-PDF command
  scripts/
    extract_annotations.py           # Parse reMarkable .rm files → JSON
    extract_citations.py             # Extract references from PDF
    resolve_citation.py              # Look up citation metadata (Semantic Scholar)
    sr_priority.py                   # Compute SM-2 priority queue
    web2pdf.py                       # Web article → clean PDF
  skills/
    learning-science/
      SKILL.md                       # Learning science techniques reference
      references/
        blooms-taxonomy.md           # Question stem templates per Bloom's level

~/paper-review/                      # Your data repo (created in Step 3)
  database.json                      # Paper database + SM-2 state (source of truth)
  CLAUDE.md                          # Data repo conventions
  reviews/                           # Markdown review summaries (git-tracked)
    2026-03-12-paper-slug.md
  papers/                            # Downloaded PDFs + extracted data (gitignored)
    paper-slug/
      *.pdf
      annotations.json
```

---

## Troubleshooting

### "rmapi: command not found"

Your PATH doesn't include the rmapi binary:
```bash
echo 'export PATH="$HOME/go/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### rmapi authentication expired

```bash
rmapi
# Follow the one-time code flow at my.remarkable.com again
```

### "uv: command not found"

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc
```

### Plugin not showing up after install

Restart Claude Code — plugin changes require a fresh session:
```bash
# Ctrl+C to exit, then:
claude
```

### Errors mentioning `/Users/titus/...`

You missed the path replacement in Step 4. Re-run:
```bash
DATA_REPO="$HOME/paper-review"
PLUGIN_DIR=$(ls -d "$HOME/.claude/plugins/cache/custom-plugins/paper-review"/*/  | head -1)
sed -i '' "s|/Users/titus/pyg/paper-review|$DATA_REPO|g" \
  "${PLUGIN_DIR}CLAUDE.md" \
  "${PLUGIN_DIR}commands/paper-review.md" \
  "${PLUGIN_DIR}commands/sr-review.md"
```

### "gh: command not found" during wrap-up

GitHub CLI is optional. The review still completes — just skip action items or install `gh`:
```bash
brew install gh && gh auth login
```

### Chrome not found (for /web2pdf)

The script looks for Chrome at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. If it's elsewhere, edit `scripts/web2pdf.py` line ~20.

### Plugin update overwrites my path config

Yes — `claude plugin update` replaces files with fresh copies. After updating, re-run the sed command from Step 4.

### rmapi mv doesn't work / "sync:fox protocol" error

This is a known rmapi bug. Use the `rmapi-mv` script instead (see Step 5). The plugin already uses `rmapi-mv` for archiving.

---

## Updating the Plugin

```bash
cd ~/claude-remote-setup && git pull
claude plugin marketplace update custom-plugins
claude plugin update paper-review@custom-plugins

# Re-apply your path configuration (update overwrites installed files)
DATA_REPO="$HOME/paper-review"
PLUGIN_DIR=$(ls -d "$HOME/.claude/plugins/cache/custom-plugins/paper-review"/*/  | head -1)
sed -i '' "s|/Users/titus/pyg/paper-review|$DATA_REPO|g" \
  "${PLUGIN_DIR}CLAUDE.md" \
  "${PLUGIN_DIR}commands/paper-review.md" \
  "${PLUGIN_DIR}commands/sr-review.md"
```

Also update `tbuckworth/tasks` → `yourusername/tasks` if you use GitHub issues.
