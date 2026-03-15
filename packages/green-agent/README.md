# SWE-bench Pro Green Agent

An A2A green agent that evaluates coding agents on the [SWE-bench Pro](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro) benchmark.

## How it works

1. Receives an evaluation request via A2A with a participant coding agent URL
2. Sends the participant a SWE-bench problem statement + Docker image info
3. The participant pulls the Docker image, works in the container, and sends back a patch
4. The green agent evaluates the patch by running the SWE-bench test harness in Docker
5. Returns structured pass/fail results

## Running locally

```bash
uv sync
uv run python src/server.py
```

## Testing

```bash
uv sync --extra test
uv run pytest --agent-url http://localhost:9009
```
