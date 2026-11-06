# Porting later upstream fixes into the handover repo

The source keeps moving after the cut. Fixes that matter to the recipients have to cross the
cut, the renames and the per-folder rewrites without dragging in what the cut removed. Titus
decides which changes go in; the agent says what each would do to past results.

## Decide first: what each change would do

For every candidate upstream change, before porting anything:

- Could it change scores, in each kind of run (there: fixed-count runs, open-book runs, answer-key
  grading)? A change to what the agent sees, how long it may work, or how a judge reads a reply
  can.
- How many past episodes would it have touched? Count from the logs; do not guess (there: the
  "prose before JSON" fix changed 4 of 720 counted fixed-count episodes; 29 of 240 open-book
  episodes had hit the 12-hour limit that a timing change would affect).
- Offer Titus options in one mail, A/B/C with a default, each with its comparability cost
  (there: C would have broken comparability with 73 runs, about $13k to re-run). Changes that
  could alter results go last in the port, as separate commits that are easy to drop.
- Release notes for the recipients go in the PR body or the handover mail, never a README.

## Method A: the layout has changed (renames done)

Used for v1.1 of the Training Effects repo (6 Nov 2026), with `scripts/replay_upstream.py`.

1. A scratch clone of the handover repo that also holds the upstream commits (`fetch_from`, or
   a remote whose objects come through alternates on a local clone).
2. `base`: the handover repo's last commit in upstream layout (the minimal-tree commit, or the
   last commit before the first rename stage).
3. Replay each upstream PR's diff onto `base`, one commit per PR, in the order chosen above:
   only files the branch already has, plus upstream-added files you name in `add`; never what
   `exclude` names (docs, plans, archives, configs the cut removed). Resolve a conflict to that
   PR's own change, commit with the printed message, rerun: done PRs are skipped.
4. Merge that branch into a new branch off the current repo with `-X find-renames=40%`, so git
   carries each change through the renames (`[replay.merge]`).
5. A file reported `DU` (deleted by us) fell below the rename threshold, usually a small file
   whose rename changed most of its bytes: apply that PR's change to its new path by hand.
6. Move upstream-added files to their new paths and rename their vocabulary: a `staged_rename.py`
   stage whose `files` lists only them.
7. Phase 2 checks (staged sandboxes, scripted episodes, the suite), the tree audit, a review,
   and an end-to-end run if the change touches the run path (`e2e-checklist.md`).

## Method B: the layout is unchanged (no renames yet)

`examples/training-effects/sync_upstream.sh`: apply the upstream diff between the pin and the new
commit for the files the repo keeps with `git apply --reject`, list files upstream added under
kept directories for judgement, recompute the keep set at the new commit (what kept code now
needs that the tree lacks), regenerate lock-derived files if the lock changed, run the checks,
then move the pin.

## Afterwards

- Recompute the keep set at the new upstream commit (`closure.py` and `make_keep_set.py` with
  `[source].pin` moved) and compare it with the tree: kept code may now import or open a file the
  cut removed.
- Update the recorded pin and the audit's reasons; `check_tree.py` must pass again.
