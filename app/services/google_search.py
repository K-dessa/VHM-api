import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import re

import httpx
import structlog

from app.core.config import settings


logger = structlog.get_logger(__name__)


class GoogleSearchClient:
    """Lightweight client for Google Custom Search JSON API.

    Requires `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` in settings.
    """

    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        if not settings.GOOGLE_SEARCH_API_KEY or not settings.GOOGLE_SEARCH_ENGINE_ID:
            raise ValueError("Google Search API not configured")

        self.api_key = settings.GOOGLE_SEARCH_API_KEY
        self.cx = settings.GOOGLE_SEARCH_ENGINE_ID
        self.timeout = settings.EXTERNAL_SERVICE_TIMEOUT or 5

    async def search(
        self,
        query: str,
        num: int = 10,
        lang_nl: bool = True,
        site_nl_only: bool = False,
        start: int = 1,
        news_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a web search and return normalized items.

        - query: search query string
        - num: number of results (max 10 per request per API spec)
        - lang_nl: if True, prefer Dutch results (lr=lang_nl & gl=nl)
        - site_nl_only: if True, add 'site:.nl' to the query
        - start: pagination start index (1-based)
        - news_only: if True, filter results to likely news articles
        """
        q = query.strip()
        if site_nl_only and "site:.nl" not in q:
            q = f'{q} site:.nl'

        params = {
            "q": q,
            "key": self.api_key,
            "cx": self.cx,
            "num": max(1, min(10, int(num))),
            "start": max(1, int(start)),
        }
        if lang_nl:
            params.update({"lr": "lang_nl", "gl": "nl", "hl": "nl"})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.BASE_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "Google CSE error",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return []
                data = resp.json()
                raw_items = data.get("items", []) or []
                normalized = [self._normalize_item(item) for item in raw_items]
                if news_only:
                    normalized = [item for item in normalized if self._is_probable_news_url(item.get("url", ""))]
                return normalized
        except Exception as e:
            logger.warning("Google CSE request failed", error=str(e))
            return []

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Google CSE item into our generic article dict shape."""
        url = item.get("link") or ""
        title = item.get("title") or item.get("htmlTitle") or url
        snippet = item.get("snippet") or ""
        source = self._extract_domain(url)
        from datetime import datetime
        return {
            "title": title,
            "url": url,
            "source": source,
            "date": datetime.now(),  # Use current time when unknown
            "content": snippet,
        }

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            host = (parsed.netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            return host or "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _is_probable_news_url(url: str) -> bool:
        """Heuristically determine if a URL likely points to a news article."""
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path.lower()

            # Keywords often present in news domains or paths
            keywords = ["news", "nieuws", "article", "artikel"]
            if any(k in host for k in keywords):
                return True
            if any(k in path for k in keywords):
                return True

            # Look for date patterns commonly used in news articles
            if re.search(r"/20\d{2}/\d{2}/\d{2}/", path):
                return True

            return False
        except Exception:
            return False
