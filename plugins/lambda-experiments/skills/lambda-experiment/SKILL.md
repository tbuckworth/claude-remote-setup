---
name: lambda-experiment
description: This skill should be used when the user asks to "run experiments on Lambda", "launch a Lambda instance", "start a PTB run", "run control arena on GPU", "start an 8-GPU run", "run a sweep on Lambda", "run experiments", "launch GPU instance", "start training on Lambda", "run elicitation sweep", "LoRA training on Lambda", or any request related to launching, running, or managing GPU experiments on Lambda Cloud instances for Control Arena.
version: 0.1.0
---

# Lambda Experiment Runner

When this skill is triggered, invoke the `/lambda` command with the user's natural language description as the argument.

The user describes what they want in plain language — they don't need to know which scripts exist or what flags to pass. The orchestrator figures out the right approach based on the request.

Examples:
- User: "Run attack/honest PTB experiments with qwen3-4b" → `/lambda Run attack/honest PTB experiments with qwen3-4b`
- User: "Train a LoRA adapter on GSM8K" → `/lambda Train a LoRA adapter on GSM8K`
- User: "Just get me a GPU instance" → `/lambda Just get me a GPU instance`
- User: "Check what's happening" → `/lambda status`
- User: "We're done, shut it down" → `/lambda terminate`

The plugin orchestrates the full lifecycle and encodes knowledge of Lambda failure patterns from 10+ previous runs.
