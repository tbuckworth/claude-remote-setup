# Lambda GPU Cost Reference

## Instance Pricing (as of March 2026)

| Instance Type | GPUs | Hourly Rate | 8h Cost | 12h Cost | 24h Cost |
|---|---|---|---|---|---|
| gpu_8x_h100_sxm5 | 8x H100 | ~$19.92/hr | $159 | $239 | $478 |
| gpu_8x_a100_80gb_sxm4 | 8x A100 80GB | ~$14.32/hr | $115 | $172 | $344 |
| gpu_1x_h100_sxm5 | 1x H100 | ~$3.78/hr | $30 | $45 | $91 |
| gpu_1x_a100_80gb_sxm4 | 1x A100 80GB | ~$2.21/hr | $18 | $27 | $53 |
| gpu_1x_a10 | 1x A10 | ~$0.75/hr | $6 | $9 | $18 |

Note: Prices may change. Check https://lambdalabs.com/pricing for current rates.

## Typical Experiment Costs

| Experiment Type | Instance | Duration | Estimated Cost |
|---|---|---|---|
| PTB sweep (24 experiments, react) | 8xH100 | 6-10h | $120-200 |
| PTB sweep (48 experiments, all tasks) | 8xH100 | 12-20h | $240-400 |
| PTB sweep (claude_code scaffold) | 8xH100 | 12-20h | $240-400 |
| LoRA training (2 tasks, 6h each) | 1xH100 | 12-16h | $45-61 |
| Elicitation sweep (200 experiments) | 8xH100 | 20-24h | $400-478 |
| Quick test (1-2 experiments) | 1xA10 | 1-2h | $1-2 |

## Cost-Benefit Decision Framework

### "Is this worth debugging?"
- Instance sitting idle at $20/hr = $0.33/min
- If a setup issue takes >15 min to debug = $5+ wasted on idle GPU
- Alternative: terminate ($0 ongoing), fix locally, re-launch
- Rule of thumb: if fix isn't obvious in 5 minutes, consider re-launch

### "Should we terminate and retry?"
- Sunk cost of partial run: (hours_elapsed * hourly_rate)
- Remaining cost: (estimated_remaining_hours * hourly_rate)
- If partial results are usable (>50% experiments complete): collect first, then decide
- If no usable results: terminate immediately to stop cost bleed

### "Is this API call worth worrying about?"
- Single Anthropic API call (Opus): ~$0.10-0.50
- Single monitoring SSH check: ~$0.001 (negligible)
- Running process_sweep.py locally: $0 (no GPU needed)
- Context: 1 minute of GPU idle time costs more than 10 monitoring checks

### "Are we using GPUs efficiently?"
- 8 GPUs at 95% utilization: optimal
- 8 GPUs at 50% utilization: check for bottleneck (CPU, disk, network)
- 8 GPUs at 0%: experiments finished or crashed -- investigate immediately
- 1 GPU busy, 7 idle: experiments launching too slowly or queue stuck

## Persistent Filesystem Storage
- Lambda filesystems: ~$0.20/GB/month
- Not a significant cost factor for experiment runs
