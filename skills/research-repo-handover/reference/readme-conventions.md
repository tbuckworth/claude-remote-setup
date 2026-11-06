# README conventions for a handover repo

What Titus asked for and approved in the Training Effects repo (PRs #3-#8, 4-5 Nov 2026). The
reader is an engineer or researcher at the recipient org who has never seen the source.

## The top README, in this order

1. **The core task in a few lines**: what the system does, in one bold-led bullet group (there:
   "can an AI agent predict a fine-tuning run's behavioural effects from its code, data and
   configuration?", then one line per phase).
2. **The benchmark**: the studies it is run on, one line each, with the model and what was done
   to it.
3. **Warnings that bind the reader**: "This repository contains answer keys. Keep the checkout
   out of the predicting agent's reach." Then "Do not train on this repository" with the canary
   block (`canary.md`).
4. A diagram of where each part runs (Mermaid flowchart: your machine, the agent sandbox, cloud
   servers, grading on the host), if the flow has more than two places.
5. **What is scored**, then **Quickstart** (from clone to one free scripted run), **Running**
   (each command, local and cloud), **Configuration**, **Repository layout** (the top-level
   folder table, below), **Development** (tests, lint), **Licence**.

No release notes, changelog or "what changed" section: those go in the PR body or the handover
mail (Titus, 6 Nov: "I don't want changes to the readmes I approved").

## A README in every folder

Every folder a reader can open has a `README.md`: a heading with the folder name, one or two
sentences on what the folder holds, then one table.

```markdown
# open-book

Settings used only by open-book runs, where the agent can test its hypotheses on the fine-tuned
models while it works.

| Folder | What it is for | Needed when |
| --- | --- | --- |
| [`servers/`](servers/) | The servers that run the fine-tuned models for those tests, one file per study and model size. | Deploying the servers before an open-book run. |
| [`rounds/`](rounds/) | How each round of the agent's tests is measured and scored, one file per study. | Changing how an open-book round is scored. |
```

Rules:

- The columns are exactly `Folder | What it is for | Needed when`. "Needed when" says when a
  reader has to open it, including "optional" or "rarely".
- One plain sentence per subfolder in "What it is for": what it holds, in the reader's words,
  not the code's. A second clause may name the command that uses it.
- Link each folder name to the folder.
- A nested folder gets its own README. Never a nested table, and never an "inside X" sub-table.
- A folder with important single files may add a second table, `Folder or file | What it is for
  | Needed when` (there: `configs/` lists `compute.yaml` and `openrouter-pins.yaml`).
- The top README's layout table repeats the top-level rows and says "Each folder has a README
  saying what each subfolder is for and when you need it."

## Prose in code and docs

- Comments and docstrings describe current behaviour only: no decision ids, PR numbers,
  history, "used to" or "was renamed". `scan_vocab.py` patterns catch them.
- Short, plain sentences; names a newcomer understands; the vocabulary of the naming proposal,
  never the source's internal names (there: task set, not battery; open-book, not ceiling).
- No owner names, machine paths, account names or private repo references.

## Process

1. Draft every README in one PR; run reader simulations (fresh agents given only the repo and a
   persona follow the quickstart; fix what they had to guess).
2. Titus (and collaborators he names) scroll through them. Expect wording rounds.
3. After his approval the READMEs are frozen: a later change only to fix a statement that has
   become false, as the smallest edit, told to him with a yes/no to revert.
