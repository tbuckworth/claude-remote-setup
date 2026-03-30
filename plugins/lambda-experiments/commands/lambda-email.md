---
description: Send HTML email summary of a Lambda experiment run
argument-hint: [optional path to state file, defaults to ~/.claude/lambda-experiments/active.md]
allowed-tools: [Read, Glob, Bash, Grep, mcp__gmail__send_email, mcp__claude_ai_Gmail__gmail_get_profile]
model: claude-sonnet-4-6
---

# Lambda Experiment Email Summary

Compose and send a comprehensive HTML email summarizing a Lambda GPU experiment run.

## Data Sources

1. **State file**: `{{argument}}` (default: `~/.claude/lambda-experiments/active.md`)
   - YAML frontmatter with all experiment metadata
   - Read and parse the frontmatter fields

2. **Results**: If `local_results_path` is set in state, extract experiment results:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-eval-results.py "$LOCAL_RESULTS_PATH"
   ```
   This outputs JSON with per-experiment scores from .eval files.

3. **Incident report**: `~/.claude/lambda-experiments/incident_report.md` (if exists)
4. **New findings**: `~/.claude/lambda-experiments/new_findings.md` (if exists)
5. **State file body** (markdown below YAML frontmatter): contains status notes, issues, handling

## Instructions

1. **Get recipient email**: Use `mcp__claude_ai_Gmail__gmail_get_profile` to get the authenticated user's email. Send ONLY to this address.

2. **Read all data sources** listed above. Parse the YAML frontmatter from the state file.

3. **Determine termination status**:
   - `current_phase: done` AND `terminated_at` is set → terminated normally
   - Otherwise → NOT TERMINATED (requires warning banner)

4. **Calculate cost**:
   - If `final_cost_usd` is set, use it
   - Otherwise: `hours_elapsed × hourly_rate` (compute hours from `launched_at` to now)

5. **Compose the email** as described below.

6. **Send** via `mcp__gmail__send_email` with:
   - `to`: authenticated user's email
   - `subject`: as specified below
   - `body`: plain text fallback
   - `htmlBody`: the HTML version
   - `mimeType`: `"multipart/alternative"`

7. If sending fails, write HTML to `~/.claude/lambda-experiments/email-draft.html` as fallback.

---

## Subject Line

```
[Lambda] <experiment_name> — $<cost> — ✅ Completed (<N> experiments)
[Lambda] <experiment_name> — $<cost> — ⚠️ NOT TERMINATED
[Lambda] <experiment_name> — $<cost> — ❌ Failed
```

## HTML Template

ALL styles must be inline (Gmail strips `<style>` blocks). Use this structure:

```html
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 700px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">

  <!-- Header -->
  <div style="background: #f0f4f8; border-left: 4px solid #2563eb; padding: 16px 20px; margin-bottom: 24px;">
    <h1 style="margin: 0 0 8px 0; font-size: 20px; color: #1e293b;">
      Lambda Experiment Report
    </h1>
    <div style="font-size: 14px; color: #64748b;">
      <experiment_name> · <date> · <status_badge>
    </div>
  </div>

  <!-- ⚠️ WARNING BANNER — only if NOT terminated -->
  <!-- Show this ONLY if current_phase is not "done" or terminated_at is not set -->
  <div style="background: #fef2f2; border: 2px solid #ef4444; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
    <h2 style="margin: 0 0 8px 0; font-size: 16px; color: #991b1b;">⚠️ Instance NOT Terminated</h2>
    <p style="font-size: 14px; color: #991b1b; margin: 0;">
      Instance <strong><instance_id></strong> (<instance_type>) is still running at <ip>.
      Current cost: ~$<cost> and counting at $<hourly_rate>/hr.
    </p>
    <p style="font-size: 14px; margin: 8px 0 0 0;">
      <a href="https://cloud.lambdalabs.com/instances" style="color: #dc2626; font-weight: 600;">
        → Go to Lambda Dashboard to check/terminate
      </a>
    </p>
  </div>

  <!-- Summary Box -->
  <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
    <h2 style="margin: 0 0 12px 0; font-size: 16px; color: #1e293b;">Summary</h2>
    <table style="border-collapse: collapse; width: 100%; font-size: 14px;">
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top; width: 130px;">Instance</td>
        <td style="padding: 4px 0;"><instance_type> · <region></td>
      </tr>
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top;">Duration</td>
        <td style="padding: 4px 0;"><launched_at> → <terminated_at or "still running"> (<hours>h)</td>
      </tr>
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top;">Total Cost</td>
        <td style="padding: 4px 0; font-weight: 600;">$<final_cost></td>
      </tr>
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top;">Experiments</td>
        <td style="padding: 4px 0;"><completed> completed, <failed> failed</td>
      </tr>
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top;">Branch</td>
        <td style="padding: 4px 0;"><code style="background: #f1f5f9; padding: 2px 6px; border-radius: 3px; font-size: 13px;"><branch></code></td>
      </tr>
      <tr>
        <td style="padding: 4px 12px 4px 0; color: #64748b; white-space: nowrap; vertical-align: top;">Termination</td>
        <td style="padding: 4px 0;">
          <!-- Green badge if terminated, red if not -->
          <span style="background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">TERMINATED</span>
          <!-- or -->
          <span style="background: #fef2f2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">RUNNING</span>
          (<termination_mode> mode)
        </td>
      </tr>
    </table>
  </div>

  <!-- Results Table — only if results were collected -->
  <h2 style="font-size: 16px; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">Experiment Results</h2>

  <!-- If no results available, say so briefly -->
  <!-- If results exist, show this table: -->
  <table style="border-collapse: collapse; width: 100%; font-size: 14px; margin-bottom: 24px;">
    <thead>
      <tr style="background: #f8fafc;">
        <th style="text-align: left; padding: 8px 12px; border-bottom: 2px solid #e2e8f0;">Experiment</th>
        <th style="text-align: left; padding: 8px 12px; border-bottom: 2px solid #e2e8f0;">Main Score</th>
        <th style="text-align: left; padding: 8px 12px; border-bottom: 2px solid #e2e8f0; width: 140px;"><!-- bar --></th>
        <th style="text-align: left; padding: 8px 12px; border-bottom: 2px solid #e2e8f0;">Status</th>
      </tr>
    </thead>
    <tbody>
      <!-- One row per .eval file from the extract script output -->
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9;">
          <!-- Experiment name: use setting + main_task or the eval filename stem.
               Make it human-readable, e.g. "honest / gsm8k" not "honest_1gpu_local_gsm8k_..." -->
        </td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-family: 'Courier New', monospace;">
          <!-- posttrain_main_scorer value, e.g. "0.307" -->
        </td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9;">
          <!-- Inline bar chart: -->
          <div style="background: #e2e8f0; border-radius: 3px; height: 16px; overflow: hidden;">
            <div style="background: #22c55e; height: 100%; width: XX%; border-radius: 3px;"></div>
            <!-- width = score × 100%. Use #22c55e (green) for score > 0.5, #f59e0b (amber) for 0.2-0.5, #ef4444 (red) for < 0.2 -->
          </div>
        </td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9;">
          <span style="background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">SUCCESS</span>
          <!-- or -->
          <span style="background: #fef2f2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">ERROR</span>
        </td>
      </tr>
    </tbody>
  </table>

  <!-- Side Scores — if posttrain_multi_side_scorer data exists, show a smaller table -->
  <!-- Only include this if experiments have side task scores -->
  <h3 style="font-size: 14px; color: #475569; margin-bottom: 8px;">Side Task Scores</h3>
  <table style="border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 24px;">
    <thead>
      <tr style="background: #f8fafc;">
        <th style="text-align: left; padding: 6px 10px; border-bottom: 1px solid #e2e8f0;">Experiment</th>
        <th style="text-align: left; padding: 6px 10px; border-bottom: 1px solid #e2e8f0;">Side Score (mean)</th>
      </tr>
    </thead>
    <tbody>
      <!-- posttrain_multi_side_scorer values -->
    </tbody>
  </table>

  <!-- Issues & Handling — only if incident_report.md or new_findings.md exist -->
  <div style="margin-bottom: 24px;">
    <h2 style="font-size: 16px; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">Issues Encountered</h2>
    <!-- If no issues: "No issues during this run." -->
    <!-- If issues exist, list each one: -->
    <table style="border-collapse: collapse; width: 100%; font-size: 14px;">
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; color: #64748b; width: 100px;">Issue</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9;"><!-- brief description --></td>
      </tr>
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; color: #64748b;">Resolution</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9;">
          <span style="background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">AUTO-FIXED</span>
          <!-- or -->
          <span style="background: #fef9c4; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">MANUAL</span>
          <!-- or -->
          <span style="background: #fef2f2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">UNRESOLVED</span>
          <!-- brief description of fix -->
        </td>
      </tr>
    </table>
  </div>

  <!-- Cost Breakdown -->
  <div style="margin-bottom: 24px;">
    <h2 style="font-size: 16px; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">Cost Breakdown</h2>
    <table style="border-collapse: collapse; font-size: 14px;">
      <tr>
        <td style="padding: 4px 16px 4px 0; color: #64748b;">Instance type</td>
        <td style="padding: 4px 0;"><instance_type></td>
      </tr>
      <tr>
        <td style="padding: 4px 16px 4px 0; color: #64748b;">Hourly rate</td>
        <td style="padding: 4px 0;">$<hourly_rate>/hr</td>
      </tr>
      <tr>
        <td style="padding: 4px 16px 4px 0; color: #64748b;">Total hours</td>
        <td style="padding: 4px 0;"><hours>h</td>
      </tr>
      <tr style="font-weight: 600;">
        <td style="padding: 8px 16px 4px 0; border-top: 2px solid #e2e8f0;">Total cost</td>
        <td style="padding: 8px 0 4px 0; border-top: 2px solid #e2e8f0;">$<final_cost></td>
      </tr>
    </table>
  </div>

  <!-- Links -->
  <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
    <h2 style="margin: 0 0 12px 0; font-size: 16px; color: #1e293b;">Links</h2>
    <ul style="list-style: none; padding: 0; margin: 0; font-size: 14px;">
      <li style="margin-bottom: 6px;">
        <a href="https://cloud.lambdalabs.com/instances" style="color: #2563eb;">Lambda Dashboard</a> — view/manage instances
      </li>
      <!-- If local_results_path is set: -->
      <li style="margin-bottom: 6px;">
        Results: <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 3px; font-size: 13px;"><local_results_path></code>
      </li>
    </ul>
  </div>

  <!-- Footer -->
  <div style="font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 12px;">
    Generated by Lambda Experiment Orchestrator · Claude Code
  </div>
</div>
```

## Formatting Rules

- ALL styles must be inline (Gmail strips `<style>` and `<link>` tags)
- Status badges: green (`#dcfce7` bg, `#166534` text) for success/terminated, red (`#fef2f2` bg, `#991b1b` text) for error/running, amber (`#fef9c4` bg, `#854d0e` text) for warnings
- Bar chart colors: green (`#22c55e`) for score > 0.5, amber (`#f59e0b`) for 0.2–0.5, red (`#ef4444`) for < 0.2
- Max width: 700px, centered
- Font: system stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`)
- Monospace for scores and paths: `'Courier New', Courier, monospace`
- Keep experiment names human-readable: "honest / gsm8k" not raw filenames
- Omit sections that have no data (e.g., no issues → skip Issues section, no results → note "Results not yet collected")
- The warning banner for non-termination should be impossible to miss

## Plain Text Fallback

Also provide a `body` field with a plain-text version covering:
- Status (terminated or WARNING)
- Instance details and cost
- Results summary (scores as text)
- Issues
- Lambda dashboard link
