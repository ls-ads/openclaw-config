FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git gh \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY server.py ./

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

CMD ["uv", "run", "--no-sync", "python", "server.py"]
