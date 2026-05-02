"""Twitter MCP Server - twikit-based, no API key needed."""

import argparse
import json
import os
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp._vendor.twikit import Client

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
    return json.dumps({"id": tweet.id, "text": text, "status": "sent"})


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
    return json.dumps(
        {
            "id": t.id,
            "author": t.user.screen_name,
            "author_name": t.user.name,
            "text": t.text,
            "created_at": str(t.created_at),
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
    )


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
    return json.dumps(result)


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
    return json.dumps(result)


@mcp.tool()
async def like_tweet(tweet_id: str) -> str:
    """Like a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.favorite_tweet(tweet_id)
    return json.dumps({"tweet_id": tweet_id, "status": "liked"})


@mcp.tool()
async def retweet(tweet_id: str) -> str:
    """Retweet a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.retweet(tweet_id)
    return json.dumps({"tweet_id": tweet_id, "status": "retweeted"})


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
    return json.dumps(result)


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
    return json.dumps(
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
    return json.dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "unfollowed"}
    )


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
    return json.dumps(
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
        return json.dumps(article, ensure_ascii=False)

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
    return json.dumps(out, ensure_ascii=False)


def _get_version() -> str:
    """Read the installed package version, falling back to 'unknown'."""
    try:
        return _pkg_version("twikit-mcp")
    except PackageNotFoundError:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(
        prog="twikit-mcp",
        description="Twitter/X MCP server — twikit-based, no API key needed.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"twikit-mcp {_get_version()}",
    )
    parser.parse_args()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
