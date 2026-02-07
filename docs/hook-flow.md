# Plugin Hook Flow

How the 8 custom plugins interact with Claude Code's hook events.

```
                              Claude Code Session
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌──────────┐    ┌────────────┐    ┌──────────┐
              │PreToolUse│    │ PostToolUse│    │   Stop   │
              │Edit/Write│    │   (Bash)   │    │          │
              └────┬─────┘    └─────┬──────┘    └────┬─────┘
                   │                │                │
                   ▼                ▼                ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │ branch-guard │ │review-changes│ │ commit-often │
           │  (command)   │ │  (command)   │ │  (command)   │
           │ Blocks edits │ │ Reviews git  │ │ Warns about  │
           │ on main      │ │ commits      │ │ uncommitted  │
           └──────────────┘ └──────────────┘ └──────────────┘


              Plan Mode (EnterPlanMode → Plan agent → ExitPlanMode)
                                      │
                                      ▼
                              ┌───────────────┐
                              │ SubagentStop   │
                              │ matcher: Plan  │
                              └───────┬───────┘
                                      │
                    ┌─────────┬───────┴───────┬─────────┐
                    │         │               │         │
                    ▼         ▼               ▼         ▼
             ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
             │assumption │ │best-prac  │ │doc-cross  │ │pre-mortem │
             │-debugger  │ │-validator │ │-checker   │ │           │
             │ (prompt)  │ │ (prompt)  │ │ (prompt)  │ │ (prompt)  │
             │           │ │           │ │           │ │           │
             │ Questions │ │ Anti-     │ │ Deprecated│ │ Failure   │
             │ unstated  │ │ patterns, │ │ APIs,     │ │ modes,    │
             │assumptions│ │ security  │ │ incorrect │ │ risks,    │
             │           │ │ concerns  │ │ usage     │ │ mitigations│
             └───────────┘ └───────────┘ └───────────┘ └───────────┘
                    │         │               │         │
                    └─────────┴───────┬───────┴─────────┘
                                      │
                              All 4 run in parallel
                              Each returns {ok: true/false}
                              Any {ok: false} blocks the plan


              Manual Agents (user-invoked via Task tool)
              ┌───────────────────────────────────────────────────────┐
              │                                                       │
              │  assumption-debugger  - Socratic debugging            │
              │  best-practices-validator - Check against docs        │
              │  doc-cross-checker    - Verify library usage          │
              │  refactoring-radar    - Find refactoring opportunities│
              │  review-changes       - Review code changes           │
              │  pre-mortem           - Pre-mortem risk analysis      │
              │                                                       │
              └───────────────────────────────────────────────────────┘
```

## Plugin Summary

| Plugin | Agent | Hook Event | Hook Type |
|--------|:-----:|------------|-----------|
| assumption-debugger | Y | SubagentStop:Plan | prompt |
| best-practices-validator | Y | SubagentStop:Plan | prompt |
| branch-guard | - | PreToolUse:Edit/Write | command |
| commit-often | - | Stop | command |
| doc-cross-checker | Y | SubagentStop:Plan | prompt |
| pre-mortem | Y | SubagentStop:Plan | prompt |
| refactoring-radar | Y | - | - |
| review-changes | Y | PostToolUse:Bash | command |
