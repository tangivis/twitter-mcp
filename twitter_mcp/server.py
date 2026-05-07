"""Twitter MCP Server - twikit-based, no API key needed."""

import argparse
import asyncio
import inspect
import json
import os
import re
import sys
import time
import types
import typing
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp._vendor.twikit import Client
from twitter_mcp._vendor.twikit.errors import NotFound, TooManyRequests

mcp = FastMCP("twitter")

# Cookies 路径: 环境变量 > 默认路径
COOKIES_PATH = Path(
    os.environ.get(
        "TWITTER_COOKIES",
        os.path.expanduser("~/.config/twitter-mcp/cookies.json"),
    )
)

# Matches /i/article/<digits> in any twitter.com / x.com URL.
_ARTICLE_URL_RE = re.compile(r"/i/article/(\d+)")
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
_GRAPHQL_BASE = "https://x.com/i/api/graphql"

# Article reader (issue #10) — two-hop flow.
#
# `ArticleEntityResultByRestId` (the op 0.1.8 used) is X's *editor* op:
# it only returns content for articles you authored. The public reader has
# no dedicated GraphQL operation; instead, the X web client takes two hops:
#
#   1. ArticleRedirectScreenQuery resolves the article rest_id to the
#      underlying tweet rest_id (the article body lives on a tweet).
#   2. TweetResultByRestId fetches that tweet with the article fieldToggles
#      enabled, exposing the body at
#      `.article.article_results.result.plain_text`.
#
# Refresh the queryId the same way every other twikit Endpoint constant is
# refreshed when X rotates a hash (curl `bundle.Articles.*.js` from
# `abs.twimg.com/responsive-web/client-web/`, no auth required).
_ARTICLE_REDIRECT_QUERY_ID = "zrSRXJmE1vj37AUmkh2oGg"
_ARTICLE_REDIRECT_OP_NAME = "ArticleRedirectScreenQuery"


async def _get_client() -> Client:
    """Create an authenticated twikit client."""
    cookies = json.loads(COOKIES_PATH.read_text())
    client = Client("en")
    client.set_cookies({"auth_token": cookies["auth_token"], "ct0": cookies["ct0"]})
    return client


def _dumps(obj) -> str:
    """JSON-encode a tool output with native non-ASCII characters preserved.

    `json.dumps` defaults to `ensure_ascii=True`, which turns 中文 / 日本語 /
    希腊文 / emoji / etc. into `\\uXXXX` escapes. That makes tool outputs
    technically valid JSON but unreadable when an LLM reads them or a human
    pipes them through the CLI. Always emit raw UTF-8 instead.
    """
    # NOTE: must call stdlib `json.dumps` directly here. The project-wide
    # rewrite that introduced this helper renamed every `json.dumps(` to
    # `_dumps(`, including this line — left unfixed it infinite-recurses.
    import json as _stdlib_json

    return _stdlib_json.dumps(obj, ensure_ascii=False)


def _parse_article_url_or_id(value: str | None) -> str | None:
    """Return the article rest_id if `value` is an /i/article/<id> URL, else None.

    Bare numeric IDs are NOT treated as articles — article and tweet IDs share
    the same numeric shape, and we cannot distinguish them without an HTTP call.
    """
    if not value:
        return None
    m = _ARTICLE_URL_RE.search(value)
    return m.group(1) if m else None


def _extract_tweet_id(value: str) -> str:
    """Strip a tweet URL down to its numeric ID; pass numeric IDs through."""
    if "/" in value:
        return value.rstrip("/").split("/")[-1]
    return value


# ── Tools ──────────────────────────────────────────────


@mcp.tool()
async def send_tweet(text: str, reply_to: str | None = None) -> str:
    """Send a tweet. Optionally reply to a tweet by ID.

    Args:
        text: Tweet content (max 280 chars).
        reply_to: Optional tweet ID to reply to.
    """
    client = await _get_client()
    tweet = await client.create_tweet(text=text, reply_to=reply_to)
    return _dumps({"id": tweet.id, "text": text, "status": "sent"})


@mcp.tool()
async def get_tweet(tweet_id: str) -> str:
    """Fetch a tweet by ID.

    Args:
        tweet_id: The tweet ID (numeric string) or full URL.
    """
    article_id = _parse_article_url_or_id(tweet_id)
    if article_id is not None:
        raise ToolError(
            f"This is an X Article (id={article_id}), not a tweet. "
            f"Use get_article instead."
        )

    tweet_id = _extract_tweet_id(tweet_id)

    client = await _get_client()
    tweets = await client.get_tweets_by_ids([tweet_id])
    if not tweets or tweets[0] is None:
        raise ToolError(
            f"Tweet {tweet_id} not found. If this is an X Article URL, "
            f"use get_article instead."
        )
    t = tweets[0]
    q = t.quote  # Tweet | None — sync, uses already-fetched response (issue #82)
    return _dumps(
        {
            "id": t.id,
            "author": t.user.screen_name,
            "author_name": t.user.name,
            "text": t.text,
            "created_at": str(t.created_at),
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
            "in_reply_to": t.in_reply_to,
            "conversation_id": t.conversation_id,
            "is_quote_status": t.is_quote_status,
            "quoted_id": q.id if q else None,
            "quoted_author": q.user.screen_name if q else None,
            "quoted_text": q.text if q else None,
        }
    )


# ── download_tweet_video helpers (issue #84) ─────────
#
# yt-dlp + ffmpeg are NOT bundled as Python deps. Users install them
# out-of-band (`uv tool install yt-dlp`, system package manager for
# ffmpeg). We shell out via subprocess; subprocess crash can't take
# down the MCP server.

_DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "twikit-mcp"


def _resolve_download_dir(arg: str | None) -> Path:
    """arg → $TWIKIT_DOWNLOAD_DIR → ~/Downloads/twikit-mcp/."""
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("TWIKIT_DOWNLOAD_DIR")
    if env:
        return Path(env).expanduser()
    return _DEFAULT_DOWNLOAD_DIR


def _cookies_json_to_netscape(json_path: Path) -> Path:
    """Convert our cookies.json → Netscape cookies.txt for yt-dlp.

    Returns a temp file path; caller must `unlink(missing_ok=True)`.
    """
    import tempfile

    cookies = json.loads(Path(json_path).read_text(encoding="utf-8"))
    ct0 = cookies.get("ct0")
    auth = cookies.get("auth_token")
    if not ct0 or not auth:
        raise ToolError(
            f"cookies.json missing ct0 or auth_token "
            f"(found keys: {sorted(cookies.keys())!r})"
        )
    fd, p = tempfile.mkstemp(suffix=".txt", prefix="twikit-mcp-cookies-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".x.com\tTRUE\t/\tTRUE\t9999999999\tct0\t{ct0}\n")
        f.write(f".x.com\tTRUE\t/\tTRUE\t9999999999\tauth_token\t{auth}\n")
    return Path(p)


def _ytdlp_classify_error(returncode: int, stderr: str) -> ToolError:
    """Map yt-dlp exit code + stderr → user-facing ToolError with hint."""
    s = stderr.lower()
    if returncode == 127 or "yt-dlp" in s and "not found" in s:
        return ToolError("yt-dlp not found. Install with: uv tool install yt-dlp")
    if "ffmpeg" in s and ("not installed" in s or "not found" in s):
        return ToolError(
            "ffmpeg required for this format. Install with: "
            "brew install ffmpeg (macOS) / apt install ffmpeg (Ubuntu)"
        )
    if "no video" in s or "unsupported url" in s:
        return ToolError("Tweet has no video attachment")
    return ToolError(
        f"yt-dlp failed (exit {returncode}): {stderr.strip() or '<no stderr>'}"
    )


async def _ytdlp_download(
    url: str,
    cookies_path: Path,
    output_dir: Path,
    format_spec: str,
) -> dict:
    """Spawn yt-dlp, parse --print-json output, return relevant subset."""
    cmd = [
        "yt-dlp",
        "--print-json",
        "--no-progress",
        "--cookies",
        str(cookies_path),
        "-f",
        format_spec,
        "-o",
        str(output_dir / "%(id)s.%(ext)s"),
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise ToolError("yt-dlp not found. Install with: uv tool install yt-dlp") from e

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise _ytdlp_classify_error(
            proc.returncode, stderr.decode("utf-8", errors="replace")
        )

    last_json_line = None
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            last_json_line = line
    if not last_json_line:
        raise ToolError(
            f"yt-dlp produced no JSON output. stderr: "
            f"{stderr.decode('utf-8', errors='replace').strip()}"
        )

    data = json.loads(last_json_line)
    filepath = data.get("filepath") or data.get("_filename")
    if not filepath:
        filepath = str(output_dir / f"{data['id']}.{data['ext']}")
    p = Path(filepath)
    return {
        "path": str(p.absolute()),
        "size_bytes": p.stat().st_size if p.exists() else None,
        "duration_sec": data.get("duration"),
        "format": f"video/{data['ext']}" if data.get("ext") else None,
        "width": data.get("width"),
        "height": data.get("height"),
        "url": data.get("webpage_url") or url,
        "tweet_id": data.get("id"),
    }


@mcp.tool()
async def download_tweet_video(
    tweet_id: str,
    output_dir: str | None = None,
    format: str = "best[ext=mp4]",
) -> str:
    """Download video(s) attached to a tweet via yt-dlp.

    Args:
        tweet_id: Tweet ID (numeric string) or full URL.
        output_dir: Where to save. Default: $TWIKIT_DOWNLOAD_DIR or
                    ~/Downloads/twikit-mcp/.
        format: yt-dlp format selector. Default "best[ext=mp4]" (single
                muxed mp4, no ffmpeg required). Pass
                "bestvideo+bestaudio" for separate-stream max-quality
                merge (requires ffmpeg).

    Returns:
        JSON with path, size_bytes, duration_sec, format, width,
        height, url, tweet_id. Raises ToolError if yt-dlp / ffmpeg
        is missing, the tweet has no video, or download fails.
    """
    tid = _extract_tweet_id(tweet_id)
    out_dir = _resolve_download_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cookies_txt = _cookies_json_to_netscape(COOKIES_PATH)
    try:
        info = await _ytdlp_download(
            url=f"https://x.com/i/status/{tid}",
            cookies_path=cookies_txt,
            output_dir=out_dir,
            format_spec=format,
        )
    finally:
        cookies_txt.unlink(missing_ok=True)

    return _dumps(info)


@mcp.tool()
async def get_timeline(count: int = 20) -> str:
    """Fetch home timeline tweets.

    Args:
        count: Number of tweets to fetch (default 20).
    """
    client = await _get_client()
    tweets = await client.get_timeline(count=count)
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "author": t.user.screen_name,
                "text": t.text[:200],
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return _dumps(result)


@mcp.tool()
async def search_tweets(query: str, count: int = 20, product: str = "Latest") -> str:
    """Search tweets.

    Args:
        query: Search query string.
        count: Number of results (default 20).
        product: "Latest" or "Top" (default "Latest").
    """
    client = await _get_client()
    tweets = await client.search_tweet(query, product=product, count=count)
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "author": t.user.screen_name,
                "text": t.text[:200],
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return _dumps(result)


@mcp.tool()
async def like_tweet(tweet_id: str) -> str:
    """Like a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.favorite_tweet(tweet_id)
    return _dumps({"tweet_id": tweet_id, "status": "liked"})


@mcp.tool()
async def retweet(tweet_id: str) -> str:
    """Retweet a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.retweet(tweet_id)
    return _dumps({"tweet_id": tweet_id, "status": "retweeted"})


@mcp.tool()
async def get_user_tweets(screen_name: str, count: int = 20) -> str:
    """Get recent tweets from a specific user.

    Args:
        screen_name: Twitter username (without @).
        count: Number of tweets to fetch (default 20).
    """
    client = await _get_client()
    user = await client.get_user_by_screen_name(screen_name)
    tweets = await client.get_user_tweets(user.id, tweet_type="Tweets", count=count)
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "text": t.text[:200],
                "created_at": str(t.created_at),
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return _dumps(result)


_PAGINATED_MAX_COUNT = 100

_VALID_TREND_CATEGORIES = frozenset(
    {"trending", "for-you", "news", "sports", "entertainment"}
)

_VALID_COMMUNITY_TWEET_TYPES = frozenset({"Top", "Latest", "Media"})


def _require_exactly_one(
    screen_name: str | None, user_id: str | None, *, op: str
) -> None:
    """Enforce exactly-one-of-(screen_name, user_id) input contract.

    Both args optional in the signature so an LLM caller can use whichever
    handle it has, but giving neither (or both) is a tool-level error,
    not a silent fall-through to twikit.
    """
    if not (screen_name or user_id):
        raise ToolError(f"{op} requires either `screen_name` or `user_id`.")
    if screen_name and user_id:
        raise ToolError(
            f"{op} accepts `screen_name` OR `user_id`, not both — got both."
        )


def _user_to_dict(u) -> dict:
    """Compact user dict used in followers / following list outputs.

    Truncates description to 200 chars (matches get_user_tweets / get_timeline
    pattern) so a 100-entry list doesn't blow MAX_MCP_OUTPUT_TOKENS.
    """
    return {
        "id": u.id,
        "screen_name": u.screen_name,
        "name": u.name,
        "description": (u.description or "")[:200],
        "followers_count": u.followers_count,
        "verified": u.verified,
        "is_blue_verified": u.is_blue_verified,
    }


@mcp.tool()
async def get_user_info(
    screen_name: str | None = None, user_id: str | None = None
) -> str:
    """Get a user's profile metadata by screen name OR numeric user ID.

    Caller must provide exactly one of `screen_name` / `user_id`.

    Args:
        screen_name: Twitter username (without @).
        user_id: Twitter numeric user ID.
    """
    _require_exactly_one(screen_name, user_id, op="get_user_info")
    client = await _get_client()
    try:
        if user_id:
            u = await client.get_user_by_id(user_id)
        else:
            u = await client.get_user_by_screen_name(screen_name)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(
            f"User not found: {screen_name or user_id}. Check the spelling / id."
        )

    return _dumps(
        {
            "id": u.id,
            "screen_name": u.screen_name,
            "name": u.name,
            "description": u.description,
            "created_at": str(u.created_at),
            "followers_count": u.followers_count,
            "following_count": u.following_count,
            "tweets_count": u.statuses_count,
            # `verified` is the legacy gold/grey badge (almost always False
            # on modern X — pre-2023 verification batch). `is_blue_verified`
            # is the X Premium blue check most accounts actually have today.
            # Expose both so callers can pick. (PR #23 review feedback.)
            "verified": u.verified,
            "is_blue_verified": u.is_blue_verified,
            "profile_image_url": u.profile_image_url,
            "protected": u.protected,
            "location": u.location,
            "url": u.url,
        }
    )


async def _resolve_user_id(
    client: Client, screen_name: str | None, user_id: str | None
) -> str:
    """Return numeric user_id, resolving from screen_name if needed."""
    if user_id:
        return user_id
    user = await client.get_user_by_screen_name(screen_name)
    return user.id


@mcp.tool()
async def get_user_followers(
    screen_name: str | None = None,
    user_id: str | None = None,
    count: int = 20,
    cursor: str | None = None,
) -> str:
    """Get a user's followers list.

    Note: X aggressively rate-limits follower / following requests — use
    sparingly, paginate via `cursor`, don't loop without backoff.

    Caller must provide exactly one of `screen_name` / `user_id`.

    Args:
        screen_name: Twitter username (without @).
        user_id: Twitter numeric user ID.
        count: Number of followers to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    _require_exactly_one(screen_name, user_id, op="get_user_followers")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )

    client = await _get_client()
    try:
        uid = await _resolve_user_id(client, screen_name, user_id)
        result = await client.get_user_followers(uid, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name or user_id}.")

    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def get_user_following(
    screen_name: str | None = None,
    user_id: str | None = None,
    count: int = 20,
    cursor: str | None = None,
) -> str:
    """Get accounts that a user follows (their following list).

    Note: X aggressively rate-limits follower / following requests — use
    sparingly, paginate via `cursor`, don't loop without backoff.

    Caller must provide exactly one of `screen_name` / `user_id`.

    Args:
        screen_name: Twitter username (without @).
        user_id: Twitter numeric user ID.
        count: Number to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    _require_exactly_one(screen_name, user_id, op="get_user_following")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )

    client = await _get_client()
    try:
        uid = await _resolve_user_id(client, screen_name, user_id)
        result = await client.get_user_following(uid, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name or user_id}.")

    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def follow_user(screen_name: str) -> str:
    """Follow a user by screen name.

    Note: X aggressively rate-limits follow / unfollow — avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    user = await client.get_user_by_screen_name(screen_name)
    await client.follow_user(user.id)
    return _dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "followed"}
    )


@mcp.tool()
async def unfollow_user(screen_name: str) -> str:
    """Unfollow a user by screen name.

    Note: X aggressively rate-limits follow / unfollow — avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    user = await client.get_user_by_screen_name(screen_name)
    await client.unfollow_user(user.id)
    return _dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "unfollowed"}
    )


@mcp.tool()
async def delete_tweet(tweet_id: str) -> str:
    """Delete a tweet by ID.

    Args:
        tweet_id: The tweet ID to delete.
    """
    client = await _get_client()
    try:
        await client.delete_tweet(tweet_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    return _dumps({"tweet_id": tweet_id, "status": "deleted"})


@mcp.tool()
async def unfavorite_tweet(tweet_id: str) -> str:
    """Unlike a tweet by ID.

    Args:
        tweet_id: The tweet ID to unlike.
    """
    client = await _get_client()
    try:
        await client.unfavorite_tweet(tweet_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    return _dumps({"tweet_id": tweet_id, "status": "unliked"})


@mcp.tool()
async def delete_retweet(tweet_id: str) -> str:
    """Un-retweet a tweet by ID.

    Args:
        tweet_id: The tweet ID to un-retweet.
    """
    client = await _get_client()
    try:
        await client.delete_retweet(tweet_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    return _dumps({"tweet_id": tweet_id, "status": "un-retweeted"})


@mcp.tool()
async def bookmark_tweet(tweet_id: str, folder_id: str | None = None) -> str:
    """Bookmark a tweet. Optionally add it to a bookmark folder.

    Args:
        tweet_id: The tweet ID to bookmark.
        folder_id: Optional bookmark folder ID.
    """
    client = await _get_client()
    try:
        await client.bookmark_tweet(tweet_id, folder_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    result: dict = {"tweet_id": tweet_id, "status": "bookmarked"}
    if folder_id is not None:
        result["folder_id"] = folder_id
    return _dumps(result)


@mcp.tool()
async def delete_bookmark(tweet_id: str) -> str:
    """Remove a tweet from bookmarks.

    Args:
        tweet_id: The tweet ID to un-bookmark.
    """
    client = await _get_client()
    try:
        await client.delete_bookmark(tweet_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Bookmark for tweet {tweet_id} not found.")
    return _dumps({"tweet_id": tweet_id, "status": "un-bookmarked"})


@mcp.tool()
async def get_bookmarks(count: int = 20, cursor: str | None = None) -> str:
    """Get bookmarked tweets (paginated).

    Args:
        count: Number of bookmarks to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_bookmarks(count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    tweets = [
        {
            "id": t.id,
            "author": t.user.screen_name,
            "text": t.text[:200],
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
        for t in result
    ]
    return _dumps(
        {
            "tweets": tweets,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(tweets),
        }
    )


@mcp.tool()
async def get_favoriters(
    tweet_id: str, count: int = 40, cursor: str | None = None
) -> str:
    """Get users who liked a tweet (paginated).

    Args:
        tweet_id: The tweet ID.
        count: Number of users to fetch (default 40, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_favoriters(tweet_id, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def get_retweeters(
    tweet_id: str, count: int = 40, cursor: str | None = None
) -> str:
    """Get users who retweeted a tweet (paginated).

    Args:
        tweet_id: The tweet ID.
        count: Number of users to fetch (default 40, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_retweeters(tweet_id, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} not found.")
    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def search_user(query: str, count: int = 20, cursor: str | None = None) -> str:
    """Search for users by query (paginated).

    Args:
        query: Search query string.
        count: Number of users to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not query.strip():
        raise ToolError("query must not be empty.")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.search_user(query, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def get_trends(category: str = "trending", count: int = 20) -> str:
    """Get trending topics by category.

    Args:
        category: One of "trending", "for-you", "news", "sports", "entertainment"
            (default "trending").
        count: Number of trends to fetch (default 20).
    """
    if category not in _VALID_TREND_CATEGORIES:
        raise ToolError(
            f"category must be one of {sorted(_VALID_TREND_CATEGORIES)}, got: {category!r}"
        )
    if count < 1:
        raise ToolError("count must be >= 1.")
    client = await _get_client()
    try:
        trends = await client.get_trends(category, count=count)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    result = [
        {
            "name": t.name,
            "tweets_count": t.tweets_count,
            "domain_context": t.domain_context,
        }
        for t in trends
    ]
    return _dumps({"trends": result, "category": category})


@mcp.tool()
async def get_article_preview(tweet_id: str) -> str:
    """Get title/preview/cover of an X Article embedded in a tweet.

    Uses X's public syndication endpoint — no authentication required.

    Args:
        tweet_id: ID (numeric string) or full URL of a tweet that links to an article.
    """
    tweet_id = _extract_tweet_id(tweet_id)
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            _SYNDICATION_URL,
            params={"id": tweet_id, "token": "a"},
            timeout=15,
        )
    resp.raise_for_status()
    data = resp.json()
    article = data.get("article")
    if not article:
        raise ToolError(f"Tweet {tweet_id} does not embed an article.")
    cover = article.get("cover_media", {}).get("media_info", {}).get("original_img_url")
    return _dumps(
        {
            "rest_id": article["rest_id"],
            "title": article.get("title", ""),
            "preview_text": article.get("preview_text", ""),
            "cover_image": cover,
            "tweet_id": data.get("id_str", tweet_id),
            "author": data.get("user", {}).get("screen_name", ""),
        }
    )


_ARTICLE_FORMATS = ("preview", "plain", "full")


@mcp.tool()
async def get_article(article_id: str, format: str = "plain") -> str:
    """Fetch an X Article (long-form post) by rest_id or URL.

    Two-hop reader flow (issue #10):

      1. `ArticleRedirectScreenQuery` resolves the article rest_id to the
         underlying tweet rest_id.
      2. `TweetResultByRestId` (twikit's existing helper) fetches the tweet
         with article fieldToggles enabled. The body lives at
         `tweet.article.article_results.result`.

    Requires authentication via cookies — same as every other authenticated
    tool here. No env-var setup.

    Args:
        article_id: Article rest_id (numeric string) or full /i/article/<id> URL.
        format: Output shape, one of:
            - "preview" (~1 KB) — rest_id, title, preview_text, cover_image
            - "plain"   (~20 KB, default) — above + plain_text + media URL list
              + lifecycle_state. The LLM-friendly shape.
            - "full"    (~150 KB+) — raw GraphQL payload including the heavy
              content_state rich-block tree. Use only when you need it
              (rich-content rendering, archiving, structure analysis).
    """
    if format not in _ARTICLE_FORMATS:
        raise ToolError(
            f"format must be one of {'/'.join(_ARTICLE_FORMATS)}, got: {format!r}"
        )

    rest_id = _parse_article_url_or_id(article_id) or article_id
    client = await _get_client()

    # ── Hop 1: article rest_id → tweet rest_id ──────────────────────────
    # twikit's transport returns (response_json, raw_response) — see issue #12.
    redirect_url = (
        f"{_GRAPHQL_BASE}/{_ARTICLE_REDIRECT_QUERY_ID}/{_ARTICLE_REDIRECT_OP_NAME}"
    )
    redirect, _ = await client.gql.gql_get(
        redirect_url,
        {"articleEntityId": rest_id},
        {},
    )
    tweet_id = (
        (redirect or {})
        .get("data", {})
        .get("article_result_by_rest_id", {})
        .get("result", {})
        .get("metadata", {})
        .get("tweet_results", {})
        .get("rest_id")
    )
    if not tweet_id:
        raise ToolError(
            f"Article {rest_id} not found "
            f"(deleted, private, or not visible to this account)."
        )

    # ── Hop 2: tweet → article body ─────────────────────────────────────
    tweet_resp, _ = await client.gql.tweet_result_by_rest_id(tweet_id)
    article = (
        (tweet_resp or {})
        .get("data", {})
        .get("tweetResult", {})
        .get("result", {})
        .get("article", {})
        .get("article_results", {})
        .get("result")
    )
    if not article:
        raise ToolError(
            f"Tweet {tweet_id} did not return an article payload "
            f"(article may be unavailable)."
        )

    if format == "full":
        return _dumps(article)

    cover = article.get("cover_media", {}).get("media_info", {}).get("original_img_url")

    if format == "preview":
        out = {
            "rest_id": article.get("rest_id"),
            "title": article.get("title"),
            "preview_text": article.get("preview_text", ""),
            "cover_image": cover,
        }
    else:  # "plain"
        # Article media URLs live at media_entities[*].media_info.original_img_url
        # — NOT at the flat media_url_https / media_url that tweet schema uses
        # (issue #16). Drop entries where the URL can't be extracted so callers
        # don't see a list of nulls.
        media = []
        for m in article.get("media_entities") or []:
            url = ((m or {}).get("media_info") or {}).get("original_img_url")
            if url:
                media.append(url)
        out = {
            "rest_id": article.get("rest_id"),
            "title": article.get("title"),
            "preview_text": article.get("preview_text", ""),
            "plain_text": article.get("plain_text", ""),
            "cover_image": cover,
            "media": media,
            "lifecycle_state": article.get("lifecycle_state"),
        }
    return _dumps(out)


_VALID_NOTIFICATION_TYPES = frozenset({"All", "Verified", "Mentions"})


@mcp.tool()
async def block_user(screen_name: str) -> str:
    """Block a user by screen name.

    Note: X aggressively rate-limits / risk-scans block + mute. Avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        await client.block_user(user.id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")
    return _dumps({"user_id": user.id, "screen_name": screen_name, "status": "blocked"})


@mcp.tool()
async def unblock_user(screen_name: str) -> str:
    """Unblock a user by screen name.

    Note: X aggressively rate-limits / risk-scans block + mute. Avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        await client.unblock_user(user.id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")
    return _dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "unblocked"}
    )


@mcp.tool()
async def mute_user(screen_name: str) -> str:
    """Mute a user by screen name.

    Note: X aggressively rate-limits / risk-scans block + mute. Avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        await client.mute_user(user.id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")
    return _dumps({"user_id": user.id, "screen_name": screen_name, "status": "muted"})


@mcp.tool()
async def unmute_user(screen_name: str) -> str:
    """Unmute a user by screen name.

    Note: X aggressively rate-limits / risk-scans block + mute. Avoid bulk usage
    or your account may be temporarily restricted.

    Args:
        screen_name: Twitter username (without @).
    """
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        await client.unmute_user(user.id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")
    return _dumps({"user_id": user.id, "screen_name": screen_name, "status": "unmuted"})


@mcp.tool()
async def get_notifications(
    notification_type: str = "All",
    count: int = 40,
    cursor: str | None = None,
) -> str:
    """Fetch notifications (paginated).

    Args:
        notification_type: One of "All", "Verified", "Mentions" (default "All").
        count: Number to fetch (default 40, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if notification_type not in _VALID_NOTIFICATION_TYPES:
        raise ToolError(
            f"notification_type must be one of {sorted(_VALID_NOTIFICATION_TYPES)}, "
            f"got: {notification_type!r}"
        )
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_notifications(
            notification_type, count=count, cursor=cursor
        )
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")

    notifications = []
    for n in result:
        entry: dict = {
            "id": n.id,
            "timestamp_ms": n.timestamp_ms,
            "icon": n.icon,
            "message": n.message,
        }
        if n.tweet is not None:
            entry["tweet_id"] = n.tweet.id
        notifications.append(entry)

    return _dumps(
        {
            "notifications": notifications,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(notifications),
        }
    )


@mcp.tool()
async def send_dm(screen_name: str, text: str, media_id: str | None = None) -> str:
    """Send a direct message to a user by screen name.

    Note: Sends a PRIVATE message. Do not bulk-call. X has aggressive anti-spam
    on DMs and may suspend the account.

    Args:
        screen_name: Twitter username (without @) to send the DM to.
        text: Message content (required, must not be empty).
        media_id: Optional media ID to attach.
    """
    if not text.strip():
        raise ToolError("text must not be empty.")
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        message = await client.send_dm(user.id, text, media_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")
    return _dumps({"message_id": message.id, "status": "sent"})


@mcp.tool()
async def send_dm_to_group(
    group_id: str, text: str, media_id: str | None = None
) -> str:
    """Send a direct message to a group conversation.

    Note: Sends a PRIVATE message. Do not bulk-call. X has aggressive anti-spam
    on DMs and may suspend the account.

    Args:
        group_id: The group conversation ID.
        text: Message content (required, must not be empty).
        media_id: Optional media ID to attach.
    """
    if not text.strip():
        raise ToolError("text must not be empty.")
    client = await _get_client()
    try:
        message = await client.send_dm_to_group(group_id, text, media_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Group {group_id!r} not found.")
    return _dumps({"message_id": message.id, "status": "sent"})


@mcp.tool()
async def get_dm_history(screen_name: str, max_id: str | None = None) -> str:
    """Get DM conversation history with a user.

    Note: Retrieves PRIVATE messages. Do not bulk-call. X has aggressive
    anti-spam on DMs and may suspend the account.

    Args:
        screen_name: Twitter username (without @).
        max_id: If specified, retrieves messages older than this ID (for pagination).
            Pass the value from a previous response's `next_cursor` here on the
            next call to walk further back in time.
    """
    client = await _get_client()
    try:
        user = await client.get_user_by_screen_name(screen_name)
        result = await client.get_dm_history(user.id, max_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"User not found: {screen_name}.")

    messages = [
        {
            "id": m.id,
            "text": m.text[:500],
            "sender_id": m.sender_id,
            "recipient_id": m.recipient_id,
            "time": m.time,
        }
        for m in result
    ]
    return _dumps(
        {
            "messages": messages,
            "next_cursor": getattr(result, "next_cursor", None),
        }
    )


@mcp.tool()
async def delete_dm(message_id: str) -> str:
    """Delete a direct message by ID.

    Note: Deletes a PRIVATE message. Do not bulk-call. X has aggressive
    anti-spam on DMs and may suspend the account.

    Args:
        message_id: The message ID to delete.
    """
    client = await _get_client()
    try:
        await client.delete_dm(message_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Message {message_id} not found.")
    return _dumps({"message_id": message_id, "status": "deleted"})


def _list_to_dict(lst) -> dict:
    """Compact list dict used in list outputs.

    Truncates description to 200 chars (matches _user_to_dict pattern).
    `mode` is "Public" | "Private" in twikit's List model.
    """
    return {
        "id": lst.id,
        "name": lst.name,
        "description": (lst.description or "")[:200],
        "member_count": lst.member_count,
        "subscriber_count": lst.subscriber_count,
        "is_private": lst.mode == "Private",
        "created_at": str(lst.created_at),
    }


def _community_to_dict(c) -> dict:
    """Compact community dict used in community tool outputs.

    Truncates description to 200 chars (matches _user_to_dict / _list_to_dict).
    """
    return {
        "id": c.id,
        "name": c.name,
        "description": (c.description or "")[:200],
        "member_count": c.member_count,
        "is_member": c.is_member,
        "join_policy": c.join_policy,
        "created_at": str(c.created_at),
    }


def _community_member_to_dict(m) -> dict:
    """Compact dict for twikit's CommunityMember (members + moderators).

    CommunityMember is *not* a User — it lacks `description` / `followers_count`.
    Surfaces only the fields actually present on the model.
    """
    return {
        "id": m.id,
        "screen_name": m.screen_name,
        "name": m.name,
        "community_role": m.community_role,
        "verified": m.verified,
        "is_blue_verified": m.is_blue_verified,
        "protected": m.protected,
        "following": m.following,
        "followed_by": m.followed_by,
    }


@mcp.tool()
async def get_list(list_id: str) -> str:
    """Get a Twitter List by ID.

    Args:
        list_id: The list ID.
    """
    client = await _get_client()
    try:
        lst = await client.get_list(list_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"List {list_id} not found.")
    return _dumps(_list_to_dict(lst))


@mcp.tool()
async def get_lists(count: int = 20, cursor: str | None = None) -> str:
    """Get the authenticated user's Twitter Lists (paginated).

    Args:
        count: Number of lists to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_lists(count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    lists = [_list_to_dict(lst) for lst in result]
    return _dumps(
        {
            "lists": lists,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(lists),
        }
    )


@mcp.tool()
async def get_list_tweets(
    list_id: str, count: int = 20, cursor: str | None = None
) -> str:
    """Get tweets from a Twitter List (paginated).

    Args:
        list_id: The list ID.
        count: Number of tweets to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_list_tweets(list_id, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"List {list_id} not found.")
    tweets = [
        {
            "id": t.id,
            "author": t.user.screen_name,
            "text": t.text[:200],
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
        for t in result
    ]
    return _dumps(
        {
            "tweets": tweets,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(tweets),
        }
    )


@mcp.tool()
async def get_list_members(
    list_id: str, count: int = 20, cursor: str | None = None
) -> str:
    """Get members of a Twitter List (paginated).

    Args:
        list_id: The list ID.
        count: Number of members to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_list_members(list_id, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"List {list_id} not found.")
    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def get_list_subscribers(
    list_id: str, count: int = 20, cursor: str | None = None
) -> str:
    """Get subscribers of a Twitter List (paginated).

    Args:
        list_id: The list ID.
        count: Number of subscribers to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_list_subscribers(list_id, count=count, cursor=cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"List {list_id} not found.")
    users = [_user_to_dict(u) for u in result]
    return _dumps(
        {
            "users": users,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(users),
        }
    )


@mcp.tool()
async def create_list(
    name: str, description: str = "", is_private: bool = False
) -> str:
    """Create a new Twitter List.

    Args:
        name: The name for the new list (required, must not be empty).
        description: Description for the list (default empty).
        is_private: If True, the list is private (default False = public).
    """
    if not name.strip():
        raise ToolError("name must not be empty.")
    client = await _get_client()
    try:
        lst = await client.create_list(name, description, is_private)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    return _dumps(_list_to_dict(lst))


@mcp.tool()
async def edit_list(
    list_id: str,
    name: str | None = None,
    description: str | None = None,
    is_private: bool | None = None,
) -> str:
    """Edit a Twitter List's metadata.

    At least one of `name`, `description`, or `is_private` must be provided.
    Pass an empty string for `description` to clear it.

    Args:
        list_id: The list ID (required).
        name: New name for the list.
        description: New description (empty string clears it).
        is_private: True to make private, False to make public.
    """
    if name is None and description is None and is_private is None:
        raise ToolError("at least one of name/description/is_private must be provided.")
    client = await _get_client()
    try:
        lst = await client.edit_list(list_id, name, description, is_private)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"List {list_id} not found.")
    return _dumps(_list_to_dict(lst))


@mcp.tool()
async def add_list_member(
    list_id: str,
    screen_name: str | None = None,
    user_id: str | None = None,
) -> str:
    """Add a user to a Twitter List.

    Caller must provide exactly one of `screen_name` / `user_id`.

    Args:
        list_id: The list ID (required).
        screen_name: Twitter username (without @).
        user_id: Twitter numeric user ID.
    """
    _require_exactly_one(screen_name, user_id, op="add_list_member")
    client = await _get_client()
    try:
        uid = await _resolve_user_id(client, screen_name, user_id)
        lst = await client.add_list_member(list_id, uid)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Not found: list {list_id} or user {screen_name or user_id}.")
    return _dumps(_list_to_dict(lst))


@mcp.tool()
async def remove_list_member(
    list_id: str,
    screen_name: str | None = None,
    user_id: str | None = None,
) -> str:
    """Remove a user from a Twitter List.

    Caller must provide exactly one of `screen_name` / `user_id`.

    Args:
        list_id: The list ID (required).
        screen_name: Twitter username (without @).
        user_id: Twitter numeric user ID.
    """
    _require_exactly_one(screen_name, user_id, op="remove_list_member")
    client = await _get_client()
    try:
        uid = await _resolve_user_id(client, screen_name, user_id)
        lst = await client.remove_list_member(list_id, uid)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Not found: list {list_id} or user {screen_name or user_id}.")
    return _dumps(_list_to_dict(lst))


@mcp.tool()
async def create_scheduled_tweet(
    scheduled_at: int,
    text: str = "",
    media_ids: list[str] | None = None,
) -> str:
    """Schedule a tweet to be posted at a future Unix timestamp.

    Scheduled tweets follow X's standard rate limits, no special caveats needed.

    Args:
        scheduled_at: Unix epoch seconds when the tweet should be posted (must be in the future).
        text: Tweet text. At least one of text or media_ids must be provided.
        media_ids: List of media IDs to attach to the scheduled tweet.
    """
    if scheduled_at <= int(time.time()):
        raise ToolError("scheduled_at must be a future Unix timestamp.")
    if not text.strip() and not media_ids:
        raise ToolError(
            "at least one of text or media_ids must be provided (empty tweet)."
        )
    client = await _get_client()
    try:
        tweet_id = await client.create_scheduled_tweet(scheduled_at, text, media_ids)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    return _dumps(
        {
            "scheduled_tweet_id": tweet_id,
            "scheduled_at": scheduled_at,
            "status": "scheduled",
        }
    )


@mcp.tool()
async def get_scheduled_tweets() -> str:
    """Return all scheduled tweets for the authenticated user.

    Note: returns the FULL list in one call — twikit's API does not paginate
    scheduled tweets. This is fine in practice since X caps scheduled tweets
    per account at a small number.

    Scheduled tweets follow X's standard rate limits, no special caveats needed.
    """
    client = await _get_client()
    try:
        tweets = await client.get_scheduled_tweets()
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    result = [
        {
            "id": t.id,
            "text": t.text[:200],
            "scheduled_at": t.execute_at,
            "state": t.state,
            "media_count": len(t.media),
        }
        for t in tweets
    ]
    return _dumps({"scheduled_tweets": result, "count": len(result)})


@mcp.tool()
async def delete_scheduled_tweet(scheduled_tweet_id: str) -> str:
    """Delete a scheduled tweet by its scheduled tweet ID.

    Scheduled tweets follow X's standard rate limits, no special caveats needed.

    Args:
        scheduled_tweet_id: The ID of the scheduled tweet (from create_scheduled_tweet
            or get_scheduled_tweets). This is NOT a regular tweet ID.
    """
    if not scheduled_tweet_id:
        raise ToolError("scheduled_tweet_id must be non-empty.")
    client = await _get_client()
    try:
        await client.delete_scheduled_tweet(scheduled_tweet_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Scheduled tweet {scheduled_tweet_id} not found.")
    return _dumps({"scheduled_tweet_id": scheduled_tweet_id, "status": "deleted"})


@mcp.tool()
async def create_poll(choices: list[str], duration_minutes: int) -> str:
    """Create an X poll and return its card URI.

    X polls have 2-4 choices and a duration in minutes.
    Pass the returned card_uri to send_tweet's poll_uri parameter to attach the poll.

    Args:
        choices: Poll choices (2-4 entries required; each must be non-empty).
        duration_minutes: Poll duration in minutes (must be > 0).
    """
    if len(choices) not in (2, 3, 4):
        raise ToolError(
            "choices must have 2, 3, or 4 entries (X polls allow 2-4 options)."
        )
    if duration_minutes <= 0:
        raise ToolError("duration_minutes must be greater than 0.")
    if duration_minutes > 10_080:
        raise ToolError(
            "duration_minutes cannot exceed 10080 (7 days — X poll maximum)."
        )
    for choice in choices:
        if not choice.strip():
            raise ToolError("all poll choices must be non-empty.")
        if len(choice) > 25:
            raise ToolError(f"poll choice {choice!r} exceeds X's 25-character limit.")
    client = await _get_client()
    try:
        card_uri = await client.create_poll(choices, duration_minutes)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    return _dumps({"card_uri": card_uri, "status": "created"})


@mcp.tool()
async def vote(
    selected_choice: str,
    card_uri: str,
    tweet_id: str,
    card_name: str,
) -> str:
    """Vote on an X poll.

    X polls have 2-4 choices and a duration in minutes.
    The card_uri and card_name come from the tweet's poll card metadata (obtainable via get_tweet).

    Args:
        selected_choice: The label of the choice to vote for (must be non-empty).
        card_uri: The poll card URI (from the tweet's poll card metadata).
        tweet_id: The ID of the tweet containing the poll.
        card_name: The name of the poll card (from the tweet's poll card metadata).
    """
    if not selected_choice.strip():
        raise ToolError("selected_choice must be non-empty.")
    if not card_uri:
        raise ToolError("card_uri must be non-empty.")
    if not card_name:
        raise ToolError("card_name must be non-empty.")
    if not tweet_id:
        raise ToolError("tweet_id must be non-empty.")
    client = await _get_client()
    try:
        await client.vote(selected_choice, card_uri, tweet_id, card_name)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Tweet {tweet_id} or poll card not found.")
    return _dumps(
        {"tweet_id": tweet_id, "selected_choice": selected_choice, "status": "voted"}
    )


@mcp.tool()
async def get_community(community_id: str) -> str:
    """Get a Twitter Community by ID.

    Args:
        community_id: The community ID.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    client = await _get_client()
    try:
        community = await client.get_community(community_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    return _dumps(_community_to_dict(community))


@mcp.tool()
async def search_community(query: str, cursor: str | None = None) -> str:
    """Search for Twitter Communities by query (paginated).

    Note: twikit's search_community does not support a count parameter.

    Args:
        query: Search query string.
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not query.strip():
        raise ToolError("query must not be empty.")
    client = await _get_client()
    try:
        result = await client.search_community(query, cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    communities = [_community_to_dict(c) for c in result]
    return _dumps(
        {
            "communities": communities,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(communities),
        }
    )


@mcp.tool()
async def get_community_tweets(
    community_id: str,
    tweet_type: str,
    count: int = 40,
    cursor: str | None = None,
) -> str:
    """Get tweets from a Twitter Community (paginated).

    Args:
        community_id: The community ID.
        tweet_type: One of "Top", "Latest", or "Media".
        count: Number of tweets to fetch (default 40, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    if tweet_type not in _VALID_COMMUNITY_TWEET_TYPES:
        raise ToolError(
            f"tweet_type must be one of {sorted(_VALID_COMMUNITY_TWEET_TYPES)}, "
            f"got: {tweet_type!r}"
        )
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_community_tweets(
            community_id, tweet_type, count, cursor
        )
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    tweets = [
        {
            "id": t.id,
            "author": t.user.screen_name,
            "text": t.text[:200],
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
        for t in result
    ]
    return _dumps(
        {
            "tweets": tweets,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(tweets),
        }
    )


@mcp.tool()
async def get_communities_timeline(count: int = 20, cursor: str | None = None) -> str:
    """Get tweets from communities the authenticated user has joined (paginated).

    Args:
        count: Number of tweets to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_communities_timeline(count, cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    tweets = [
        {
            "id": t.id,
            "author": t.user.screen_name,
            "text": t.text[:200],
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
        for t in result
    ]
    return _dumps(
        {
            "tweets": tweets,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(tweets),
        }
    )


@mcp.tool()
async def get_community_members(
    community_id: str, count: int = 20, cursor: str | None = None
) -> str:
    """Get members of a Twitter Community (paginated).

    Args:
        community_id: The community ID.
        count: Number of members to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_community_members(community_id, count, cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    members = [_community_member_to_dict(m) for m in result]
    return _dumps(
        {
            "members": members,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(members),
        }
    )


@mcp.tool()
async def get_community_moderators(
    community_id: str, count: int = 20, cursor: str | None = None
) -> str:
    """Get moderators of a Twitter Community (paginated).

    Args:
        community_id: The community ID.
        count: Number of moderators to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.get_community_moderators(community_id, count, cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    moderators = [_community_member_to_dict(m) for m in result]
    return _dumps(
        {
            "moderators": moderators,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(moderators),
        }
    )


@mcp.tool()
async def search_community_tweet(
    community_id: str,
    query: str,
    count: int = 20,
    cursor: str | None = None,
) -> str:
    """Search tweets within a Twitter Community (paginated).

    Args:
        community_id: The community ID.
        query: Search query string.
        count: Number of tweets to fetch (default 20, max 100).
        cursor: Pagination cursor from a previous response's `next_cursor`.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    if not query.strip():
        raise ToolError("query must not be empty.")
    if count < 1:
        raise ToolError("count must be >= 1.")
    if count > _PAGINATED_MAX_COUNT:
        raise ToolError(
            f"count exceeds the {_PAGINATED_MAX_COUNT} cap; paginate via `cursor` instead."
        )
    client = await _get_client()
    try:
        result = await client.search_community_tweet(community_id, query, count, cursor)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    tweets = [
        {
            "id": t.id,
            "author": t.user.screen_name,
            "text": t.text[:200],
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
        for t in result
    ]
    return _dumps(
        {
            "tweets": tweets,
            "next_cursor": getattr(result, "next_cursor", None),
            "count": len(tweets),
        }
    )


@mcp.tool()
async def join_community(community_id: str) -> str:
    """Join a Twitter Community.

    Args:
        community_id: The community ID to join.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    client = await _get_client()
    try:
        community = await client.join_community(community_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    return _dumps({**_community_to_dict(community), "status": "joined"})


@mcp.tool()
async def leave_community(community_id: str) -> str:
    """Leave a Twitter Community.

    Args:
        community_id: The community ID to leave.
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    client = await _get_client()
    try:
        community = await client.leave_community(community_id)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    return _dumps({**_community_to_dict(community), "status": "left"})


@mcp.tool()
async def request_to_join_community(
    community_id: str, answer: str | None = None
) -> str:
    """Request to join a Twitter Community.

    For communities with restricted join policies that require moderator
    approval, an `answer` to the join request question may be required.

    Args:
        community_id: The community ID to request to join.
        answer: Optional answer to the join request question (required for
            some communities with moderator approval policy).
    """
    if not community_id:
        raise ToolError("community_id must be non-empty.")
    client = await _get_client()
    try:
        await client.request_to_join_community(community_id, answer)
    except TooManyRequests as e:
        raise ToolError(f"X rate limit exceeded; retry later. ({e})")
    except NotFound:
        raise ToolError(f"Community {community_id} not found.")
    return _dumps({"community_id": community_id, "status": "request_sent"})


def _get_version() -> str:
    """Read the installed package version, falling back to 'unknown'."""
    try:
        return _pkg_version("twikit-mcp")
    except PackageNotFoundError:
        return "unknown"


# ── CLI mode ──────────────────────────────────────────
#
# `twikit-mcp` is dual-mode:
#   - Default (no subcommand) / `serve` → MCP server over stdio. Backward
#     compatible with every existing client config in the wild.
#   - `list` → print the names of all registered tools, one per line.
#   - `call <tool> [key=value …]` → invoke that tool and print the JSON
#     output, useful for shell scripts + interactive debugging without
#     needing an MCP client wired up.
#
# Tool args come in as strings (`count=5`); we coerce them to the type
# declared on the tool's Python signature. Bools accept loose forms
# (true/false/1/0/yes/no). `Optional[X] = None` and `X | None` both
# unwrap to the inner type. Unknown args raise a clear error naming
# the legal set.


def _coerce(value: str, annotation):
    """Cast a CLI string to the annotation's expected Python type.

    Handles the annotation forms our tools actually use:
      - `str` (passthrough), `int`, `float`, `bool`
      - `Optional[X]` / `X | None` (PEP 604 union with None)
      - any unknown/fancy annotation → return the raw string
    """
    # Empty / unspecified annotation → pass through.
    if annotation is inspect.Parameter.empty or annotation is str:
        return value
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        return value.strip().lower() in ("true", "1", "yes", "y", "on")

    # PEP 604 union (`int | None`) and typing.Union[...]: unwrap to a
    # non-None member and recurse. NoneType is dropped — passing
    # `--key=` as the empty string is the way to send None explicitly.
    origin = typing.get_origin(annotation)
    if origin is typing.Union or isinstance(annotation, types.UnionType):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        if value == "" and len(members) < len(typing.get_args(annotation)):
            return None
        for m in members:
            try:
                return _coerce(value, m)
            except (TypeError, ValueError):
                continue
    # Fallback: pass the raw string. Any tool-side validation will
    # surface a clean ToolError if needed.
    return value


def _list_tools_text() -> str:
    """Sorted tool names, one per line."""
    return "\n".join(sorted(mcp._tool_manager._tools))


async def _call_tool_async(tool_name: str, raw_kwargs: dict[str, str]) -> str:
    """Look up a tool, coerce kwargs, await it, return its string output."""
    tools = mcp._tool_manager._tools
    if tool_name not in tools:
        raise SystemExit(
            f"Unknown tool: {tool_name!r}. Run `twikit-mcp list` to see "
            f"the available {len(tools)} tools."
        )
    tool = tools[tool_name]
    fn = getattr(tool, "fn", None) or getattr(tool, "func", None) or tool
    sig = inspect.signature(fn)
    coerced: dict[str, object] = {}
    for k, v in raw_kwargs.items():
        if k not in sig.parameters:
            raise SystemExit(
                f"Unknown arg `{k}` for tool `{tool_name}`. "
                f"Valid args: {list(sig.parameters)}"
            )
        coerced[k] = _coerce(v, sig.parameters[k].annotation)
    return await fn(**coerced)


def _parse_kv_pairs(items: list[str]) -> dict[str, str]:
    """Parse the `key=value` positional args from `twikit-mcp call`."""
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(
                f"Bad arg form: {item!r}. Use `key=value` (e.g. screen_name=elonmusk)."
            )
        k, v = item.split("=", 1)
        out[k] = v
    return out


# ── Human-friendly CLI formatters ─────────────────────
#
# These are used by the `tweet` / `user` / `tl` / `search` / `trends`
# subcommands. They take the tool's already-decoded dict (or list-of-
# dicts) output and render plain text for terminal reading. No external
# deps (no `rich` etc.) — keeps install tiny.


def _compact_num(n) -> str:
    """1234567 → '1.2M' / 12500 → '12.5K' / small numbers unchanged."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


# ── TTY-aware card rendering (issue #61, #68) ────────
#
# When stdout is a tty, human subcommands render boxed cards (Twitter-
# like UI) via [Rich](https://github.com/Textualize/rich) — gives us
# correct emoji/CJK cell-width math, OSC 8 clickable hyperlinks, and a
# theme-friendly look. When piped, fall back to plain text so `| jq` /
# `> file` keep the byte-for-byte format users already script against.


def _is_tty() -> bool:
    """Wrap `sys.stdout.isatty()` so tests can monkeypatch a single source."""
    import sys as _sys

    return _sys.stdout.isatty()


def _term_width() -> int:
    """Card width: clamp to 60..100. <60 is unreadable, >100 is showy."""
    import shutil as _shutil

    return min(max(_shutil.get_terminal_size().columns, 60), 100)


def _rich_render(renderable, width: int) -> str:
    """Render a Rich `renderable` to string at fixed `width`.

    `NO_COLOR=1` → `color_system=None` strips CSI styling entirely
    (including bold / dim attributes, which Rich's `no_color=True` would
    otherwise keep). OSC 8 hyperlinks are always emitted in TTY mode.
    """
    from io import StringIO

    from rich.console import Console

    no_color = bool(os.environ.get("NO_COLOR"))
    buf = StringIO()
    Console(
        file=buf,
        width=width,
        force_terminal=True,
        no_color=no_color,
        color_system=None if no_color else "truecolor",
        emoji=False,
        legacy_windows=False,
    ).print(renderable, end="")
    return buf.getvalue().rstrip("\n")


def _link_text(url: str, label: str | None = None, style: str = "dim") -> object:
    """Build a `Text` styled `url` (or `label`) with an OSC 8 hyperlink to
    `url`. Rendered as `\\x1b]8;;<url>\\x1b\\\\<label>\\x1b]8;;\\x1b\\\\` by Rich."""
    from rich.text import Text

    txt = Text(label if label is not None else url, style=style)
    txt.stylize(f"link {url}")
    return txt


def _card_tweet(t: dict, width: int) -> str:
    from rich.box import ROUNDED
    from rich.console import Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    author = t.get("author", "?")
    name = t.get("author_name", "")
    body = (t.get("text") or "").strip()
    created = t.get("created_at", "")
    likes = _compact_num(t.get("likes", 0))
    rts = _compact_num(t.get("retweets", 0))
    tid = t.get("id", "")
    url = f"https://x.com/{author}/status/{tid}" if author and tid else ""

    header = Text()
    if name:
        header.append(name + " · ", style="bold")
    header.append(f"@{author}", style="bold cyan")

    items: list = [header]
    if created:
        items.append(Text(created, style="dim"))
    items.append(Rule(style="dim"))
    items.append(Text(body) if body else Text(""))
    items.append(Rule(style="dim"))
    counts = Text.assemble(
        ("❤ ", "red"),
        (likes, "bold"),
        "    ",
        ("🔁 ", "green"),
        (rts, "bold"),
    )
    items.append(counts)
    if url:
        items.append(_link_text(url))

    panel = Panel(
        Group(*items),
        width=width,
        box=ROUNDED,
        border_style="cyan",
        padding=(0, 1),
    )
    return _rich_render(panel, width)


def _card_user(u: dict, width: int) -> str:
    from rich.box import ROUNDED
    from rich.console import Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    sn = u.get("screen_name", "?")
    name = u.get("name", "")
    verified = "✓" if u.get("is_blue_verified") or u.get("verified") else ""
    desc = (u.get("description") or "").strip()
    fc = _compact_num(u.get("followers_count", 0))
    fg = _compact_num(u.get("following_count", 0))
    tw = _compact_num(u.get("tweets_count", 0))
    location = u.get("location") or ""
    bio_url = u.get("url") or ""
    created = u.get("created_at", "")

    header = Text()
    if name:
        header.append(name + " · ", style="bold")
    header.append(f"@{sn}", style="bold cyan")
    if verified:
        header.append("  ✓", style="bold blue")

    items: list = [header, Rule(style="dim")]
    if desc:
        items.append(Text(desc))
        items.append(Rule(style="dim"))

    stats = Table.grid(padding=(0, 4))
    stats.add_column(style="dim")
    stats.add_column(style="bold")
    stats.add_row("Followers", fc)
    stats.add_row("Following", fg)
    stats.add_row("Posts", tw)
    items.append(stats)

    meta = Table.grid(padding=(0, 4))
    meta.add_column(style="dim")
    meta.add_column()
    if location:
        meta.add_row("📍", location)
    if created:
        meta.add_row("Joined", created)
    if location or created:
        items.append(meta)

    items.append(Rule(style="dim"))
    items.append(_link_text(f"https://x.com/{sn}"))
    if bio_url:
        link_row = Table.grid(padding=(0, 1))
        link_row.add_column(style="dim")
        link_row.add_column()
        link_row.add_row("Link", _link_text(bio_url))
        items.append(link_row)

    panel = Panel(
        Group(*items),
        width=width,
        box=ROUNDED,
        border_style="cyan",
        padding=(0, 1),
    )
    return _rich_render(panel, width)


def _card_trends(payload: dict, width: int) -> str:
    from rich.box import ROUNDED
    from rich.table import Table

    trends = payload.get("trends") or []
    if not trends:
        return "(no trends)"

    table = Table(
        title="Trending",
        title_style="bold",
        box=ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        width=width,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", justify="right", no_wrap=True)
    table.add_column("Trend", style="bold")
    table.add_column("Tweets", style="green", justify="right", no_wrap=True)
    table.add_column("Context", style="dim")

    for i, t in enumerate(trends, 1):
        nm = t.get("name", "?")
        cnt = t.get("tweets_count")
        ctx = t.get("domain_context") or ""
        cnt_str = _compact_num(cnt) if cnt else ""
        table.add_row(str(i), nm, cnt_str, ctx)

    return _rich_render(table, width)


def _format_tweet(t: dict) -> str:
    """One tweet block. TTY → boxed card; piped → plain text (issue #61)."""
    if _is_tty():
        return _card_tweet(t, _term_width())

    # Plain (pre-#61, byte-stable for jq / file pipelines).
    author = t.get("author", "?")
    name = t.get("author_name", "")
    header = f"@{author}" + (f" · {name}" if name else "")
    text = (t.get("text") or "").strip()
    created = t.get("created_at", "")
    likes = _compact_num(t.get("likes", 0))
    rts = _compact_num(t.get("retweets", 0))
    tid = t.get("id", "")
    url = f"https://x.com/{author}/status/{tid}" if author and tid else ""
    parts = [header, text, f"❤ {likes}  🔁 {rts}  · {created}"]
    if url:
        parts.append(url)
    return "\n".join(p for p in parts if p)


def _format_tweet_list(tweets: list[dict]) -> str:
    """Numbered tweets separated by blank lines."""
    if not tweets:
        return "(no tweets)"
    blocks = []
    for i, t in enumerate(tweets, 1):
        blocks.append(f"[{i}] " + _format_tweet(t))
    return "\n\n".join(blocks)


def _format_user(u: dict) -> str:
    """One user profile block. TTY → boxed card; piped → plain (issue #61)."""
    if _is_tty():
        return _card_user(u, _term_width())

    sn = u.get("screen_name", "?")
    name = u.get("name", "")
    verified = "✓" if u.get("is_blue_verified") or u.get("verified") else ""
    header = f"@{sn}" + (f" · {name}" if name else "")
    if verified:
        header += f" {verified}"
    desc = (u.get("description") or "").strip()
    fc = _compact_num(u.get("followers_count", 0))
    fg = _compact_num(u.get("following_count", 0))
    tw = _compact_num(u.get("tweets_count", 0))
    location = u.get("location") or ""
    url = u.get("url") or ""
    created = u.get("created_at", "")
    line2 = f"Followers: {fc}   Following: {fg}   Posts: {tw}"
    line3_bits = []
    if location:
        line3_bits.append(f"📍 {location}")
    if created:
        line3_bits.append(f"Joined: {created}")
    parts = [header, desc, line2]
    if line3_bits:
        parts.append("   ".join(line3_bits))
    parts.append(f"https://x.com/{sn}")
    if url:
        parts.append(f"Link: {url}")
    return "\n".join(p for p in parts if p)


def _format_trends(payload: dict) -> str:
    """Numbered trend list. TTY → boxed card; piped → plain (issue #61)."""
    if _is_tty():
        return _card_trends(payload, _term_width())

    trends = payload.get("trends") or []
    if not trends:
        return "(no trends)"
    out = []
    for i, t in enumerate(trends, 1):
        nm = t.get("name", "?")
        cnt = t.get("tweets_count")
        ctx = t.get("domain_context") or ""
        line = f"{i:>2}. {nm}"
        if cnt:
            line += f"  ({_compact_num(cnt)} tweets)"
        if ctx:
            line += f"  — {ctx}"
        out.append(line)
    return "\n".join(out)


async def _human_tweet(id_or_url: str) -> str:
    raw = await _call_tool_async("get_tweet", {"tweet_id": id_or_url})
    import json as _stdlib_json

    return _format_tweet(_stdlib_json.loads(raw))


async def _human_user(screen_name: str) -> str:
    raw = await _call_tool_async("get_user_info", {"screen_name": screen_name})
    import json as _stdlib_json

    return _format_user(_stdlib_json.loads(raw))


async def _human_timeline(count: int) -> str:
    raw = await _call_tool_async("get_timeline", {"count": str(count)})
    import json as _stdlib_json

    return _format_tweet_list(_stdlib_json.loads(raw))


async def _human_search(query: str, count: int) -> str:
    raw = await _call_tool_async(
        "search_tweets", {"query": query, "count": str(count), "product": "Top"}
    )
    import json as _stdlib_json

    return _format_tweet_list(_stdlib_json.loads(raw))


async def _human_trends(count: int) -> str:
    raw = await _call_tool_async(
        "get_trends", {"category": "trending", "count": str(count)}
    )
    import json as _stdlib_json

    return _format_trends(_stdlib_json.loads(raw))


async def _human_video(tweet_id: str, output_dir: str | None) -> str:
    """CLI dispatch for `twikit-mcp video <id>`. Calls the tool, formats
    a one-line summary: 'Saved 5.0 MB / 23s mp4 → /path/to/file'."""
    raw = await download_tweet_video(tweet_id=tweet_id, output_dir=output_dir)
    import json as _stdlib_json

    info = _stdlib_json.loads(raw)
    size = info.get("size_bytes") or 0
    mb = size / (1024 * 1024)
    dur = info.get("duration_sec")
    dur_str = f"{int(dur)}s" if dur else "—"
    fmt = (info.get("format") or "").rsplit("/", 1)[-1] or "?"
    return f"Saved {mb:.1f} MB / {dur_str} {fmt} → {info['path']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="twikit-mcp",
        description=(
            "Twitter/X MCP server — twikit-based, no API key needed. "
            "Default mode runs the MCP server over stdio; subcommands "
            "give a one-shot CLI for scripts + debugging."
        ),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"twikit-mcp {_get_version()}",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser(
        "serve",
        help="Run as an MCP server over stdio (default when no subcommand given).",
    )
    sub.add_parser(
        "list",
        help="List the names of all registered MCP tools, one per line.",
    )
    p_call = sub.add_parser(
        "call",
        help="Invoke a single tool from the CLI. Args use key=value form.",
        description=(
            "Invoke a tool. Args are key=value pairs whose names match the "
            "tool's Python signature. Type coercion: int / float / bool from "
            "their string forms; bool accepts true|false|1|0|yes|no. "
            "Example: twikit-mcp call get_user_info screen_name=elonmusk"
        ),
    )
    p_call.add_argument("tool", help="Tool name (see `twikit-mcp list`).")
    p_call.add_argument(
        "kwargs",
        nargs="*",
        metavar="KEY=VALUE",
        help="Zero or more arguments in key=value form.",
    )

    # ── Human-friendly subcommands ────────────────────
    # Same underlying tools as `call`, but with positional args + pretty
    # text output (no raw JSON). For when you want to read X in the shell.
    p_tweet = sub.add_parser(
        "tweet",
        help="Pretty-print a single tweet by ID or URL.",
        description="Example: twikit-mcp tweet 20",
    )
    p_tweet.add_argument("id_or_url", help="Tweet ID (numeric) or full x.com URL.")

    p_user = sub.add_parser(
        "user",
        help="Pretty-print a user's profile.",
        description="Example: twikit-mcp user elonmusk",
    )
    p_user.add_argument("screen_name", help="Twitter username (without @).")

    p_tl = sub.add_parser(
        "tl",
        help="Pretty-print your home timeline (cookie identity).",
        description="Example: twikit-mcp tl 10",
    )
    p_tl.add_argument(
        "count", nargs="?", default=20, type=int, help="Number of tweets (default 20)."
    )

    p_search = sub.add_parser(
        "search",
        help="Pretty-print Top search results.",
        description='Example: twikit-mcp search "AI" 5',
    )
    p_search.add_argument("query", help="Search query string.")
    p_search.add_argument(
        "count", nargs="?", default=10, type=int, help="Number of results (default 10)."
    )

    p_trends = sub.add_parser(
        "trends",
        help="Pretty-print global trending topics.",
        description="Example: twikit-mcp trends 10",
    )
    p_trends.add_argument(
        "count", nargs="?", default=20, type=int, help="Number of trends (default 20)."
    )

    p_video = sub.add_parser(
        "video",
        help="Download video from a tweet via yt-dlp.",
        description=(
            "Download tweet video to disk. Requires `yt-dlp` on PATH "
            "(install: `uv tool install yt-dlp`). Example: "
            "twikit-mcp video 1234567890 -o ~/Movies"
        ),
    )
    p_video.add_argument("tweet_id", help="Tweet ID (numeric) or full x.com URL.")
    p_video.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help=(
            "Where to save (default: $TWIKIT_DOWNLOAD_DIR or ~/Downloads/twikit-mcp/)."
        ),
    )

    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(_list_tools_text())
        return 0

    if args.cmd == "call":
        kwargs = _parse_kv_pairs(args.kwargs)
        try:
            out = asyncio.run(_call_tool_async(args.tool, kwargs))
        except ToolError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(2)
        print(out)
        return 0

    # Human-friendly read paths. All share the same ToolError → stderr +
    # exit-2 handling as `call`.
    _human_dispatch = {
        "tweet": lambda a: _human_tweet(a.id_or_url),
        "user": lambda a: _human_user(a.screen_name),
        "tl": lambda a: _human_timeline(a.count),
        "search": lambda a: _human_search(a.query, a.count),
        "trends": lambda a: _human_trends(a.count),
        "video": lambda a: _human_video(a.tweet_id, a.output_dir),
    }
    if args.cmd in _human_dispatch:
        try:
            out = asyncio.run(_human_dispatch[args.cmd](args))
        except ToolError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(2)
        print(out)
        return 0

    # Default / `serve` → existing MCP server behavior.
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    main()
