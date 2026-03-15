# SWE-bench Pro — A2A Green Agent

An [Agent-to-Agent (A2A)](https://github.com/google/A2A) assessment system for evaluating coding agents on [SWE-bench Pro](https://www.swebench.com/) — real-world software engineering tasks extracted from GitHub issues.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AgentBeats Platform                        │
│                    (or local docker compose)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    A2A/JSON-RPC     ┌──────────────────────┐  │
│  │              │ ──────────────────> │                      │  │
│  │  Green Agent │   problem statement │  Purple Agent        │  │
│  │  (evaluator) │ <────────────────── │  (coding agent)      │  │
│  │  port 9009   │     git diff patch  │  port 9009           │  │
│  │              │                     │                      │  │
│  └──────┬───────┘                     └──────────┬───────────┘  │
│         │                                        │              │
│         │ Docker-outside-of-Docker                │ DooD        │
│         │ (put_archive / get_archive)             │ (optional)  │
│         ▼                                        ▼              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Host Docker Daemon                      │   │
│  │                                                           │   │
│  │  ┌─────────────────────┐                                  │   │
│  │  │  SWE-bench container │  Created per-instance by green  │   │
│  │  │  (jefzda/sweap-*)    │  agent for test evaluation      │   │
│  │  └─────────────────────┘                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
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

## Project Structure

```
swe-bench-claude-2/
├── packages/
│   ├── green-agent/           # Evaluator agent
│   │   ├── src/
│   │   │   ├── server.py      # A2A server + agent card
│   │   │   ├── agent.py       # Eval orchestration logic
│   │   │   ├── evaluator.py   # Docker-based test runner (DooD)
│   │   │   ├── executor.py    # A2A request handler
│   │   │   └── messenger.py   # A2A client for green→purple
│   │   ├── data/              # Instance metadata (gitignored: run_scripts/)
│   │   ├── amber-manifest.json5
│   │   └── Dockerfile
│   │
│   └── purple-agent/          # Coding agent (participant)
│       ├── src/
│       │   ├── server.py      # A2A server + agent card
│       │   ├── agent.py       # Problem solver (mini-swe-agent or gold patches)
│       │   ├── executor.py    # A2A request handler
│       │   └── messenger.py   # A2A client utilities
│       ├── data/              # Gold patches for testing
│       ├── amber-manifest.json5
│       └── Dockerfile
│
├── leaderboard/
│   ├── scenario.toml          # Assessment config (agents + env + params)
│   ├── scenario.json5         # Amber manifest (for quick-submit path)
│   ├── generate_compose.py    # scenario.toml → docker-compose.yml
│   ├── record_provenance.py   # Captures image digests for reproducibility
│   ├── submissions/           # Submitted scenario configs + provenance
│   └── results/               # Assessment results JSON
│
├── .github/workflows/
│   ├── ci.yml                 # Build, gold-patch e2e test, push to GHCR
│   └── run-scenario.yml       # Full assessment via agentbeats-client
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
mkdir -p output
docker compose up --exit-code-from agentbeats-client
```

This generates a `docker-compose.yml` with both agents + the `agentbeats-client` orchestrator. The green agent gets Docker socket access (`/var/run/docker.sock`) and runs as root for DooD evaluation.

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

### 4. GitHub Actions CI

Push to `main` triggers `ci.yml`:

- Builds both Docker images
- Runs gold-patch e2e test in containers
- Pushes images to `ghcr.io/aefhm/swe-bench-claude-2/{green,purple}-agent:latest`

Push a change to `leaderboard/scenario.toml` triggers `run-scenario.yml`:

- Generates docker-compose from scenario.toml
- Runs full assessment via agentbeats-client
- Records provenance (image digests)
- Creates submission branch with results

## Key Design Decisions

**Docker-outside-of-Docker (DooD):** The green agent evaluates patches by launching sibling containers on the host Docker daemon. Volume mounts don't work in DooD (paths resolve on the host, not inside the container), so we use `put_archive`/`get_archive` to transfer files into evaluation containers.

**A2A Protocol:** Both agents expose `/.well-known/agent-card.json` and communicate via JSON-RPC. The green agent discovers the purple agent's URL either from the eval request body (`participants.coding_agent`) or from the `CODING_AGENT_URL` environment variable (set by Amber slot bindings).

**Port 9009:** Both agents default to port 9009, matching the AgentBeats convention. In Docker Compose, each container has its own network namespace so there's no port conflict.

**Root user in containers:** The green agent runs as root to access the Docker socket. The Amber docker-gateway proxy also requires root to bind `/var/run/docker.sock`.

## Docker Images

```
ghcr.io/aefhm/swe-bench-claude-2/green-agent:latest
ghcr.io/aefhm/swe-bench-claude-2/purple-agent:latest
```

Both images are built from the repo root (for uv workspace support) using `--frozen` to avoid lockfile mismatch in partial workspace copies.
