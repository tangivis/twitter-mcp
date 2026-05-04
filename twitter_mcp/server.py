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


_PAGINATED_MAX_COUNT = 100

_VALID_TREND_CATEGORIES = frozenset(
    {"trending", "for-you", "news", "sports", "entertainment"}
)


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

    return json.dumps(
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
            "profile_image_url": u.profile_image_url_https,
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
    return json.dumps(
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
    return json.dumps(
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
    return json.dumps({"tweet_id": tweet_id, "status": "deleted"})


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
    return json.dumps({"tweet_id": tweet_id, "status": "unliked"})


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
    return json.dumps({"tweet_id": tweet_id, "status": "un-retweeted"})


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
    return json.dumps(result)


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
    return json.dumps({"tweet_id": tweet_id, "status": "un-bookmarked"})


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
    return json.dumps(
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
    return json.dumps(
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
    return json.dumps(
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
    return json.dumps(
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
    return json.dumps({"trends": result, "category": category})


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
    return json.dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "blocked"}
    )


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
    return json.dumps(
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
    return json.dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "muted"}
    )


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
    return json.dumps(
        {"user_id": user.id, "screen_name": screen_name, "status": "unmuted"}
    )


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

    return json.dumps(
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
    return json.dumps({"message_id": message.id, "status": "sent"})


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
    return json.dumps({"message_id": message.id, "status": "sent"})


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
    return json.dumps(
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
    return json.dumps({"message_id": message_id, "status": "deleted"})


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
