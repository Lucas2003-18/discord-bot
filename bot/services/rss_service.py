import feedparser
import logging

log = logging.getLogger(__name__)

FEEDS = {
    "hackernews": "https://news.ycombinator.com/rss",
    "devto_python": "https://dev.to/feed/tag/python",
    "devto_fastapi": "https://dev.to/feed/tag/fastapi",
}


def get_hn_top(limit: int = 5) -> list[dict] | None:
    try:
        feed = feedparser.parse(FEEDS["hackernews"])
        return [
            {"title": e.title, "url": e.link}
            for e in feed.entries[:limit]
        ]
    except Exception as e:
        log.error("rss_service HN error: %s", e)
        return None


def get_devto_top(limit: int = 3) -> list[dict] | None:
    try:
        seen_titles: set[str] = set()
        articles = []
        for feed_url in (FEEDS["devto_python"], FEEDS["devto_fastapi"]):
            feed = feedparser.parse(feed_url)
            for e in feed.entries:
                if e.title not in seen_titles:
                    seen_titles.add(e.title)
                    articles.append({"title": e.title, "url": e.link})
                if len(articles) >= limit:
                    break
            if len(articles) >= limit:
                break
        return articles
    except Exception as e:
        log.error("rss_service dev.to error: %s", e)
        return None
