FROM ghcr.io/astral-sh/uv:python3.13-bookworm

# Install Docker CLI + git (mini-swe-agent launches SWE-bench containers as siblings)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list && \
    apt-get update && apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

RUN adduser agent
RUN groupadd -f docker && usermod -aG docker agent

# Run as root — the Amber docker-gateway proxy needs permission to bind
# /var/run/docker.sock, and DooD needs access to the host Docker socket.
WORKDIR /home/agent

# Copy workspace root files (uv workspace needs root pyproject + lockfile)
COPY --chown=agent pyproject.toml uv.lock ./

# Copy this package
COPY --chown=agent packages/purple-agent/pyproject.toml packages/purple-agent/
COPY --chown=agent packages/purple-agent/src packages/purple-agent/src
# Bake instance data into the image so it works with both Amber and local runs
COPY --chown=agent leaderboard/data packages/purple-agent/data

RUN \
    --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --frozen --package purple-agent

WORKDIR /home/agent/packages/purple-agent
ENTRYPOINT ["uv", "run", "--package", "purple-agent", "python", "src/server.py"]
CMD ["--host", "0.0.0.0", "--port", "9009"]
EXPOSE 9009
