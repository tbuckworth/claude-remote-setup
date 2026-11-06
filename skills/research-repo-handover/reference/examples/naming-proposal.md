Keep `training_effects` as the core, with the two studies beside it at `src/benchmarks/`.

```text
training-effects-prediction/
├── src/                          # Core implementation and benchmark definitions.
│   ├── training_effects/         # Python package implementing the reusable core.
│   │   ├── prediction/           # Run predicting agents; grade reports and hypotheses.
│   │   ├── measurement/          # Test hypotheses on models and judge their responses.
│   │   ├── reporting/            # Combine grades and measurements into published outputs.
│   │   ├── sandbox/              # Stage agent inputs and prevent answer leakage.
│   │   ├── prompts/              # Versioned text read by agents and judges.
│   │   ├── training/             # Training execution and frozen vendored trainers.
│   │   ├── datasets/             # Download and verify training datasets.
│   │   └── infrastructure/       # Shared providers, remote jobs, storage and filesystem guards.
│   └── benchmarks/               # Study definitions and reference material.
│       ├── optimisers/           # Adam/Lion/Muon comparison on Qwen3-8B.
│       │   ├── task_sets/        # Episode variants and grading settings.
│       │   ├── training_setups/  # Fine-tuning recipes examined by the agent.
│       │   └── ground-truth/     # Optimiser answer keys; host only.
│       ├── organisms/            # Emergent-misalignment study on Qwen3-1.7B/4B.
│       │   ├── task_sets/        # Episode variants and grading settings.
│       │   ├── training_setups/  # Fine-tuning recipes examined by the agent.
│       │   └── ground-truth/     # Organism answer keys; host only.
│       └── shared/               # Dataset manifest and pinned training environment.
│           ├── reading/          # Papers and their index; selection remains task-specific.
│           ├── checkpoints/      # Tokenizers and chat templates, not model weights.
│           └── scoring/          # Reference examples for hypothesis judges.
├── configs/                      # Operator settings, kept outside source.
│   ├── agent-runs/               # Predictor, task set, execution location and shared defaults.
│   ├── measurements/             # Post-run hypothesis measurement jobs.
│   │   └── validation/           # Settings used by task checks; not runnable job examples.
│   ├── reports/                  # Inputs and destinations for generated reports.
│   ├── model-manifests/          # Pinned model/adapter inventories; not downloaded weights.
│   ├── severe-harm-screen/       # Screening policy settings and classifier server configuration.
│   ├── open-book/                # Testing while the predicting agent is running.
│   │   ├── servers/              # Deploy trained target models: hardware and capacity.
│   │   └── rounds/               # Sampling, judging and feedback shown after each round.
│   └── answer-key-grading/       # Check graders by submitting answer keys as reports.
├── deploy-scripts/               # GPU measurement job template and shell launch helpers.
├── tests/                        # Mirror core packages, plus integration and support.
└── .github/                      # CI workflows.
```

Keep root documentation, project metadata and lockfile. Keep `configs/compute.yaml` (prices) and `openrouter-pins.yaml` (provider routing). Generated `data/` (downloads), `logs/` (episodes) and `results/` (measurements) remain outside `src/`.

Moves preserve filenames recursively; the answer-key move overrides its parent. Unlisted paths stay unchanged. **P** means `src/training_effects`.

| Old path | New path | Reason |
|---|---|---|
| `benchmarks/` | `src/benchmarks/` | Put both halves under source. |
| `benchmarks/shared/ground-truth/` | `src/benchmarks/organisms/ground-truth/` | Correct study ownership. |
| `P/benchmark/` | `P/prediction/` | Remove collision with study benchmarks. |
| `P/evaluation/` | `P/measurement/` | Name the model-testing stage. |
| `tests/benchmark/` | `tests/prediction/` | Mirror implementation. |
| `tests/evaluation/` | `tests/measurement/` | Mirror implementation. |
| `configs/runs/` | `configs/agent-runs/` | Say what runs. |
| `configs/trained-models/` | `configs/model-manifests/` | Distinguish inventories from weights. |
| `configs/screen/` | `configs/severe-harm-screen/` | Explain the screen's purpose. |
| `configs/target-servers/` | `configs/open-book/servers/` | Group open-book deployment. |
| `configs/open-book-rounds/` | `configs/open-book/rounds/` | Separate round behaviour from deployment. |
| `deploy/` | `deploy-scripts/` | Identify operational launch files. |

Delete `P/evaluation/catalogue/`, including its lone `__init__.py`. Make an absent default catalogue return empty; preserve explicit-root discovery/errors. Both discovery functions currently call `iterdir()`.

The source split has these trade-offs:

- Keep the import package, CLI `training-effects`, all six command groups, and Inspect task names. Subpackage imports change; a package-wide rename adds unnecessary churn.
- `src/benchmarks/` remains checkout data, without `__init__.py`; retain the wheel's explicit `src/training_effects` package selection. A checkout remains required.
- Study folders own task sets, setups and answer keys; shared papers stay together. Model manifests remain operator-selectable configuration.
- Keep reporting: it joins grades with measurements and implements `report`. Keep infrastructure as support shared by prediction and measurement, and keep vendored trainers in place. This is a layout cleanup, not full architectural decoupling.

The README should open in seven lines:

1. Training Effects: predict behavioural changes from fine-tuning code, data and configuration.
2. An agent writes a report graded against answer keys, then proposes ten tests measured afterwards.
3. The reusable core lives in `src/training_effects/`.
4. The supplied benchmark comprises two studies in `src/benchmarks/`.
5. Optimisers: Adam, Lion and Muon on Qwen3-8B.
6. Organisms: emergent misalignment on Qwen3-1.7B and Qwen3-4B.
7. Open-book variants allow testing rounds; keep the checkout and answer keys outside the agent's reach.

`rg -n --hidden` estimates, excluding Git metadata, locks and environment files (**matching lines/files**, not exhaustive dependencies): package `benchmark` **638/143**, `evaluation` **201/68**; `benchmarks/` **170/98**; run configs **59/12**, model manifests **45/43**, screen **41/23**, deployment **26/16**. Keeping infrastructure avoids **359/149** references.

Update answer-key guards, setup discovery, remote source shipping, formatter exclusions and historical-path readers together; old logs must still resolve their keys without rewriting recorded identifiers. Adjust host lookup paths only. Preserve all task/setup/model/version IDs, sampling, prompt wording, paper filenames, answer-key bytes and vendor bytes. Keep “benchmark” and “evaluation” wherever model-visible text uses them.

Before accepting implementation, byte-compare staged trees at identical container paths and rendered judge requests across both studies and open-book variants. Path edits can alter generated briefs and provenance hashes despite untouched prompts; preserve frozen material. Run the full tests and style checks after migration.

