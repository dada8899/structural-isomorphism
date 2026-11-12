#!/usr/bin/env python3
"""GitHub-webhook → Discord-channel bridge.

Receives GitHub webhook payloads at /webhook/github, verifies the HMAC
signature, and routes the event to the right Discord channel via the
Discord REST API (using bot token from env).

Also: when the bot is connected to Discord via gateway, listens for
on_member_join and DMs the welcome message from docs/community/discord-welcome-message.md.

Design notes:
- One file, no daemon framework, runs as a single aiohttp server + a
  parallel discord.py client.
- HMAC signature verification per GitHub's spec
  (https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
- Channel IDs are loaded from env, not hardcoded — keeps the file shareable.
- All external calls (Discord REST, gateway) are wrapped in try/except
  with structured logging per CLAUDE.md guidance.

Env vars:
    DISCORD_BOT_TOKEN              bot token from Discord Dev Portal
    GITHUB_WEBHOOK_SECRET          shared secret with GitHub
    DISCORD_CHANNEL_GENERAL        channel ID (Discord developer mode → right-click)
    DISCORD_CHANNEL_HELP
    DISCORD_CHANGELOG_CHANNEL_ID   for #changelog (contributors-only PR mirror)
    DISCORD_CONTRIBUTORS_CHANNEL_ID
    DISCORD_RELEASES_CHANNEL_ID
    DISCORD_SHOWCASE_CHANNEL_ID
    DISCORD_QUESTIONS_CHANNEL_ID
    DISCORD_INTRODUCTIONS_CHANNEL_ID
    DISCORD_GUILD_ID               server (guild) ID
    LISTEN_HOST                    default 127.0.0.1
    LISTEN_PORT                    default 8770
    WELCOME_MESSAGE_PATH           default docs/community/discord-welcome-message.md

Run:
    python3 scripts/discord-bot.py

Do NOT run this in production without filling the env file and provisioning
a Discord application + bot user. See docs/community/discord-bot-config-final-2026-05-24.md.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from aiohttp import web

# discord.py is the canonical Discord client lib; pip install discord.py>=2.3
try:
    import discord
    from discord.ext import commands
except ImportError:
    print(
        "ERROR: discord.py not installed. Run: pip install 'discord.py>=2.3'",
        file=sys.stderr,
    )
    sys.exit(1)

# Structured logging — key/value style, easy to grep in journalctl.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("discord-bot")

# ----- env / config -----------------------------------------------------------

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

CHANNEL_GENERAL = int(os.environ.get("DISCORD_CHANNEL_GENERAL", "0"))
CHANNEL_HELP = int(os.environ.get("DISCORD_CHANNEL_HELP", "0"))
CHANNEL_CHANGELOG = int(os.environ.get("DISCORD_CHANGELOG_CHANNEL_ID", "0"))
CHANNEL_CONTRIBUTORS = int(os.environ.get("DISCORD_CONTRIBUTORS_CHANNEL_ID", "0"))
CHANNEL_RELEASES = int(os.environ.get("DISCORD_RELEASES_CHANNEL_ID", "0"))
CHANNEL_SHOWCASE = int(os.environ.get("DISCORD_SHOWCASE_CHANNEL_ID", "0"))
CHANNEL_QUESTIONS = int(os.environ.get("DISCORD_QUESTIONS_CHANNEL_ID", "0"))
CHANNEL_INTRODUCTIONS = int(os.environ.get("DISCORD_INTRODUCTIONS_CHANNEL_ID", "0"))
GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0"))

LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8770"))

WELCOME_MESSAGE_PATH = Path(
    os.environ.get(
        "WELCOME_MESSAGE_PATH",
        "docs/community/discord-welcome-message.md",
    )
)

# Fail fast at startup if essential env is missing. The systemd unit will
# restart and the operator will see this in journalctl.
if not DISCORD_BOT_TOKEN:
    log.error("DISCORD_BOT_TOKEN not set; refusing to start")
    sys.exit(2)
if not GITHUB_WEBHOOK_SECRET:
    log.error("GITHUB_WEBHOOK_SECRET not set; refusing to start")
    sys.exit(2)

# ----- discord.py client ------------------------------------------------------

intents = discord.Intents.default()
intents.members = True   # required for on_member_join
intents.message_content = False  # we don't read user messages

bot = commands.Bot(command_prefix="!si ", intents=intents)


@bot.event
async def on_ready() -> None:
    log.info("bot_ready user=%s guild_count=%d", bot.user, len(bot.guilds))


def _load_welcome_message() -> str:
    """Read welcome DM template from the markdown file.

    Extracts the content inside the first triple-backtick block under
    '## Welcome DM template'. Falls back to a short default if the file
    is missing or malformed (defence in depth — never crash on missing doc).
    """
    try:
        text = WELCOME_MESSAGE_PATH.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("welcome_message_load_failed path=%s err=%s", WELCOME_MESSAGE_PATH, e)
        return (
            "Welcome to Structural Isomorphism! Head to #rules first, "
            "then introduce yourself in #introductions. Glad to have you."
        )

    # Naive but robust: find the first fenced block after the header.
    marker = "## Welcome DM template"
    if marker not in text:
        return text[:1800]  # under 2000-char Discord DM limit

    after = text.split(marker, 1)[1]
    parts = after.split("```", 2)
    if len(parts) < 2:
        return after.strip()[:1800]
    body = parts[1]
    # discord.py supports {user.mention} but not Carl-bot's exact syntax;
    # replace at send time with the actual mention.
    return body.strip()[:1800]


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """DM the welcome message to every joining member.

    Carl-bot already auto-assigns @member role; our bot adds the rich DM.
    """
    log.info("member_join id=%d name=%s", member.id, member.name)
    try:
        template = _load_welcome_message()
        msg = template.replace("{user.mention}", member.mention).replace(
            "{server.name}", member.guild.name
        )
        try:
            await member.send(msg)
            log.info("welcome_dm_sent id=%d", member.id)
        except discord.Forbidden:
            # User has DMs disabled — common, not an error.
            log.info("welcome_dm_blocked id=%d (DMs disabled)", member.id)
    except Exception as e:
        log.exception("on_member_join_failed id=%d err=%s", member.id, e)


# ----- GitHub → Discord routing ----------------------------------------------


def _verify_signature(payload: bytes, header: str | None) -> bool:
    """Verify GitHub's X-Hub-Signature-256 HMAC.

    Per https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries.
    Returns False if header is missing or doesn't match — never raises.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(
            GITHUB_WEBHOOK_SECRET.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, header)


def _color_for_event(event: str, action: str | None) -> int:
    """Map event to embed color (Discord uses int RGB)."""
    if event == "release":
        return 0x7057FF  # purple, matches `good first issue` GH label color
    if event == "pull_request" and action == "closed":
        return 0x6F42C1  # GitHub merged-purple
    if event == "pull_request":
        return 0x238636  # GitHub open-green
    if event == "issues" and action == "opened":
        return 0xD73A4A  # GitHub bug-red (used loosely for "new issue")
    if event == "discussion":
        return 0x0969DA  # GitHub blue
    return 0x586069  # neutral grey


def _build_embed(event: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build the Discord embed dict for a GitHub payload, or None to skip."""
    action = payload.get("action")

    if event == "issues" and action == "opened":
        issue = payload["issue"]
        labels = [lab["name"] for lab in issue.get("labels", [])]
        return {
            "title": f"Issue #{issue['number']}: {issue['title']}",
            "url": issue["html_url"],
            "description": (issue.get("body") or "")[:300],
            "color": _color_for_event(event, action),
            "fields": [
                {"name": "Author", "value": issue["user"]["login"], "inline": True},
                {"name": "Labels", "value": ", ".join(labels) or "—", "inline": True},
            ],
            "_route_hint": "help" if "good first issue" in labels else "general",
        }

    if event == "pull_request" and action == "opened":
        pr = payload["pull_request"]
        return {
            "title": f"PR #{pr['number']} opened: {pr['title']}",
            "url": pr["html_url"],
            "description": (pr.get("body") or "")[:300],
            "color": _color_for_event(event, action),
            "fields": [
                {"name": "Author", "value": pr["user"]["login"], "inline": True},
                {"name": "Branch", "value": pr["head"]["ref"], "inline": True},
            ],
            "_route_hint": "contributors",
        }

    if event == "pull_request" and action == "closed":
        pr = payload["pull_request"]
        if not pr.get("merged"):
            # Closed without merge — quiet, don't post.
            return None
        author = pr["user"]["login"]
        # Heuristic for new-contributor (first-time): GitHub passes
        # author_association. NONE / FIRST_TIME_CONTRIBUTOR → showcase channel.
        is_new = pr.get("author_association") in ("NONE", "FIRST_TIME_CONTRIBUTOR")
        return {
            "title": f"PR #{pr['number']} merged: {pr['title']}",
            "url": pr["html_url"],
            "description": f"Thanks to **{author}** for the contribution.",
            "color": _color_for_event(event, action),
            "_route_hint": "showcase" if is_new else "contributors",
        }

    if event == "release" and action == "published":
        rel = payload["release"]
        return {
            "title": f"Release {rel['tag_name']}: {rel['name'] or ''}",
            "url": rel["html_url"],
            "description": (rel.get("body") or "")[:500],
            "color": _color_for_event(event, action),
            "_route_hint": "releases",
        }

    if event == "discussion" and action == "created":
        disc = payload["discussion"]
        cat = (disc.get("category") or {}).get("name", "")
        if cat.lower() != "q&a":
            return None
        return {
            "title": f"Q&A: {disc['title']}",
            "url": disc["html_url"],
            "description": (disc.get("body") or "")[:300],
            "color": _color_for_event(event, action),
            "fields": [{"name": "Author", "value": disc["user"]["login"], "inline": True}],
            "_route_hint": "questions",
        }

    return None


def _channel_for_hint(hint: str) -> int:
    return {
        "help": CHANNEL_HELP,
        "general": CHANNEL_GENERAL,
        "contributors": CHANNEL_CONTRIBUTORS,
        "showcase": CHANNEL_SHOWCASE,
        "releases": CHANNEL_RELEASES,
        "questions": CHANNEL_QUESTIONS,
        "changelog": CHANNEL_CHANGELOG,
    }.get(hint, CHANNEL_GENERAL)


async def _post_embed(channel_id: int, embed_dict: dict[str, Any]) -> None:
    """Post embed to a Discord channel; swallow errors and log."""
    if channel_id <= 0:
        log.warning("post_skipped reason=channel_id_unset")
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except discord.NotFound:
        log.error("channel_not_found id=%d", channel_id)
        return
    except Exception as e:
        log.exception("channel_fetch_failed id=%d err=%s", channel_id, e)
        return

    embed = discord.Embed(
        title=embed_dict["title"],
        url=embed_dict.get("url"),
        description=embed_dict.get("description") or "",
        color=embed_dict.get("color", 0x586069),
    )
    for field in embed_dict.get("fields", []):
        embed.add_field(
            name=field["name"],
            value=field["value"] or "—",
            inline=field.get("inline", False),
        )
    try:
        await channel.send(embed=embed)
        log.info(
            "embed_posted channel=%d title=%r",
            channel_id,
            embed_dict["title"][:80],
        )
    except Exception as e:
        log.exception("embed_post_failed channel=%d err=%s", channel_id, e)


# ----- aiohttp HTTP server (webhook receiver) --------------------------------


async def handle_github_webhook(request: web.Request) -> web.Response:
    """Receive a GitHub webhook, verify HMAC, route to Discord."""
    body = await request.read()
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(body, sig):
        log.warning("webhook_signature_invalid remote=%s", request.remote)
        return web.Response(status=401, text="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        log.error("webhook_bad_json err=%s", e)
        return web.Response(status=400, text="bad json")

    log.info(
        "webhook_received event=%s action=%s repo=%s",
        event,
        payload.get("action"),
        (payload.get("repository") or {}).get("full_name"),
    )

    embed = _build_embed(event, payload)
    if embed is None:
        return web.Response(status=200, text="event ignored (no route)")

    hint = embed.pop("_route_hint", "general")
    channel_id = _channel_for_hint(hint)
    # Don't await — fire-and-forget so GitHub gets a fast 200.
    asyncio.create_task(_post_embed(channel_id, embed))
    return web.Response(status=200, text="ok")


async def handle_healthz(request: web.Request) -> web.Response:
    """Liveness probe for nginx + systemd watchdog."""
    return web.json_response(
        {
            "ok": True,
            "bot_user": str(bot.user) if bot.is_ready() else None,
            "guilds": len(bot.guilds) if bot.is_ready() else 0,
        }
    )


def make_http_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/github", handle_github_webhook)
    app.router.add_get("/healthz", handle_healthz)
    return app


# ----- main: run bot + http in same loop --------------------------------------


async def _main() -> None:
    app = make_http_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, LISTEN_HOST, LISTEN_PORT)
    await site.start()
    log.info("http_listening host=%s port=%d", LISTEN_HOST, LISTEN_PORT)

    # bot.start blocks; gather both so an exit in either tears down the other.
    try:
        await bot.start(DISCORD_BOT_TOKEN)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("shutdown reason=keyboard_interrupt")
