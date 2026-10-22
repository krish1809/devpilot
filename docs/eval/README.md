# DevPilot evaluation

Two evaluations live here:

| Report | What it measures |
|---|---|
| [phase6-rag.md](phase6-rag.md) | 5 hand-made multi-file repos: does retrieval help the agent find and fix the *root cause*? (smoke-level) |
| `phase7-<name>.md` | **SWE-bench Lite**: real GitHub issues from 12 Python projects, scored with the official SWE-bench harness |

## SWE-bench Lite (Phase 7)

### Method

- **Dataset:** [SWE-bench Lite](https://www.swebench.com/) test split (300 real issues; every
  reference patch edits a single file). DevPilot runs a **seeded random sample** (default
  20 instances, seed 7) — the sample, its seed, and all budget settings are stored with the
  run (`eval_runs.settings`) and printed in the report.
- **Agent setting (standard):** the agent gets only the issue text and the repository at the
  base commit. It **never sees the benchmark's tests**, so runs have no test command and the
  repair loop only re-tries edits that failed to apply. Each patch still passes the automated
  reviewer (single file, size cap, no conflict markers).
- **Scoring:** every patch is evaluated by the **official harness**
  (`swebench.harness.run_evaluation`, installed in `apps/api/.venv-swebench`) inside the
  instance's prebuilt Docker image. Resolved = all FAIL_TO_PASS and PASS_TO_PASS tests pass.
  The harness's own infra-failure classification (e.g. a test needing network the machine
  can't reach) is recorded and listed in the report; such cases count as **unresolved**.
- **Configs:**
  - `rag` — **the headline**: issue only; hybrid retrieval (pgvector + Postgres full-text)
    suggests files and code, the planner localizes the file.
  - `oracle-file` — the file the reference patch edits is given, no retrieval: isolates
    patch writing from localization (an upper bound for localization, not a realistic setting).
  - `oracle-file+rag` — oracle file plus retrieved cross-file context.
  - `gold` (optional, `score --with-gold`) — the reference patches themselves, to calibrate
    the environment: the best score achievable on this machine.
- **Versions:** `lite-s20-seed7-v1-nogate` is the first 6 instances with the agent *before* the
  Python syntax gate (patches that broke indentation were scored as failures without any test
  running); it is kept as an ablation. `lite-s20-seed7` is the headline run with the gate.
- **Unattended:** `run-all` loops generate → score → report, sleeping while the LLM's daily
  token quota (200k tokens/day on Groq's free tier) refills; the report is rewritten after each pass.
  It finishes only when every result is both generated **and** scored.
- **Uncertainty:** resolve rates are reported with a 95% Wilson interval. With n = 20 the
  interval is wide (±15–20 points); read differences between configs accordingly.

### Running it

```bash
cd apps/api && source .venv/bin/activate

# one-time: the official harness in its own virtualenv (heavy deps kept out of the API)
python -m venv .venv-swebench && .venv-swebench/bin/pip install swebench

# 1) generate patches (resumable; stops cleanly when the LLM's daily quota runs out)
python -m scripts.swebench_eval generate --name lite-s20-seed7 --n 20 --seed 7 \
    --owner you@example.com
# 2) score with the official harness (pulls each instance image, then deletes it)
python -m scripts.swebench_eval score --name lite-s20-seed7 [--with-gold]
# 3) write docs/eval/phase7-<name>.{md,json}
python -m scripts.swebench_eval report --name lite-s20-seed7
```

Results are also stored in Postgres (`eval_runs`, `eval_results`) and shown in the web app
under **Benchmarks** (`/evals`), including every patch.

### Scoring in GitHub Actions, and the unattended pipeline

Scoring needs room for each instance's Docker image — ~1–3 GB compressed on Docker Hub, roughly
3× that unpacked, up to ~9 GB for Matplotlib — more than a busy laptop can spare. So scoring can
run in CI instead, with the same harness version and the same command line
([`app/evals/harness_io.py`](../../apps/api/app/evals/harness_io.py) is shared by both sides):

```bash
# export every patch, push docs/eval/predictions/<name>.jsonl, dispatch the scoring workflow,
# wait for it, and import the verdicts
python -m scripts.swebench_eval ci-score --name lite-s20-seed7 --with-gold
```

[`.github/workflows/swebench-score.yml`](../../.github/workflows/swebench-score.yml) gives each
instance its own job (frees ~25 GB on the runner, installs `swebench==5.0.2`, runs
[`scripts/ci_score.py`](../../apps/api/scripts/ci_score.py), retrying harness errors) and merges
the verdicts into a `swebench-scores` artifact. Every reported verdict then comes from the same CI
environment; a CI harness error never overwrites a real verdict already on record. The
predictions file is committed, so anyone can see — and re-score — the exact patches behind the
numbers.

`pipeline` runs the whole thing unattended: generate (paced by the LLM's daily quota and the disk
guard, publishing the partial report and the README's progress line after each productive pass)
→ score in CI → publish the final report, the README numbers and the showcase data, which the
deployed API loads on its next start ([DEPLOY.md](../DEPLOY.md)). It publishes from a dedicated
clone (`~/.cache/devpilot/swebench/publish-repo`), never from the developer's checkout, and it
installs as a systemd user service so it survives the terminal that started it and resumes at
login after a reboot:

```bash
infra/systemd/install.sh --name lite-s20-seed7 --n 20 --seed 7 --owner you@example.com \
    --with-gold --ablation lite-s20-seed7-v1-nogate
tail -f ~/.cache/devpilot/swebench/pipeline.log      # progress
systemctl --user disable --now devpilot-benchmark    # stop
```

When it finishes it writes `~/.cache/devpilot/swebench/pipeline-<name>.done` and disables the
service.

### Constraints that shaped the setup

- **LLM:** Groq free tier, `openai/gpt-oss-120b` — 8,000 tokens/minute and 1,000
  requests/day. Every prompt is budgeted to fit (issue ≤ 4k chars, retrieved context ≤ 5k,
  large files shown as ≤ 5k-char excerpts and edited with SEARCH/REPLACE blocks); 429s are
  retried as the provider asks. Expect roughly 1–2 minutes per instance per config.
- **Embeddings on CPU** run at ~10–15 chunks/s, so repositories over 3,000 chunks are indexed
  lazily (text + full-text index up front, vectors only for keyword candidates at query time).
- **Disk (local scoring):** scoring removes each instance image after use, but Docker's
  containerd image store keeps the compressed layers next to the unpacked ones, so an image
  needs about 4× its Docker Hub size. Before each instance a guard in `app/evals/swebench.py`
  looks that size up and requires `max(6 GB, 4 × compressed + 1 GB)` free (12 GB if the lookup
  fails) on the tighter of the eval cache's and Docker's filesystems; generation requires 2 GB.
  Below that it stops cleanly instead of filling the disk (which would also take Postgres down),
  and `run-all`/`pipeline` sleep and retry. Scoring in CI sidesteps all of this.
- **Network:** some upstream test suites (e.g. `requests`) call real hosts; failures there are
  infra failures, not agent failures — the harness labels them.

### How to read the number

Report it as "DevPilot resolves X% (95% CI a–b%) of a seeded 20-instance sample of SWE-bench
Lite with a free-tier open-weight model" — a capability demonstration, not a leaderboard
claim. Leaderboard systems use far larger models, many more attempts, and the full 300.
