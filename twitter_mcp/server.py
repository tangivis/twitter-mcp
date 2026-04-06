"""Twitter MCP Server - twikit-based, no API key needed."""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from twikit import Client

mcp = FastMCP("twitter")

# Cookies 路径: 环境变量 > 默认路径
COOKIES_PATH = Path(
    os.environ.get(
        "TWITTER_COOKIES",
        os.path.expanduser("~/.config/twitter-mcp/cookies.json"),
    )
)


async def _get_client() -> Client:
    """Create an authenticated twikit client."""
    cookies = json.loads(COOKIES_PATH.read_text())
    client = Client("en")
    client.set_cookies(
        {"auth_token": cookies["auth_token"], "ct0": cookies["ct0"]}
    )
    return client


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
    # Handle full URL input
    if "/" in tweet_id:
        tweet_id = tweet_id.rstrip("/").split("/")[-1]

    client = await _get_client()
    tweets = await client.get_tweets_by_ids([tweet_id])
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
async def search_tweets(
    query: str, count: int = 20, product: str = "Latest"
) -> str:
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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
