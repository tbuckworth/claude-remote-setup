---
name: lambda-status
description: This skill should be used when the user asks "what's running on Lambda?", "Lambda status", "how are the experiments going?", "check on the instance", "are the experiments done?", "how much has it cost so far?", "is the GPU still running?", "experiment progress", or any request related to checking the status of running Lambda GPU experiments.
version: 0.1.0
---

# Lambda Experiment Status

When this skill is triggered, invoke `/lambda status` to check on any running Lambda GPU experiments.

Reports: current phase, experiments completed vs total, GPU utilization, hours elapsed, cost so far, any issues detected.
