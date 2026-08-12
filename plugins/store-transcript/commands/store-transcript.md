---
description: Archive this session's transcript into the private deception-transcripts repo with provenance, then PR and merge
argument-hint: "<why you are storing this transcript>"
allowed-tools: [Bash]
---

# Store this session's transcript

Archive the transcript of the session you are running in right now into the private
GitHub repo `tbuckworth/deception-transcripts`, together with a log recording why it was
stored and the git provenance of the repo the session was working in.

## Constants

- **Script**: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/store_transcript.py`
- **Archive repo**: `~/pyg/deception-transcripts` → `<your-github-user>/deception-transcripts` (private)
- **Layout**: `<archive>/<session-id>/<transcript>.jsonl` + `<archive>/<session-id>/log.md`

Override the destination with `STORE_TRANSCRIPT_ARCHIVE` (local path) and
`STORE_TRANSCRIPT_REPO` (`owner/repo`, or a bare name to use your own account).
A bare repo name resolves against the `gh` logged-in user, so the defaults work
on a fresh machine with no configuration.

## Workflow

1. Take `{{argument}}` as the reason. If it is empty, ask the user in one short question
   why they are storing this transcript, and use their answer. Do not invent a reason.

2. Run the script **in the background** (`run_in_background: true`), passing the reason as a
   single quoted argument:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/store_transcript.py "<reason>"
```

   Archiving takes tens of seconds and blocks nothing that the session needs. Backgrounding
   it keeps the session usable and keeps the script's output out of the conversation — carry
   on with whatever was being worked on rather than waiting.

   The script does everything itself: locates this session's live transcript, reads the
   session's working directory out of it, collects that repo's commit hash / branch /
   remote, **scrambles any secrets**, writes `log.md` and `scrub-audit.md`, then commits
   on a `store/<session-id>` branch, pushes, opens a PR and squash-merges it.

   Run it from the session's working directory, and **as a plain backgrounded Bash call, not
   inside a subagent**. The script identifies the live session from `CLAUDE_CODE_SESSION_ID`,
   falling back to the most recently modified transcript whose recorded `cwd` matches the
   current directory. A background Bash call inherits both, so it resolves correctly. A
   subagent buys nothing here — the script is fully self-contained, with nothing for an agent
   to decide — while adding a way for the wrong session or directory to be picked.

3. When it finishes, report it in **one line**: the session ID and the PR URL the script
   printed. If it failed, say what failed in one line. Nothing else — this is housekeeping
   that interrupted whatever was actually being worked on, so return to that.

## Scrubbing

Secrets are **scrambled, not redacted** — replaced with same-shaped fakes so the
transcript still reads as a real session to a model. `[REDACTED]` would be a tell.

- Substitution is deterministic (keyed HMAC), so one secret maps to one fake
  everywhere in the transcript, and a key exported early then used later stays
  consistent. Format is preserved: prefix, length, character class, hex-only bodies.
- Scrubbing runs **before the first commit** — a secret that reaches git history
  cannot be removed by a later commit.
- If any swept secret survives into the output, the run **aborts and writes nothing**.
  That is a scrubber bug; report it rather than working around it.
- `scrub-audit.md` records per-rule counts only, never values.
- The HMAC salt lives at `~/.config/store-transcript/salt` (mode 600), outside the
  archive repo. Override with `STORE_TRANSCRIPT_SALT_FILE`. Deleting it just means
  future runs produce different fakes.
- Tests: `python3 ${CLAUDE_PLUGIN_ROOT}/tests/test_scrub.py` plants known secrets and
  asserts all are caught. Run it after touching the rules.

Scrubbing covers credentials, not identity. Names, paths and repo contents are stored
as-is, and semantic identification survives regardless — so the archive repo should
stay private. Use `--no-scrub` only when you deliberately want a verbatim copy.

## Notes

- The transcript is a snapshot taken mid-session, so it will not contain the turns that
  come after the archive runs. That is expected. Because the script now runs in the
  background, the cut point is wherever the session had reached a few seconds after
  dispatch — slightly later than before, and not exactly predictable. Re-run it at the end
  if you need the tail of the session; re-running overwrites that session's directory with
  a fresh snapshot.
- Do not read the transcript's contents or paste them into your reply — these files are
  large and may contain sensitive material. Only copy the file.
- The script creates the archive repo (private) and the local git repo if they do not
  exist yet, so a fresh machine works with no setup.
- Useful flags when the defaults are wrong: `--session-id <id>` to archive a *different*
  session, `--agent claude|codex` to override auto-detection, `--archive <path>` and
  `--repo-slug <owner/name>` for a different archive, `--no-pr` to commit locally only.
- Re-running for the same session overwrites that session's directory with a fresh
  snapshot; if nothing changed the script reports that and exits without a PR.
