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

# Article GraphQL endpoint (issue #7).
# `TwitterArticleByRestId` was renamed; the new op is `ArticleEntityResultByRestId`
# served from the `bundle.TwitterArticles.*.js` chunk on abs.twimg.com.
# Refresh the queryId the same way every other twikit Endpoint constant is
# refreshed when X rotates a hash (manual capture from the public bundle).
_ARTICLE_QUERY_ID = "8-OHhj8-KCAHUP8XjPaAYQ"
_ARTICLE_OP_NAME = "ArticleEntityResultByRestId"
_ARTICLE_FEATURES = {
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
_ARTICLE_FIELD_TOGGLES = {
    "withPayments": False,
    "withAuxiliaryUserLabels": False,
}


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


@mcp.tool()
async def get_article(article_id: str) -> str:
    """Fetch the full body of an X Article (long-form post) via GraphQL.

    Calls the persisted GraphQL operation `ArticleEntityResultByRestId` with
    a hardcoded queryId (refresh it from the public `bundle.TwitterArticles.*.js`
    chunk if X rotates the hash). Requires authentication via cookies — same as
    every other authenticated tool here.

    Args:
        article_id: Article rest_id (numeric string) or full /i/article/<id> URL.
    """
    rest_id = _parse_article_url_or_id(article_id) or article_id
    variables = {"articleId": rest_id}
    url = f"{_GRAPHQL_BASE}/{_ARTICLE_QUERY_ID}/{_ARTICLE_OP_NAME}"
    client = await _get_client()
    result = await client.gql.gql_get(
        url,
        variables,
        _ARTICLE_FEATURES,
        extra_params={"fieldToggles": _ARTICLE_FIELD_TOGGLES},
    )
    return json.dumps(result)


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
