# The real end-to-end run

One run of every shipped command on the real infrastructure, before handover and after any
change that touches the run path (a port, a rename). It is the only check that finds what the
free checks cannot: a cloud image that does not build, a credential the code expects under
another name, a command that compares unresolved paths. It costs money, so Titus approves the
spend first; cost it and say the number.

## Before

- [ ] Titus's yes for the spend, with the estimate (Training Effects: r5, every command with
      three H100 measurement pods and a 52-minute open-book run, about $35; a one-episode
      open-book check about $12).
- [ ] A fresh clone of the merged commit (or the branch under test), never the working checkout.
      Copy in only the local secrets profile and the data; nothing else from the old clone.
- [ ] A branch in that clone for the run's own config edits (fresh log dirs and run ids, the
      results dataset, the owner label, the measurement inputs). Commit before every launch:
      the run entry points refuse a dirty tree. Never commit while a cloud image is building
      from the checkout.
- [ ] Owner label set (`TE_MODAL_OWNER=handover` there) so names do not collide on a shared
      workspace; check the shared volume's capacity if it has an inode or size cap.
- [ ] The step wrapper: `examples/e2e-env.example.sh` and `examples/e2e-step.sh` (one log, a
      start stamp and an exit stamp per step, values read from files and never echoed).

## The steps (the v1.1 order, 6 Nov 2026)

| # | Group | Steps |
| --- | --- | --- |
| 1 | Free first | each scripted (mock) configuration locally: optimisers, organisms, open-book |
| 2 | Servers | severe-harm screen deploy; target server stage, deploy, check |
| 3 | Agents | a dry run then one real episode per study; one scripted episode on the cloud sandbox; one open-book episode with two rounds |
| 4 | Grading | answer-key grading by the real judges, per study |
| 5 | Measurement | per run: a dry run, then the measurement pod (copy `logs/<run>/hypotheses/` into the measurement inputs and commit first) |
| 6 | Results | import; hypotheses Markdown, JSON and HTML reports; the phase-1 Markdown report |
| 7 | Follow-ups | complete, consolidate, rescore, regrade (a regrade on a copy of a log) |
| 8 | Stop | every server; then the open-book run's measurement and reports; artifact push |

Some follow-up commands refuse by design on a fresh run (nothing to consolidate, a rescore with
nothing to change): read the one-line message before calling it a failure.

## Spend discipline

- [ ] Register every paid launch with cloud-watch straight after it starts
      (`cloud-watch launch --expect 6h --reason "e2e <step>" -- <command>`, or
      `cloud-watch register <provider:account:name> ...`).
- [ ] Deployed servers bill until stopped: stop each, then check `modal app list` (its JSON keys
      are lowercase) before ending the session.
- [ ] Close your cloud-watch records; disown resources the launch wrapper picked up that are not
      yours (there: another session's apps).

## What to check for each run: harness health, not scores

The predicting agent's score is the measurement, not a target: report it once, plainly. Check:

- status, and `scores_trustworthy`;
- every judge called (a null grade from one provider error needs a regrade, not a re-run);
- the declared tools are the expected ones (nothing removed reappeared, nothing new crept in);
- errors, refusals (read `stop_reason`), episodes cut by a time or message limit;
- for open-book runs: every round ran, and how long the agent waited;
- the agent's own feedback.

## After

- [ ] One mail to Titus: a table per step (exit, duration, cost), anything that misbehaved,
      the total cost, and that everything is stopped.
- [ ] Fix what the run found on a branch (Training Effects r5 found `benchmark consolidate`
      comparing unresolved paths); re-run only the affected steps.
