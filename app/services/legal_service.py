"""Legal service with Rechtspraak Open Data support.

This module provides a small pluggable index layer and a harvester for the
Rechtspraak Open Data.  It exposes two public search functions
``search_by_company`` and ``search_by_kvk`` which operate on an in‑process
full‑text index.  The implementation is intentionally lightweight so that it
can run in a test environment without external services.

Usage
-----
The typical flow is:

1. Run :meth:`LegalService.harvest` to fetch ECLI identifiers that were
   modified in a given period.  For each ECLI the full content is retrieved and
   indexed.  Harvesting can be executed repeatedly; a cursor keeps track of the
   last processed ``modified`` timestamp.
2. Call :meth:`LegalService.search_by_company` or
   :meth:`LegalService.search_by_kvk` to search the local index.

The service respects a configurable rate limit, retries transient network
errors with exponential backoff and parses XML documents into plain text while
attempting to extract KvK numbers.

The data supplied by Rechtspraak can be anonymised.  This service therefore
offers best‑effort searching only; absence of results is no guarantee that a
company has never appeared in case law.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Search index abstraction
# ---------------------------------------------------------------------------


class SearchIndex:
    """Abstract search index interface."""

    def upsert(self, doc: Dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, ecli: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def search(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 25,
        offset: int = 0,
        synonyms: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError


class InMemorySearchIndex(SearchIndex):
    """Very small in‑process full‑text index used for testing.

    Documents are stored in a dictionary keyed by ECLI.  Searching iterates
    over all documents and performs case‑insensitive substring and fuzzy
    matching.  This is obviously not meant for production use but keeps the
    index pluggable as required by the specification.
    """

    def __init__(self) -> None:
        self.docs: Dict[str, Dict[str, Any]] = {}

    # -------------------------- index maintenance -------------------------
    def upsert(self, doc: Dict[str, Any]) -> None:
        self.docs[doc["ecli"]] = doc

    def delete(self, ecli: str) -> None:
        self.docs.pop(ecli, None)

    # ------------------------------- search -------------------------------
    def search(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 25,
        offset: int = 0,
        synonyms: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        query_terms = [query.lower()]
        if synonyms:
            query_terms.extend([s.lower() for s in synonyms])

        results: List[tuple[int, Dict[str, Any], str]] = []

        for doc in self.docs.values():
            if filters and not _apply_filters(doc, filters):
                continue

            score = 0
            snippet = ""

            text_fields = [
                ("title", doc.get("title", "")),
                ("inhoudsindicatie_text", doc.get("inhoudsindicatie_text", "")),
                ("full_text", doc.get("full_text", "")),
            ]

            for term in query_terms:
                for field_name, text in text_fields:
                    field = text.lower()
                    if term in field:
                        score += 2 if field_name != "full_text" else 1
                        if not snippet:
                            snippet = _make_snippet(text, term)
                    else:
                        # fuzzy/prefix search
                        if field.startswith(term) or SequenceMatcher(None, term, field[: len(term)]).ratio() > 0.8:
                            score += 1
                            if not snippet:
                                snippet = text[:200]

            if score > 0:
                results.append((score, doc, snippet))

        results.sort(key=lambda x: x[0], reverse=True)
        sliced = results[offset : offset + limit]
        return [
            {
                "ecli": d["ecli"],
                "title": d.get("title", ""),
                "date": d.get("date"),
                "instantie": d.get("instantie"),
                "rechtsgebieden": d.get("rechtsgebieden", []),
                "zaaknummers": d.get("zaaknummers", []),
                "kvk_numbers": d.get("kvk_numbers", []),
                "deeplink": d.get("deeplink"),
                "snippet": snip,
            }
            for _, d, snip in sliced
        ]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _strip_text(xml_fragment: str) -> str:
    """Strip markup and normalise whitespace."""

    soup = BeautifulSoup(xml_fragment, "lxml")
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


KVK_PATTERN = re.compile(
    r"(?:(?:kvk|kamer\s+van\s+koophandel)[^0-9]{0,20})?(\d{8})",
    re.IGNORECASE,
)


def _extract_kvk_numbers(text: str) -> List[str]:
    """Extract 8 digit KvK numbers from text."""

    numbers = {match.group(1) for match in KVK_PATTERN.finditer(text or "")}
    return list(numbers)


def _make_snippet(text: str, term: str) -> str:
    idx = text.lower().find(term)
    if idx == -1:
        return text[:200].strip()
    start = max(0, idx - 40)
    end = min(len(text), idx + 40)
    return text[start:end].strip()


def _apply_filters(doc: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    instantie = filters.get("instantie")
    rechtsgebied = filters.get("rechtsgebied")

    if date_from and doc.get("date") and doc["date"] < date_from:
        return False
    if date_to and doc.get("date") and doc["date"] > date_to:
        return False
    if instantie:
        inst = doc.get("instantie", {})
        if instantie not in (inst.get("name"), inst.get("id")):
            return False
    if rechtsgebied:
        labels = [rg.get("label") for rg in doc.get("rechtsgebieden", [])]
        ids = [rg.get("uri") for rg in doc.get("rechtsgebieden", [])]
        if rechtsgebied not in labels and rechtsgebied not in ids:
            return False
    return True


# ---------------------------------------------------------------------------
# LegalService implementation
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    ecli: str
    title: str
    date: Optional[datetime]
    instantie: Dict[str, Any]
    rechtsgebieden: List[Dict[str, Any]]
    zaaknummers: List[str]
    kvk_numbers: List[str]
    deeplink: str
    snippet: str


class LegalService:
    """Service for harvesting and searching Rechtspraak data."""

    def __init__(
        self,
        *,
        base_url: str = "https://data.rechtspraak.nl",
        rate_limit: int = 60,  # requests per minute
        timeout: int = 30,
        index: Optional[SearchIndex] = None,
        cursor_file: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_url = f"{self.base_url}/uitspraken/zoeken"
        self.content_url = f"{self.base_url}/uitspraken/content"
        self.timeout = timeout
        self.index = index or InMemorySearchIndex()

        # rate limiting: seconds between requests
        self.rate_limit_delay = 60.0 / max(rate_limit, 1)
        self._last_request: float = 0.0

        self.cursor_file = cursor_file
        self.cursor: Optional[str] = self._load_cursor()

        self.user_agent = "VHM-LegalService/1.0"

    # ----------------------------- cursor I/O ----------------------------
    def _load_cursor(self) -> Optional[str]:
        if self.cursor_file and os.path.exists(self.cursor_file):
            return open(self.cursor_file, "r", encoding="utf-8").read().strip() or None
        return None

    def _save_cursor(self, value: str) -> None:
        self.cursor = value
        if self.cursor_file:
            with open(self.cursor_file, "w", encoding="utf-8") as fh:
                fh.write(value)

    # -------------------------- rate limiting ---------------------------
    async def _enforce_rate_limit(self) -> None:
        now = asyncio.get_event_loop().time()
        wait = self.rate_limit_delay - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = asyncio.get_event_loop().time()

    # ---------------------------- HTTP helpers ---------------------------
    @retry(
        retry=retry_if_exception_type(httpx.RequestError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
    )
    async def _http_get(self, url: str, params: Dict[str, Any]) -> httpx.Response:
        await self._enforce_rate_limit()
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp

    # --------------------------- harvesting -----------------------------
    async def harvest(self, *, modified: Optional[str] = None, max: int = 1000) -> Dict[str, int]:
        """Harvest ECLI identifiers and update the index.

        Parameters
        ----------
        modified:
            ISO timestamp or date string accepted by Rechtspraak's ``modified``
            parameter.  When omitted the internal cursor is used.
        max:
            Maximum number of results per request (``≤ 1000``).

        Returns
        -------
        dict
            ``{"upserts": int, "deletes": int, "pages": int}``
        """

        params = {
            "return": "DOC",
            "max": max,
        }
        if modified or self.cursor:
            params["modified"] = modified or self.cursor

        offset = 0
        upserts = 0
        deletes = 0
        pages = 0

        while True:
            params["from"] = offset
            resp = await self._http_get(self.search_url, params)
            entries = self._parse_feed(resp.text)
            if not entries:
                break
            pages += 1

            for entry in entries:
                ecli = entry["ecli"]
                if entry.get("deleted"):
                    self.index.delete(ecli)
                    deletes += 1
                    continue

                content = await self.fetch_ecli_content(ecli)
                if content:
                    self.index.upsert(content)
                    upserts += 1
                    if entry.get("updated"):
                        self._save_cursor(entry["updated"])

            offset += len(entries)

        logger.info(
            "harvest complete", upserts=upserts, deletes=deletes, pages=pages
        )
        return {"upserts": upserts, "deletes": deletes, "pages": pages}

    def _parse_feed(self, feed_xml: str) -> List[Dict[str, Any]]:
        root = ET.fromstring(feed_xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            eid = entry.findtext("atom:id", default="", namespaces=ns).strip()
            updated = entry.findtext("atom:updated", default="", namespaces=ns).strip()
            deleted = entry.attrib.get("deleted")
            entries.append({"ecli": eid, "updated": updated, "deleted": deleted})
        return entries

    # --------------------------- content fetch --------------------------
    async def fetch_ecli_content(self, ecli: str) -> Optional[Dict[str, Any]]:
        params = {"id": ecli, "return": "DOC"}
        try:
            resp = await self._http_get(self.content_url, params)
        except httpx.HTTPError as exc:  # pragma: no cover - network error
            logger.warning("content fetch failed", ecli=ecli, error=str(exc))
            return None
        return self._parse_ecli_content(resp.text)

    def _parse_ecli_content(self, xml_text: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_text)

        def find_text(name: str) -> str:
            for elem in root.iter():
                if elem.tag.split("}")[-1] == name and (elem.text):
                    return elem.text.strip()
            return ""

        def find_all(name: str) -> List[str]:
            return [
                e.text.strip()
                for e in root.iter()
                if e.tag.split("}")[-1] == name and e.text
            ]

        # Basic metadata
        ecli = find_text("identifier") or find_text("ECLI")
        title = find_text("title")
        date_str = find_text("issued") or find_text("date")
        date_val: Optional[datetime] = None
        if date_str:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    date_val = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        # Instantie (creator)
        instantie_name = ""
        instantie_id = ""
        for elem in root.iter():
            if elem.tag.split("}")[-1] == "creator":
                instantie_name = (elem.text or "").strip()
                instantie_id = elem.attrib.get("resourceIdentifier", "")
                break

        rechtsgebieden = [
            {
                "label": e.text.strip(),
                "uri": e.attrib.get("resourceIdentifier", ""),
            }
            for e in root.iter()
            if e.tag.split("}")[-1] == "subject" and e.text
        ]

        procedures = find_all("procedure")
        zaaknummers = find_all("zaaknummer")

        inhoud_elem = next(
            (e for e in root.iter() if e.tag.split("}")[-1] == "inhoudsindicatie"),
            None,
        )
        inhoud_text = _strip_text(ET.tostring(inhoud_elem, encoding="unicode")) if inhoud_elem else ""

        full_text = ""
        for e in root.iter():
            if e.tag.split("}")[-1] in {"uitspraak", "conclusie"}:
                full_text += " " + _strip_text(ET.tostring(e, encoding="unicode"))
        full_text = full_text.strip()

        kvk_numbers = _extract_kvk_numbers(" ".join([title, inhoud_text, full_text]))

        return {
            "ecli": ecli,
            "title": title,
            "date": date_val,
            "instantie": {"name": instantie_name, "id": instantie_id},
            "rechtsgebieden": rechtsgebieden,
            "procedures": procedures,
            "zaaknummers": zaaknummers,
            "inhoudsindicatie_text": inhoud_text,
            "full_text": full_text,
            "kvk_numbers": kvk_numbers,
            "deeplink": f"http://deeplink.rechtspraak.nl/uitspraak?id={ecli}",
        }

    # ------------------------------ search ------------------------------
    def search_by_company(
        self,
        name: str,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        instantie: Optional[str] = None,
        rechtsgebied: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        synonyms: Optional[Iterable[str]] = None,
    ) -> List[SearchResult]:
        filters = {
            "date_from": date_from,
            "date_to": date_to,
            "instantie": instantie,
            "rechtsgebied": rechtsgebied,
        }
        docs = self.index.search(
            name,
            filters=filters,
            limit=limit,
            offset=offset,
            synonyms=synonyms,
        )
        return [SearchResult(**doc) for doc in docs]

    def search_by_kvk(
        self, kvk: str, *, limit: int = 25, offset: int = 0
    ) -> List[SearchResult]:
        kvk_norm = re.sub(r"\D", "", kvk)[-8:]
        results = []
        for doc in self.index.docs.values():
            if kvk_norm in doc.get("kvk_numbers", []):
                snippet = _make_snippet(
                    " ".join([doc.get("title", ""), doc.get("full_text", "")]),
                    kvk_norm,
                )
                result = {
                    "ecli": doc["ecli"],
                    "title": doc.get("title", ""),
                    "date": doc.get("date"),
                    "instantie": doc.get("instantie", {}),
                    "rechtsgebieden": doc.get("rechtsgebieden", []),
                    "zaaknummers": doc.get("zaaknummers", []),
                    "kvk_numbers": doc.get("kvk_numbers", []),
                    "deeplink": doc.get("deeplink"),
                    "snippet": snippet,
                }
                results.append(result)

        results.sort(key=lambda d: d.get("date") or datetime.min, reverse=True)
        sliced = results[offset : offset + limit]
        return [SearchResult(**d) for d in sliced]

    # ------------------------------------------------------------------
    # Backwards compatibility stub - previous versions exposed a
    # ``search_company_cases`` coroutine.  It now delegates to
    # ``search_by_company`` but returns an empty list of ``LegalCase``
    # objects because the original data model is not maintained here.
    # ------------------------------------------------------------------
    async def search_company_cases(self, company_name: str, *_, **__) -> List[Any]:
        logger.warning(
            "search_company_cases is deprecated; use search_by_company instead"
        )
        return []

