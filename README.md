# SWE-bench Pro — A2A Green Agent

An [Agent-to-Agent (A2A)](https://github.com/google/A2A) assessment system for evaluating coding agents on [SWE-bench Pro](https://www.swebench.com/) — real-world software engineering tasks extracted from GitHub issues.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentBeats Platform                            │
│                    (or local docker compose)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐                                               │
│  │  agentbeats-      │                                               │
│  │  client           │  eval request (config from scenario.toml)     │
│  │  (orchestrator)   │ ─────────────────────┐                        │
│  └──────────────────┘                       │                        │
│         ▲                                   ▼                        │
│         │ results              ┌──────────────────────┐              │
│         │ (accuracy,           │                      │              │
│         │  details)            │    Green Agent        │              │
│         │                      │    (evaluator)        │              │
│         │                      │    port 9009          │              │
│         └──────────────────── │                      │              │
│                                └───────┬──────┬───────┘              │
│                            A2A/JSON-RPC│      │DooD                  │
│                          ┌─────────────┘      │(put_archive/         │
│                          ▼                    │ get_archive)         │
│               ┌──────────────────────┐        │                      │
│               │                      │        │                      │
│               │  Purple Agent        │        │                      │
│               │  (coding agent)      │        │                      │
│               │  port 9009           │        │                      │
│               │                      │        │                      │
│               └──────────┬───────────┘        │                      │
│                          │ DooD               │                      │
│                          ▼                    ▼                      │
│               ┌──────────────────────────────────────────────────┐   │
│               │                Host Docker Daemon                 │   │
│               │                                                   │   │
│               │  ┌─────────────────────┐  ┌────────────────────┐  │   │
│               │  │ SWE-bench container  │  │ SWE-bench container│  │   │
│               │  │ (purple: solve issue)│  │ (green: run tests) │  │   │
│               │  └─────────────────────┘  └────────────────────┘  │   │
│               └──────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Evaluation Flow

```
agentbeats-client                Green Agent                 Purple Agent
      │                              │                            │
      │  eval request (config)       │                            │
      │ ──────────────────────────> │                            │
      │                              │                            │
      │                              │  problem_statement +       │
      │                              │  docker_image + commit     │
      │                              │ ────────────────────────> │
      │                              │                            │
      │                              │                            │── launch SWE-bench
      │                              │                            │   container (DooD)
      │                              │                            │── solve issue
      │                              │                            │   (LLM or gold patch)
      │                              │                            │
      │                              │  git diff patch            │
      │                              │ <──────────────────────── │
      │                              │                            │
      │                              │── create eval container
      │                              │   (SWE-bench image)
      │                              │── put_archive: patch +
      │                              │   run_script into container
      │                              │── run tests
      │                              │── get_archive: results
      │                              │── compare FAIL_TO_PASS
      │                              │   and PASS_TO_PASS
      │                              │
      │  results (accuracy, details) │                            │
      │ <────────────────────────── │                            │
      │                              │                            │
```

### Data Flow

```
leaderboard/
├── scenario.toml          ─── source of truth for real eval runs
│   ├── model config           (model name, API key refs)
│   ├── instance selection     (max_instances, instance_ids)
│   └── agent images           (GHCR refs)
│
├── scenario.ci.toml       ─── CI gold-patch smoke test
│   └── USE_GOLD_PATCHES=true  (no LLM, no API keys)
│
├── data/                  ─── dataset (mounted into agents at runtime)
│   ├── instances.json         task definitions, docker images, test lists
│   ├── gold_patches.json      known-good patches for pipeline testing
│   └── run_scripts/           per-instance test harness scripts
│       └── {instance_id}/
│           ├── run_script.sh
│           └── parser.py
│
└── generate_compose.py    ─── scenario.toml → docker-compose.yml
```

## Project Structure

```
swe-bench-claude-2/
├── packages/
│   ├── green-agent/           # Evaluator agent (pure eval engine)
│   │   ├── src/
│   │   │   ├── server.py      # A2A server + agent card
│   │   │   ├── agent.py       # Eval orchestration logic
│   │   │   ├── evaluator.py   # Docker-based test runner (DooD)
│   │   │   ├── executor.py    # A2A request handler
│   │   │   └── messenger.py   # A2A client for green→purple
│   │   ├── amber-manifest.json5
│   │   └── Dockerfile         # No data baked in
│   │
│   └── purple-agent/          # Coding agent (participant)
│       ├── src/
│       │   ├── server.py      # A2A server + agent card
│       │   ├── agent.py       # Problem solver (mini-swe-agent or gold patches)
│       │   ├── executor.py    # A2A request handler
│       │   └── messenger.py   # A2A client utilities
│       ├── amber-manifest.json5
│       └── Dockerfile         # No data baked in
│
├── leaderboard/
│   ├── scenario.toml          # Real eval config (model, instances, API keys)
│   ├── scenario.ci.toml       # CI gold-patch config
│   ├── scenario.json5         # Amber manifest (for quick-submit path)
│   ├── data/                  # Dataset (mounted into agents at runtime)
│   │   ├── instances.json
│   │   ├── gold_patches.json
│   │   └── run_scripts/
│   ├── generate_compose.py    # scenario.toml → docker-compose.yml
│   └── record_provenance.py   # Captures image digests for reproducibility
│
├── .github/workflows/
│   ├── ci.yml                 # Build → gold-patch test → push to GHCR
│   └── real-eval.yml          # Real LLM eval (runs after CI succeeds on main)
│
├── test_e2e.sh                # Local e2e test (starts both agents natively)
├── test_e2e_client.py         # A2A test client
└── pyproject.toml             # uv workspace root
```

## Deployment Paths

### 1. Local Testing

Run both agents natively with `uv`:

```bash
./test_e2e.sh --gold          # Gold-patch pipeline test (no LLM needed)
./test_e2e.sh --model gpt-4o  # Real eval with an LLM
```

### 2. Docker Compose (scenario.toml)

The standard AgentBeats leaderboard flow:

```bash
cd leaderboard
pip install tomli tomli-w pyyaml requests
python generate_compose.py --scenario scenario.toml
cp .env.example .env  # fill in API keys
mkdir -p output
docker compose up --exit-code-from agentbeats-client
```

Both agents get `./data` mounted in and Docker socket access for DooD evaluation.

### 3. Amber Manifests (quick-submit)

For the AgentBeats quick-submit path using Amber:

```bash
# Compile scenario to docker-compose
docker run --rm -v "$(pwd):/work" \
  -e AMBER_DEV_IMAGE_TAGS="router=main,helper=main,provisioner=main,docker_gateway=main" \
  ghcr.io/rdi-foundation/amber-cli:main \
  compile /work/leaderboard/scenario.json5 --compose /work/amber-generated

# Run
cd amber-generated && docker compose up -d
```

Amber provides encrypted mesh networking between agents, a Docker socket gateway, and OpenTelemetry observability.

### 4. GitHub Actions

Two workflows, chained:

**CI** (`ci.yml`) — triggers on push to main and PRs:
- Builds both Docker images
- Runs gold-patch smoke test via `scenario.ci.toml`
- Pushes images to GHCR on success

**Real Eval** (`real-eval.yml`) — triggers after CI succeeds on main:
- Pulls freshly built images from GHCR
- Runs real LLM eval using `scenario.toml` config
- Uploads results as GitHub Actions artifact
- Requires `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) as repo secret

## Key Design Decisions

**Dataset decoupled from images:** Instance data, gold patches, and test scripts live in `leaderboard/data/` and are mounted into agent containers at runtime. Changing the task set doesn't require an image rebuild. All run config (model, instance selection, max count) comes from `scenario.toml`.

**Docker-outside-of-Docker (DooD):** Both agents launch sibling containers on the host Docker daemon. Volume mounts don't work in DooD (paths resolve on the host, not inside the container), so the green agent uses `put_archive`/`get_archive` to transfer files into evaluation containers.

**A2A Protocol:** Both agents expose `/.well-known/agent-card.json` and communicate via JSON-RPC. The green agent discovers the purple agent's URL either from the eval request body (`participants.coding_agent`) or from the `CODING_AGENT_URL` environment variable (set by Amber slot bindings).

**Port 9009:** Both agents default to port 9009, matching the AgentBeats convention. In Docker Compose, each container has its own network namespace so there's no port conflict.

**Root user in containers:** Both agents run as root to access the Docker socket. The Amber docker-gateway proxy also requires root to bind `/var/run/docker.sock`.

## Docker Images

```
ghcr.io/aefhm/swe-bench-claude-2/green-agent:latest
ghcr.io/aefhm/swe-bench-claude-2/purple-agent:latest
```

Both images are built from the repo root (for uv workspace support) using `--frozen` to avoid lockfile mismatch in partial workspace copies. No data is baked in — mount `leaderboard/data/` at runtime.
