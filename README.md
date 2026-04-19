# openclaw-config

A self-hosted, Docker-based template for orchestrating social-media promotion of
your technical blog posts via [OpenClaw](https://openclaw.ai) and a Discord bot.

You write a markdown blog post. You DM the bot the file. The bot drafts:

- An **X / Twitter** post (returned for manual posting).
- A **LinkedIn** post (returned for manual posting).
- A **Medium** cross-post (returned as markdown).
- A **Reddit** self-post (with subreddit recommendations from a configurable
  allowlist; framed as a value-first discussion, not a link drop).
- A **short-form video script** (hook + beats + on-screen cues) suitable for
  screen-capture + TTS, plus an optional ElevenLabs voiceover render.
- Optionally, a **pull request against your blog repo** containing the
  markdown file ready to merge and deploy.

All inference runs on a private LLM behind a [RunPod
serverless](https://www.runpod.io/serverless-gpu) endpoint (Qwen, Gemma, or any
OpenAI-compatible model). Remote management runs over [Tailscale](https://tailscale.com).

This repo is a **generic template** — fork it, fill in `.env`, and run.

## What's in the box

```
.
├── docker-compose.yml          # tailscale, openclaw, mcp services
├── .env.example                # all configurable values
├── openclaw/
│   └── openclaw.json5          # OpenClaw gateway config (channels, agent, MCP)
├── mcp/
│   ├── Dockerfile              # python:3.12-slim + uv
│   ├── pyproject.toml
│   └── server.py               # FastMCP server with the social-drafting tools
└── docs/
    └── SETUP.md                # fresh-Ubuntu install walkthrough
```

## Architecture

```
Discord (your phone)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  Optiplex / Ubuntu 24.04                             │
│                                                      │
│  ┌──────────────┐                                    │
│  │  tailscale   │  ◄── you reach the Control UI      │
│  │  (sidecar)   │       at http://<tsname>:18789     │
│  └──────┬───────┘                                    │
│         │ shared netns                               │
│  ┌──────┴───────┐    ┌──────────────────┐            │
│  │  openclaw    │───▶│  mcp (Python)    │──┐         │
│  │  (Node)      │    │  social tools    │  │         │
│  └──────┬───────┘    └─────────┬────────┘  │         │
└─────────┼──────────────────────┼───────────┼─────────┘
          │                      │           │
          ▼                      ▼           ▼
       Discord              RunPod LLM   GitHub /
       Gateway              (OpenAI-      ElevenLabs
                            compatible)
```

The three containers share the Tailscale container's network namespace, so
the OpenClaw Control UI is reachable on your tailnet (`http://<hostname>:18789`)
without exposing anything to the public internet. The MCP server is reachable
by OpenClaw at `http://localhost:8000` inside that shared namespace.

## Quick start

1. `cp .env.example .env` and fill in the values.
2. `docker compose up -d`
3. Open `http://<tailscale-hostname>:18789` to verify the Gateway is up.
4. DM your Discord bot to pair it (OpenClaw replies with a code, paste it back).
5. DM the bot a `.md` file attachment. It will reply with drafts for each
   channel, and ask before opening the blog PR.

Detailed walkthrough: [docs/SETUP.md](docs/SETUP.md).

## Hardware

Tested on a Dell Optiplex 7070 (i5-9500T, 8 GB RAM, Ubuntu 24.04 LTS). Works on
any machine that can run Docker — the LLM is offloaded to RunPod, so local
resources are minimal (~1 GB RAM total across the three containers).

## Customizing

Everything brand-specific is in `.env`. Prompt templates live in `mcp/server.py`
and reference `BRAND_NAME`, `BRAND_URL`, and `BRAND_VOICE` env vars — edit those
to fit your voice.

## License

MIT.
