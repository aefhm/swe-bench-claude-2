# SWE-bench Pro — A2A Green Agent

An A2A assessment system for evaluating coding agents on [SWE-bench Pro](https://www.swebench.com/) — 731 real-world software engineering tasks extracted from GitHub issues.

Both agents live in this monorepo for development convenience. They will be split into separate repos once the eval pipeline stabilizes — the green agent becomes the published leaderboard assessment, and the purple agent becomes a standalone participant that others can fork or replace.

The Amber docker-gateway framework was tested in [swe-bench-claude](https://github.com/aefhm/swe-bench-claude) but has not been ported to this repo yet. This repo uses plain Docker Compose and GitHub Actions instead.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentBeats Platform                            │
│                    (or local docker compose)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  agentbeats-client ──────> Green Agent (evaluator)                  │
│         ▲                    │           │                           │
│         │ results            │ A2A       │ DooD                      │
│         │                    ▼           │ (put_archive/get_archive) │
│         │              Purple Agent      │                           │
│         │              (A2A wrapper      │                           │
│         │               around           │                           │
│         │               mini-swe-agent)  │                           │
│         │                    │ DooD      │                           │
│         │                    ▼           ▼                           │
│         │              ┌──────────────────────────┐                 │
│         │              │    Host Docker Daemon      │                 │
│         │              │  SWE-bench containers     │                 │
│         │              └──────────────────────────┘                 │
│         └───────────────────────────────────────────                │
└─────────────────────────────────────────────────────────────────────┘
```

The purple agent is an A2A wrapper around [mini-swe-agent](https://github.com/SWE-bench/mini-swe-agent), which does the actual coding work inside a SWE-bench Docker container. Both agents use DooD to launch SWE-bench containers as siblings on the host Docker daemon. The green agent uses `put_archive`/`get_archive` (not volume mounts, which don't work in DooD) to transfer patches and scripts into eval containers.

**Note on Docker access:** The purple agent needs Docker socket access to launch SWE-bench containers for the coding agent to work in. At least one model (tested on throw away code in swe-bench-claude) showed degraded performance when the coding agent was not given its own Docker container to operate in.

## Data

Single file: `leaderboard/data/instances.jsonl` — 731 lines, 29 MB. Each line is a self-contained JSON object with instance metadata, gold patch, run script, and parsing script inlined.

Instance selection in `scenario.toml` uses human-friendly `short_id` values (e.g., `ansible-001`, `qutebrowser-042`). Set `instances = []` to run all 731.

```
leaderboard/
├── scenario.toml          ─── real eval (model, instances, API keys)
├── scenario.ci.toml       ─── CI gold-patch smoke test (USE_GOLD_PATCHES=true)
├── data/
│   └── instances.jsonl    ─── full SWE-bench Pro dataset
└── generate_compose.py    ─── scenario.toml → docker-compose.yml
```

## Project Structure

```
swe-bench-claude-2/
├── packages/
│   ├── green-agent/           # Evaluator
│   │   ├── src/
│   │   │   ├── server.py      # A2A server + agent card
│   │   │   ├── agent.py       # Eval orchestration
│   │   │   ├── evaluator.py   # Docker-based test runner (DooD)
│   │   │   ├── executor.py    # A2A request handler
│   │   │   └── messenger.py   # A2A client for green→purple
│   │   ├── amber-manifest.json5
│   │   └── Dockerfile
│   │
│   └── purple-agent/          # Coding agent (participant)
│       ├── src/
│       │   ├── server.py      # A2A server + agent card
│       │   ├── agent.py       # Problem solver (mini-swe-agent or gold patches)
│       │   ├── executor.py    # A2A request handler
│       │   └── messenger.py   # A2A client utilities
│       ├── amber-manifest.json5
│       └── Dockerfile
│
├── leaderboard/               # Config + data (see above)
│
├── .github/workflows/
│   ├── ci.yml                 # Build → gold-patch test → push to GHCR
│   └── real-eval.yml          # Batched matrix eval (see Parallelization)
│
├── test_e2e.sh                # Local e2e test (starts both agents natively)
├── test_e2e_client.py         # A2A test client
└── pyproject.toml             # uv workspace root
```

## Running

### Local (native)

```bash
./test_e2e.sh --gold          # Gold-patch pipeline test (no LLM)
./test_e2e.sh --model gpt-4o  # Real eval with an LLM
```

### Docker Compose

```bash
cd leaderboard
python generate_compose.py --scenario scenario.toml
cp .env.example .env  # fill in API keys
mkdir -p output
docker compose up --exit-code-from agentbeats-client
```

To test a single instance: set `instances = ["ansible-001"]` in `scenario.toml`.

### GitHub Actions

Two workflows, chained via `workflow_run`:

**CI** (`ci.yml`) — on push/PR: build images → gold-patch smoke test via `scenario.ci.toml` → push to GHCR.

**Real Eval** (`real-eval.yml`) — after CI succeeds on main: pull images from GHCR → batched matrix eval using `scenario.toml` → aggregate results artifact. Requires `ANTHROPIC_API_KEY` repo secret.

## Parallelization

The real-eval workflow uses a **batched matrix** strategy to run all 731 instances across GitHub Actions runners.

```
setup job
  │  parse scenario.toml → 731 instances → chunk into batches of 37
  │  output: [batch-000, batch-001, ..., batch-019]
  ▼
eval jobs (matrix over batches, up to 20 concurrent)
  ┌─────────────────┐  ┌─────────────────┐       ┌─────────────────┐
  │ batch-000        │  │ batch-001        │  ...  │ batch-019        │
  │ 37 instances     │  │ 37 instances     │       │ 5 instances      │
  │ sequential loop  │  │ sequential loop  │       │ sequential loop  │
  └────────┬─────── ┘  └────────┬────────┘       └────────┬────────┘
           │                     │                          │
           ▼                     ▼                          ▼
       artifact:             artifact:                  artifact:
       eval-batch-000        eval-batch-001             eval-batch-019
                    \            |                      /
                     ▼           ▼                     ▼
                   summary job (aggregate all results)
                     → eval-aggregate artifact
```

Each eval job loops through its batch sequentially: override `scenario.toml` to single instance → `docker compose up` → collect results → `docker compose down` → next. Images are pulled once per job and cached.

**GitHub free-tier constraints:**

| Constraint | Limit | Our usage |
|---|---|---|
| Max matrix jobs per workflow | 256 | 20 (batches of 37) |
| Concurrent jobs (public repo) | 20 | 20 — single wave |
| Max job duration | 6 hours | ~3-5 hours per batch |

At 5-8 min/instance, full 731 run completes in **~3-5 hours** wall clock in a single wave (all 20 jobs concurrent, no queuing).

**Tuning:** `BATCH_SIZE` in the setup job (`real-eval.yml`) controls the tradeoff. Current value of 37 fills exactly 20 jobs, saturating all concurrent slots without exceeding the 256 matrix limit.

**API rate limits:** 20 concurrent jobs making LLM calls requires Anthropic API Tier 2+ (1,000 req/min). Tier 1 will throttle.

## Docker Images

```
ghcr.io/aefhm/swe-bench-claude-2/green-agent:latest
ghcr.io/aefhm/swe-bench-claude-2/purple-agent:latest
```

Built from repo root (uv workspace). No data baked in — `instances.jsonl` is mounted at runtime.
