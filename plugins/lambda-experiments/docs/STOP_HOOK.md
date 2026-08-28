# Why there is no Stop hook

The original one blocked session exit when a Lambda GPU instance was thought to be running. It was
removed on 2026-08-28. Three separate reasons, and the third is the one that matters.

## It never blocked anything

It printed `{"ok": true}` or `{"ok": false, "reason": ...}`. Claude Code reads
`{"decision": "approve"|"block", "reason": ...}` for a Stop hook — `ok` is not a field it knows, so
the output was parsed as "no decision" and the session ended either way. Anyone relying on it to
catch a forgotten H100 was unprotected the whole time.

## It did not check Lambda

It grepped `state/active.md` — a markdown file inside the plugin's *install directory* — for a
`current_phase:` line. So it reported on a note someone had left, not on what was running. That file
had drifted: it described an "ArenaHardWriting Hints Test" with `ip: (pending)` and no
`current_phase:` line at all, which meant the hook took the "nothing running" path unconditionally.
A plugin cache directory is also the wrong place for mutable state — it is replaced on update.

## Blocking is the wrong verb anyway

This is the reason not to simply fix the two bugs above.

Instances outlive sessions, and several sessions run at once against **different Lambda accounts**.
"An instance exists" therefore does not mean "you left something running" — it may be another
session's live experiment, on a key this session does not hold. A hook that blocks on it stops
session A finishing because of session B's legitimate work, and a Stop hook that fires wrongly is a
Stop hook people switch off.

There is also no way for one session to enumerate every account: the API is per-key, and a hook can
only see keys it has.

## What would work

Inform, do not block, and make ownership visible.

1. **Attribute at launch.** `POST instance-operations/launch` takes a `name`. Name every instance
   for the session that created it (`ahw-hints-$CLAUDE_CODE_SESSION_ID` or similar). Ownership then
   lives on the instance, where every session can read it, instead of in a local file only one
   session can see.

2. **Read the API, per key.** `GET https://cloud.lambdalabs.com/api/v1/instances` with
   `curl -u "$LAMBDA_API_KEY:"` is the only source of truth. Iterate whatever keys the environment
   provides; report accounts it cannot see as unknown rather than as empty.

3. **Report, with cost.** On Stop, print the running instances, their names, and the hourly burn —
   `2 instances, ~$7.56/hr, 1 named for this session`. Advisory output belongs in `systemMessage`,
   not `decision: block`.

4. **Fail open, always.** A network call on every session end will sometimes time out. Any failure
   must `exit 0` and print nothing. A hook exiting non-zero produces
   `Stop hook error: Failed with non-blocking status code`, which is noise that trains people to
   ignore hook output — and was already happening with the old hook.

5. **Consider SessionEnd instead.** Stop fires whenever the assistant finishes a turn, which for a
   long agentic session is very often. `SessionEnd` fires once, which is where a cost warning
   actually belongs.

Blocking is only defensible for the narrow case of an instance **this session launched and named**,
still running, with no other session claiming it — and even then a loud advisory is probably better.
