"""MCP server exposing social-drafting tools to an OpenClaw agent.

Each draft_* tool calls the configured RunPod (OpenAI-compatible) endpoint with
a channel-specific prompt template, then returns the draft text. The agent
relays drafts back to the user in Discord for manual posting. The
publish_blog_pr tool opens a PR against the configured blog repo with the
markdown file ready to merge.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from textwrap import dedent

import httpx
from fastmcp import FastMCP
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Config — all from container env (loaded from .env via docker compose).
# ---------------------------------------------------------------------------
RUNPOD_BASE_URL = os.environ["RUNPOD_BASE_URL"]
RUNPOD_API_KEY = os.environ["RUNPOD_API_KEY"]
RUNPOD_MODEL = os.environ["RUNPOD_MODEL"]

BRAND_NAME = os.environ.get("BRAND_NAME", "the blog")
BRAND_URL = os.environ.get("BRAND_URL", "")
BRAND_TAGLINE = os.environ.get("BRAND_TAGLINE", "")
BRAND_VOICE = os.environ.get(
    "BRAND_VOICE", "Direct, technical, no hype. Show the command, show the output."
)

REDDIT_ALLOWED_SUBS = [
    s.strip() for s in os.environ.get("REDDIT_ALLOWED_SUBS", "").split(",") if s.strip()
]

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

BLOG_REPO = os.environ.get("BLOG_REPO", "")
BLOG_DEFAULT_BRANCH = os.environ.get("BLOG_DEFAULT_BRANCH", "main")
BLOG_POSTS_DIR = os.environ.get("BLOG_POSTS_DIR", "src/content/posts")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

DATA_DIR = Path("/app/data")
VOICEOVER_DIR = DATA_DIR / "voiceovers"
VOICEOVER_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# LLM client — RunPod serverless exposes an OpenAI-compatible endpoint.
# ---------------------------------------------------------------------------
llm = AsyncOpenAI(base_url=RUNPOD_BASE_URL, api_key=RUNPOD_API_KEY)

BRAND_BLOCK = dedent(
    f"""
    Brand: {BRAND_NAME}
    URL:   {BRAND_URL}
    About: {BRAND_TAGLINE}
    Voice: {BRAND_VOICE}
    """
).strip()


async def _generate(system: str, user: str, max_tokens: int = 1200) -> str:
    resp = await llm.chat.completions.create(
        model=RUNPOD_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("social-tools")


@mcp.tool
async def draft_x_post(markdown: str) -> str:
    """Draft a single X / Twitter post for the given blog markdown.

    Returns one tweet, ≤280 characters, with a hook, a one-line takeaway, and
    a CTA pointing to the blog URL. Does not post anywhere.
    """
    system = dedent(
        f"""
        You write X / Twitter posts that promote technical blog content.

        {BRAND_BLOCK}

        Rules:
        - Output ONLY the tweet text. No quotes, no commentary, no hashtags
          unless they are technically meaningful (e.g. #LocalLLM is fine,
          #Tech is not).
        - Hard limit: 280 characters including the URL.
        - Open with a concrete hook: a number, a result, or a sharp claim.
        - End with the URL on its own line.
        - No emoji unless the post is genuinely playful.
        """
    ).strip()
    user = f"Blog post markdown:\n\n{markdown}\n\nThe URL to include is: {BRAND_URL}"
    return await _generate(system, user, max_tokens=300)


@mcp.tool
async def draft_linkedin_post(markdown: str) -> str:
    """Draft a LinkedIn post for the given blog markdown.

    Returns 600–1500 characters, written for a technical-professional audience.
    """
    system = dedent(
        f"""
        You write LinkedIn posts that promote technical blog content.

        {BRAND_BLOCK}

        Rules:
        - Output ONLY the post text. No surrounding explanation.
        - 600–1500 characters.
        - Open with a one-sentence hook on its own line.
        - Use short paragraphs (1–3 lines) separated by blank lines.
        - End with: "Full write-up: {BRAND_URL}"
        - No hashtag spam. At most three, only if they're terms a real
          practitioner would search.
        """
    ).strip()
    return await _generate(system, f"Blog post markdown:\n\n{markdown}", max_tokens=900)


@mcp.tool
async def draft_medium_post(markdown: str, title: str = "") -> str:
    """Draft a Medium cross-post version of the blog markdown.

    Adds a canonical-source note at the top pointing back to the original.
    Returns full markdown — paste into Medium's importer or compose view.
    """
    system = dedent(
        f"""
        You adapt technical blog posts for Medium cross-posting.

        {BRAND_BLOCK}

        Rules:
        - Output ONLY the markdown body, no commentary.
        - Begin with a one-line italic note: "*Originally published at
          [{BRAND_NAME}]({BRAND_URL}).*" then a blank line.
        - Preserve code blocks and technical detail exactly. Do not water down.
        - You may rewrite the intro paragraph for a Medium reader who has not
          seen the original — keep the rest near-verbatim.
        - End with a one-line CTA linking back to {BRAND_URL}.
        """
    ).strip()
    user = f"Title: {title}\n\nOriginal markdown:\n\n{markdown}"
    return await _generate(system, user, max_tokens=4000)


@mcp.tool
async def draft_reddit_post(markdown: str) -> str:
    """Recommend a subreddit (from the configured allowlist) and draft a
    value-first self-post.

    The draft does NOT include the blog URL — it is written as a discussion
    post about what the author learned/experienced. Promotion happens
    indirectly via the user's Reddit profile, which links to {BRAND_URL}.
    """
    if not REDDIT_ALLOWED_SUBS:
        return (
            "No subreddits configured. Set REDDIT_ALLOWED_SUBS in .env "
            "(comma-separated, no r/ prefix)."
        )
    subs = ", ".join(f"r/{s}" for s in REDDIT_ALLOWED_SUBS)
    system = dedent(
        f"""
        You help a technical author share blog-post content on Reddit without
        getting flagged as self-promotion.

        {BRAND_BLOCK}

        The author's allowed subreddits are: {subs}

        Rules:
        - Output in this exact format:
          SUBREDDIT: r/<one of the allowed subs>
          REASONING: <one sentence on why this sub fits>
          TITLE: <a question or specific claim, no clickbait>
          BODY:
          <the self-post body in markdown>
        - The BODY must read as a first-person account of what the author
          tried, observed, or learned. No links to the blog. No "I wrote a
          blog post about this." No "check my profile."
        - Lead with a concrete result, command, or finding worth discussing.
        - Invite responses: end with a specific question.
        - 150–500 words.
        """
    ).strip()
    return await _generate(system, f"Blog post markdown:\n\n{markdown}", max_tokens=1200)


@mcp.tool
async def draft_short_script(markdown: str, duration_sec: int = 45) -> str:
    """Draft a short-form video script (YouTube Shorts / TikTok) for screen-
    capture + voiceover production.

    Returns a structured script with HOOK, BEATS (with on-screen text and
    B-roll cues), and OUTRO. Use synthesize_voiceover() to render the audio.
    """
    system = dedent(
        f"""
        You write short-form video scripts for technical content. The video is
        produced by screen-capture (terminal, code editor, dashboards) plus a
        TTS voiceover. The viewer's goal: click through to read the full post.

        {BRAND_BLOCK}

        Rules:
        - Target duration: {duration_sec} seconds (~{duration_sec * 2} words spoken).
        - Output in this exact format:
          HOOK (0-3s): <spoken line>  | ON-SCREEN: <text overlay> | B-ROLL: <what to capture>
          BEAT 1 (3-Xs): <spoken line> | ON-SCREEN: <...> | B-ROLL: <...>
          BEAT 2 (X-Ys): ...
          ...
          OUTRO (last 3s): <spoken line> | ON-SCREEN: "Full write-up at {BRAND_URL}" | B-ROLL: <...>
        - Open with a number, result, or pointed question. No "Hey guys".
        - Keep beats to 8–12 seconds each.
        - Spoken lines must sound natural read aloud — short clauses, no
          parenthetical asides.
        """
    ).strip()
    return await _generate(system, f"Blog post markdown:\n\n{markdown}", max_tokens=1500)


@mcp.tool
async def synthesize_voiceover(script_spoken_text: str, filename: str = "voiceover.mp3") -> str:
    """Render the spoken portion of a short-form script to MP3 via ElevenLabs.

    Pass ONLY the spoken lines (one per line), not the on-screen / B-roll
    annotations. Returns the path to the saved file inside the container's
    /app/data/voiceovers/ directory (host: ./data/voiceovers/).
    """
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        return "ElevenLabs not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID."
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename) or "voiceover.mp3"
    if not safe_name.endswith(".mp3"):
        safe_name += ".mp3"
    out_path = VOICEOVER_DIR / safe_name

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "accept": "audio/mpeg"}
    body = {
        "text": script_spoken_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.7},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        out_path.write_bytes(r.content)
    return f"Saved {out_path} ({len(r.content) // 1024} KB). Host path: ./data/voiceovers/{safe_name}"


@mcp.tool
async def publish_blog_pr(markdown: str, title: str, slug: str) -> str:
    """Open a PR against the configured blog repo with the markdown post.

    Creates a new branch, writes the file to BLOG_POSTS_DIR/<slug>.md, commits,
    pushes, and opens a PR. Returns the PR URL. The user merges it themselves
    to trigger their own deploy pipeline.
    """
    if not BLOG_REPO or not GITHUB_TOKEN:
        return "Blog publishing not configured. Set BLOG_REPO and GITHUB_TOKEN."
    safe_slug = re.sub(r"[^a-z0-9-]", "-", slug.lower()).strip("-") or "post"
    branch = f"openclaw/post-{safe_slug}"

    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GH_TOKEN": GITHUB_TOKEN, "GIT_TERMINAL_PROMPT": "0"}
        repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{BLOG_REPO}.git"

        def run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                args, cwd=cwd, env=env, check=True, capture_output=True, text=True
            )

        try:
            run("git", "clone", "--depth", "1", "--branch", BLOG_DEFAULT_BRANCH, repo_url, tmp)
            run("git", "config", "user.email", "openclaw@localhost", cwd=tmp)
            run("git", "config", "user.name", "openclaw-bot", cwd=tmp)
            run("git", "checkout", "-b", branch, cwd=tmp)

            posts_dir = Path(tmp) / BLOG_POSTS_DIR
            posts_dir.mkdir(parents=True, exist_ok=True)
            (posts_dir / f"{safe_slug}.md").write_text(markdown)

            run("git", "add", str(Path(BLOG_POSTS_DIR) / f"{safe_slug}.md"), cwd=tmp)
            run("git", "commit", "-m", f"post: {title}", cwd=tmp)
            run("git", "push", "-u", "origin", branch, cwd=tmp)

            pr = run(
                "gh", "pr", "create",
                "--repo", BLOG_REPO,
                "--base", BLOG_DEFAULT_BRANCH,
                "--head", branch,
                "--title", title,
                "--body", "Drafted by openclaw. Review and merge to deploy.",
                cwd=tmp,
            )
            return pr.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
