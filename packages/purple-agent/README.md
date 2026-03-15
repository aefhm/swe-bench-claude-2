# SWE-bench Pro Purple Agent

An A2A participant agent that solves SWE-bench Pro coding tasks using [mini-swe-agent](https://github.com/scaleapi/mini-swe-agent).

## How it works

1. Receives a problem statement + Docker image via A2A from a green agent
2. Pulls the SWE-bench Docker image and launches a container
3. Runs mini-swe-agent inside the container to solve the issue
4. Returns the git patch to the green agent

## Running locally

```bash
uv sync
uv run python src/server.py --port 9012
```

### Gold-patch mode (pipeline testing, no LLM needed)

```bash
uv run python src/server.py --port 9012 --use-gold-patches
```
