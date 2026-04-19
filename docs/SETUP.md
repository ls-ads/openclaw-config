# Setup walkthrough — fresh Ubuntu 24.04

End-to-end install on a clean Ubuntu desktop/server. ~30 minutes if you have
all the credentials handy.

## 0. Hardware / network

- Any x86_64 box with ≥ 4 GB RAM works (LLM is offloaded to RunPod).
- Tested on a Dell Optiplex 7070 (i5-9500T, 8 GB).
- The machine should be on a network with outbound internet. No inbound ports
  are required — Tailscale handles remote access.

## 1. Install Docker + Compose plugin

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
# log out and back in (or `newgrp docker`) so your user picks up group membership
```

Verify: `docker run --rm hello-world`.

## 2. Clone this repo

```bash
git clone https://github.com/<your-fork>/openclaw-config.git
cd openclaw-config
cp .env.example .env
```

Now open `.env` in an editor — every variable is documented inline. You'll
collect the credentials in the next steps.

## 3. Tailscale auth key

1. https://login.tailscale.com/admin/settings/keys
2. **Generate auth key** → reusable, ephemeral OFF, tags optional.
3. Paste into `.env`:
   ```
   TS_AUTHKEY=tskey-auth-...
   TS_HOSTNAME=openclaw   # appears as this name on your tailnet
   ```

## 4. Discord bot

1. https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy → `DISCORD_BOT_TOKEN` in `.env`.
3. **Bot** tab → enable **Message Content Intent**.
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`,
   permissions `Send Messages`, `Read Message History`, `Attach Files`. Open
   the generated URL in a browser and add the bot to a personal server (or
   leave it unattached — DMs work without a server).
5. In Discord (with Developer Mode on, Settings → Advanced), right-click your
   own username → **Copy User ID** → `DISCORD_OWNER_ID`.

## 5. RunPod serverless LLM

1. https://www.runpod.io/console/serverless → deploy a vLLM template with
   your chosen model (e.g. `Qwen/Qwen3-32B-Instruct`, `google/gemma-3-27b-it`).
2. Note the endpoint ID and your API key.
3. Fill `.env`:
   ```
   RUNPOD_BASE_URL=https://api.runpod.ai/v2/<endpoint-id>/openai/v1
   RUNPOD_API_KEY=...
   RUNPOD_MODEL=Qwen/Qwen3-32B-Instruct      # exact name your endpoint serves
   ```
4. Sanity check from the host:
   ```bash
   curl -s "$RUNPOD_BASE_URL/models" -H "Authorization: Bearer $RUNPOD_API_KEY" | jq .
   ```

## 6. Blog repo PR access

1. https://github.com/settings/personal-access-tokens/new → fine-grained PAT
   limited to your blog repo with permissions:
   - **Contents: Read & write**
   - **Pull requests: Read & write**
2. Fill `.env`:
   ```
   BLOG_REPO=youruser/yourblog
   BLOG_DEFAULT_BRANCH=main
   BLOG_POSTS_DIR=src/content/posts        # adjust to your repo layout
   GITHUB_TOKEN=github_pat_...
   ```

## 7. (Optional) ElevenLabs voiceover

Skip if you'll record voiceovers yourself.

1. https://elevenlabs.io → API key.
2. Voice library → pick a voice → copy its ID.
3. Fill `.env`:
   ```
   ELEVENLABS_API_KEY=...
   ELEVENLABS_VOICE_ID=...
   ```

## 8. Brand block + Reddit allowlist

Edit the `BRAND_*` and `REDDIT_ALLOWED_SUBS` values in `.env`. The allowlist
is comma-separated, no `r/` prefix. The bot will only ever recommend subs from
this list.

## 9. Bring it up

```bash
docker compose up -d --build
docker compose logs -f openclaw
```

You should see Tailscale come up first, then the MCP server, then OpenClaw.

In your Tailscale admin, the machine should appear as `<TS_HOSTNAME>`.

Open the Control UI from any tailnet device:
```
http://<TS_HOSTNAME>:18789
```

## 10. Pair the Discord bot

OpenClaw's default DM policy is `pairing` — but this template uses
`allowlist` with your `DISCORD_OWNER_ID`, so pairing is skipped and you can
DM immediately.

1. Find your bot in Discord (in any server it's added to, or via direct
   message after using the OAuth invite link).
2. DM it: `hello`.
3. The agent should reply.

## 11. First post

DM the bot a markdown file as an attachment, with a message like:

> Draft socials for this post. Title: "Running Gemma 3 on a 5090".
> Slug: gemma-3-on-5090.

Expected behaviour:
1. Bot calls `draft_x_post`, `draft_linkedin_post`, `draft_medium_post`,
   `draft_reddit_post`, and `draft_short_script` in parallel.
2. Bot replies with all five drafts inline.
3. Bot asks before opening the blog PR.
4. If you confirm, it calls `publish_blog_pr` and replies with the PR URL.
5. Optional: `synthesize the voiceover for the short` → bot calls
   `synthesize_voiceover`, file lands in `./data/voiceovers/` on the host.

## Troubleshooting

| Symptom | Check |
|---|---|
| `tailscale` container restarts | `docker logs tailscale` — usually a stale auth key |
| Control UI 404 | `docker compose logs openclaw` — config parse error in `openclaw.json5` |
| Bot doesn't reply | Discord intents not enabled, or wrong `DISCORD_OWNER_ID` |
| Tools never called | `docker logs openclaw-mcp` — MCP server not reachable on `localhost:8000` (the three containers must share the tailscale netns) |
| `publish_blog_pr` fails | PAT lacks `pull_requests: write`, or `BLOG_POSTS_DIR` path doesn't exist in repo |
| RunPod 401/404 | Verify `RUNPOD_BASE_URL` ends in `/openai/v1` and the model name matches what the endpoint serves |

## Updating

```bash
git pull
docker compose pull        # pulls latest openclaw image
docker compose up -d --build
```
