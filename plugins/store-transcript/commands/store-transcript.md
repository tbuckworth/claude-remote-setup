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

2. Run the script, passing the reason as a single quoted argument:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/store_transcript.py "<reason>"
```

   The script does everything itself: locates this session's live transcript, reads the
   session's working directory out of it, collects that repo's commit hash / branch /
   remote, copies the transcript and writes `log.md`, then commits on a `store/<session-id>`
   branch, pushes, opens a PR and squash-merges it.

3. Report back concisely: the session ID, the destination path, the source repo commit,
   and the PR URL the script printed.

## Notes

- The transcript is a snapshot taken mid-session, so it will not contain the turns that
  come after the archive runs. That is expected.
- Do not read the transcript's contents or paste them into your reply — these files are
  large and may contain sensitive material. Only copy the file.
- The script creates the archive repo (private) and the local git repo if they do not
  exist yet, so a fresh machine works with no setup.
- Useful flags when the defaults are wrong: `--session-id <id>` to archive a *different*
  session, `--agent claude|codex` to override auto-detection, `--archive <path>` and
  `--repo-slug <owner/name>` for a different archive, `--no-pr` to commit locally only.
- Re-running for the same session overwrites that session's directory with a fresh
  snapshot; if nothing changed the script reports that and exits without a PR.
