import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
import hashlib

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import structlog

from app.core.config import settings
from app.models.response_models import LegalCase, LegalFindings
from app.utils.text_utils import (
    normalize_company_name,
    calculate_similarity,
    match_company_variations,
)

logger = structlog.get_logger(__name__)


class LegalService:
    """Service for accessing legal case information from Rechtspraak Open Data API"""

    def __init__(self):
        self.api_base_url = "https://data.rechtspraak.nl/uitspraken/zoeken"
        self.content_base_url = "https://data.rechtspraak.nl/uitspraken/content"
        self.timeout = getattr(settings, "RECHTSPRAAK_TIMEOUT", 30)
        self.user_agent = f"{settings.APP_NAME}/{getattr(settings, 'APP_VERSION', '1.0')} (Business Analysis API)"
        self.rate_limit_delay = 1.0  # 1 request per second
        self.last_request_time = 0.0

        # In-memory cache
        self._cache = {}
        self._cache_ttl = {}
        self.search_cache_ttl = 1800  # 30 minutes
        self.case_cache_ttl = 86400  # 24 hours

        # Robots.txt compliance - always allowed for public API
        self.robots_allowed = True
        self.crawl_delay = self.rate_limit_delay

        logger.info("Legal service initialized", base_url=self.api_base_url)

    async def initialize(self):
        """Initialize service (no robots.txt check needed for API)"""
        logger.info("Legal service initialization complete", api_base_url=self.api_base_url)

    async def _enforce_rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.crawl_delay:
            sleep_time = self.crawl_delay - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def _get_cache_key(
        self,
        company_name: str,
        trade_name: str = None,
        contact_person: str = None,
        filters: Dict = None,
    ) -> str:
        """Generate cache key for search results"""
        key_parts = [company_name]
        if trade_name:
            key_parts.append(trade_name)
        if contact_person:
            key_parts.append(contact_person)
        if filters:
            key_parts.append(str(sorted(filters.items())))

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get item from cache if not expired"""
        if cache_key in self._cache:
            if time.time() < self._cache_ttl.get(cache_key, 0):
                return self._cache[cache_key]
            else:
                # Clean up expired entry
                self._cache.pop(cache_key, None)
                self._cache_ttl.pop(cache_key, None)
        return None

    def _set_cache(self, cache_key: str, value: Any, ttl_seconds: int):
        """Set item in cache with TTL"""
        self._cache[cache_key] = value
        self._cache_ttl[cache_key] = time.time() + ttl_seconds

        # Simple LRU eviction: keep only 100 most recent items
        if len(self._cache) > 100:
            oldest_key = min(self._cache_ttl.keys(), key=lambda k: self._cache_ttl[k])
            self._cache.pop(oldest_key, None)
            self._cache_ttl.pop(oldest_key, None)

    async def search_company_cases(
        self, company_name: str, trade_name: str = None, contact_person: str = None
    ) -> List[LegalCase]:
        """
        Search for legal cases involving a company and optionally a contact person.
        This method is MANDATORY and will always attempt to search Rechtspraak.nl.

        Args:
            company_name: Official company name
            trade_name: Trade name if different from official name
            contact_person: Contact person name to also search for

        Returns:
            List of relevant legal cases (empty list if search fails but never skips)
        """
        # MANDATORY: Always attempt to search Rechtspraak.nl, even if robots.txt is restrictive
        # This is a business requirement for Dutch company analysis

        # Check cache first (include contact person in cache key)
        cache_key = self._get_cache_key(company_name, trade_name, contact_person)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            logger.info(
                "Returning cached legal search results", company_name=company_name
            )
            return cached_result

        logger.info(
            "Searching for legal cases (MANDATORY Rechtspraak.nl search)",
            company_name=company_name,
            trade_name=trade_name,
            contact_person=contact_person,
        )

        try:
            # MANDATORY: Always attempt search regardless of robots.txt
            # The Rechtspraak Open Data API doesn't support free text queries.
            # We therefore fetch a recent set of ECLI entries and filter them
            # locally for relevant party names.

            cases = await self._perform_search()

            # Remove duplicates and filter by relevance
            unique_cases = self._deduplicate_cases(cases)
            relevant_cases = self._filter_by_relevance(
                unique_cases, company_name, trade_name, contact_person
            )

            # Cache the results
            self._set_cache(cache_key, relevant_cases, self.search_cache_ttl)

            logger.info(
                "Legal search completed",
                company_name=company_name,
                total_found=len(relevant_cases),
            )

            return relevant_cases

        except Exception as e:
            # IMPORTANT: Even if search fails, we log it but don't completely fail
            # This maintains the mandatory nature of trying to search Rechtspraak.nl
            logger.error(
                "Legal search failed but this was still a mandatory attempt",
                company_name=company_name,
                error=str(e),
            )

            # Return empty list but with a warning that search was attempted
            return []

    async def _perform_search(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Retrieve recent ECLIs and associated case info.

        Because the Rechtspraak API does not support arbitrary text queries,
        this method fetches a list of recent cases using date filters and later
        filtering is applied in :meth:`_filter_by_relevance`.
        """
        search_results = []
        max_results = 50  # Limit total results

        try:
            await self._enforce_rate_limit()

            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=365)
            params: List[tuple] = [
                ("date", start_date.strftime("%Y-%m-%d")),
                ("date", end_date.strftime("%Y-%m-%d")),
                ("return", "DOC"),  # Only cases with documents
                ("max", str(max_results)),
                ("sort", "DESC"),
            ]

            if filters:
                for key, value in filters.items():
                    params.append((key, value))

            api_response = await self._fetch_api_search(params)
            if not api_response:
                return []

            # Parse API response to extract cases
            search_results = await self._parse_api_results(api_response)

        except Exception as e:
            logger.error("Error during API search", error=str(e))

        return search_results

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _fetch_api_search(
        self, params: Any
    ) -> Optional[Dict[str, Any]]:
        """Fetch search results from Rechtspraak Open Data API.

        ``params`` may be a mapping or a list of key/value tuples so that
        duplicate query parameters (e.g. multiple ``date`` filters) can be
        supplied.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/atom+xml, application/json",
            "Accept-Language": "nl,en;q=0.5",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    self.api_base_url, params=params, headers=headers
                )

                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        try:
                            return response.json()
                        except ValueError as e:
                            logger.warning(
                                "API search response JSON decode error",
                                params=params,
                                error=str(e),
                                response_text=response.text[:1000],
                            )
                            return None
                    elif "application/atom+xml" in content_type or "application/xml" in content_type:
                        # Return raw XML to be parsed separately
                        return response.text
                    else:
                        logger.warning(
                            "Unexpected content type from API search",
                            params=params,
                            content_type=content_type,
                        )
                        return None
                else:
                    logger.warning(
                        "API search request failed",
                        status_code=response.status_code,
                        params=params,
                    )
                    return None

            except httpx.TimeoutException:
                logger.error("API search request timed out", params=params)
                raise
            except Exception as e:
                logger.error("API search request error", params=params, error=str(e))
                raise

    async def _parse_api_results(
        self, api_response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Parse search results from Rechtspraak API JSON response"""
        try:
            results = []

            # When the API returns JSON structure
            if isinstance(api_response, dict):
                cases = api_response.get("results", [])
                if not cases and "docs" in api_response:
                    cases = api_response["docs"]
                if not cases and isinstance(api_response, list):
                    cases = api_response

                for case_data in cases[:20]:  # Limit to first 20 results
                    try:
                        case_info = await self._extract_case_from_api_data(case_data)
                        if case_info:
                            results.append(case_info)
                    except Exception as e:
                        logger.debug(
                            "Error parsing individual API result item", error=str(e)
                        )
                        continue
            else:
                # Assume XML string (Atom feed)
                import xml.etree.ElementTree as ET

                try:
                    root = ET.fromstring(api_response)
                except Exception as e:
                    logger.error("Failed to parse XML response", error=str(e))
                    return []

                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns)

                for entry in entries[:20]:
                    try:
                        ecli = entry.findtext("atom:id", default="", namespaces=ns)
                        title_text = entry.findtext("atom:title", default="", namespaces=ns)
                        summary = entry.findtext("atom:summary", default="", namespaces=ns)
                        updated = entry.findtext("atom:updated", default="", namespaces=ns)

                        # Extract link to public detail page
                        link = ""
                        for l in entry.findall("atom:link", ns):
                            if l.attrib.get("rel") == "alternate":
                                link = l.attrib.get("href", "")
                                break

                        # Parse court and date from title if present
                        court = ""
                        date_text = updated[:10] if updated else ""
                        title = title_text
                        parts = title_text.split(",")
                        if parts:
                            # first part is often ECLI
                            if not ecli:
                                ecli = parts[0].strip()
                            if len(parts) > 1:
                                court = parts[1].strip()
                            if len(parts) > 2:
                                date_text = parts[2].strip()
                            if len(parts) > 3:
                                title = ",".join(parts[3:]).strip() or title_text

                        case_data = {
                            "identifier": ecli,
                            "title": title,
                            "date": date_text,
                            "spatial": court,
                            "summary": summary,
                            "link": link,
                        }

                        case_info = await self._extract_case_from_api_data(case_data)
                        if case_info:
                            results.append(case_info)
                    except Exception as e:
                        logger.debug(
                            "Error parsing individual Atom entry", error=str(e)
                        )
                        continue

            logger.debug("Parsed API search results", count=len(results))
            return results

        except Exception as e:
            logger.error("Error parsing API search results", error=str(e))
            return []

    async def _extract_case_from_api_data(
        self, case_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract case information from API response data"""
        try:
            # Extract ECLI from the API response
            ecli = case_data.get("identifier", case_data.get("ecli", ""))

            # Extract basic information
            title = case_data.get("title", case_data.get("subject", ""))
            date_str = case_data.get("date", case_data.get("modified", ""))

            # Extract court information
            court = case_data.get("spatial", case_data.get("court", "Unknown Court"))

            # Extract case type
            case_type = case_data.get("type", case_data.get("subject", "civil"))

            # Construct case URL using ECLI
            case_url = f"{self.content_base_url}?id={ecli}" if ecli else ""

            # Get full case details if ECLI is available
            full_text = ""
            parties = []
            case_number = ""
            summary = case_data.get("summary", title)

            if ecli:
                case_details = await self._fetch_case_details(ecli)
                if case_details:
                    full_text = case_details.get("full_text", "")
                    parties = case_details.get("parties", [])
                    case_number = case_details.get("case_number", "")
                    summary = case_details.get("summary", summary)

            return {
                "ecli": ecli,
                "title": title,
                "date_text": date_str,
                "court_text": court,
                "case_type": case_type.lower(),
                "case_number": case_number,
                "parties": parties,
                "summary": summary[:500],
                "full_text": full_text[:2000],  # Limit full text
                "url": case_url,
            }

        except Exception as e:
            logger.debug(
                "Error extracting case information from API data", error=str(e)
            )
            return None

    async def _fetch_case_details(self, ecli: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific case using ECLI"""
        try:
            await self._enforce_rate_limit()

            params = {"id": ecli, "return": "DOC"}  # Return full document

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {
                    "User-Agent": self.user_agent,
                    "Accept": "application/xml, application/json",
                }
                response = await client.get(
                    self.content_base_url, params=params, headers=headers
                )

                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return self._parse_case_detail_api(response.json(), ecli)
                    else:
                        return self._parse_case_detail_xml(response.text, ecli)
                else:
                    logger.warning(
                        "Failed to fetch case details",
                        ecli=ecli,
                        status_code=response.status_code,
                    )
                    return None

        except Exception as e:
            logger.error("Error fetching case details", ecli=ecli, error=str(e))
            return None

    def _parse_case_detail_api(
        self, api_data: Dict[str, Any], ecli: str
    ) -> Dict[str, Any]:
        """Parse detailed case information from API JSON response"""
        try:
            # Extract case number
            case_number = api_data.get("case_number", api_data.get("zaaknummer", ""))

            # Extract parties from the case content
            full_text = api_data.get("content", api_data.get("text", ""))
            parties = self._extract_parties_from_text(full_text)

            # Extract other metadata
            subject = api_data.get("subject", api_data.get("title", ""))

            return {
                "ecli": ecli,
                "case_number": case_number,
                "parties": parties,
                "full_text": full_text[:5000],  # Limit text size
                "subject": subject,
            }

        except Exception as e:
            logger.error("Error parsing case detail API data", ecli=ecli, error=str(e))
            return {}

    def _parse_case_detail_xml(self, xml_text: str, ecli: str) -> Dict[str, Any]:
        """Parse detailed case information from Rechtspraak XML response"""
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_text)
            ns = {
                "psi": "http://psi.rechtspraak.nl/",
                "rs": "http://www.rechtspraak.nl/schema/rechtspraak-1.0",
                "dcterms": "http://purl.org/dc/terms/",
            }

            case_number = ""
            case_elem = root.find('.//psi:zaaknummer', ns)
            if case_elem is not None and case_elem.text:
                case_number = case_elem.text

            summary = ""
            summary_elem = root.find('.//rs:inhoudsindicatie', ns)
            if summary_elem is not None:
                summary = " ".join(
                    p.text.strip() for p in summary_elem.findall('.//rs:para', ns) if p.text
                )

            full_text = ""
            uitspraak_elem = root.find('.//rs:uitspraak', ns)
            if uitspraak_elem is not None:
                full_text = " ".join(
                    p.text.strip() for p in uitspraak_elem.findall('.//rs:para', ns) if p.text
                )

            parties = self._extract_parties_from_text(full_text)

            return {
                "ecli": ecli,
                "case_number": case_number,
                "parties": parties,
                "full_text": full_text[:5000],
                "summary": summary,
            }

        except Exception as e:
            logger.error("Error parsing case detail XML", ecli=ecli, error=str(e))
            return {}

    def _deduplicate_cases(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate cases based on URL or ECLI"""
        seen_urls = set()
        seen_eclis = set()
        unique_cases = []

        for case in cases:
            url = case.get("url", "")
            ecli = case.get("ecli", "")

            if url and url not in seen_urls:
                seen_urls.add(url)
                if ecli:
                    seen_eclis.add(ecli)
                unique_cases.append(case)
            elif ecli and ecli not in seen_eclis:
                seen_eclis.add(ecli)
                unique_cases.append(case)

        return unique_cases

    def _filter_by_relevance(
        self,
        cases: List[Dict[str, Any]],
        company_name: str,
        trade_name: str = None,
        contact_person: str = None,
    ) -> List[LegalCase]:
        """Filter cases by relevance to the company and convert to LegalCase objects"""
        relevant_cases = []

        for case_data in cases:
            try:
                relevance_score = self._calculate_relevance_score(
                    case_data, company_name, trade_name, contact_person
                )

                if relevance_score >= 0.6:  # Minimum threshold
                    legal_case = self._convert_to_legal_case(case_data, relevance_score)
                    if legal_case:
                        relevant_cases.append(legal_case)

            except Exception as e:
                logger.debug("Error processing case for relevance", error=str(e))
                continue

        # Sort by relevance score descending
        relevant_cases.sort(key=lambda x: x.relevance_score, reverse=True)

        return relevant_cases[:20]  # Return top 20 most relevant

    def _calculate_relevance_score(
        self,
        case_data: Dict[str, Any],
        company_name: str,
        trade_name: str = None,
        contact_person: str = None,
    ) -> float:
        """Calculate relevance score for a case"""
        score = 0.0

        # Normalize company names for comparison
        normalized_company = normalize_company_name(company_name)
        normalized_trade = normalize_company_name(trade_name) if trade_name else None

        # Check title/summary for company name matches
        text_to_check = f"{case_data.get('title', '')} {case_data.get('summary', '')}"
        company_matches = match_company_variations(text_to_check, normalized_company)

        if company_matches:
            score += 0.8  # Strong match in title/summary

        if normalized_trade:
            trade_matches = match_company_variations(text_to_check, normalized_trade)
            if trade_matches:
                score += 0.7

        # Check for contact person mentions
        if contact_person:
            contact_person_lower = contact_person.lower()
            # Check in title, summary and full text
            full_text_to_check = f"{text_to_check} {case_data.get('full_text', '')}"

            if contact_person_lower in full_text_to_check.lower():
                score += 0.6  # High relevance if contact person is mentioned
                logger.info(
                    f"Contact person '{contact_person}' found in legal case",
                    case_title=case_data.get("title", "")[:50],
                )

        # Check parties list if available
        parties = case_data.get("parties", [])
        for party in parties:
            party_similarity = calculate_similarity(
                normalize_company_name(party), normalized_company
            )
            if party_similarity > 0.8:
                score = max(score, 1.0)  # Exact party match
            elif party_similarity > 0.6:
                score = max(score, 0.7)

            # Also check if contact person matches party
            if contact_person and contact_person.lower() in party.lower():
                score = max(score, 0.8)  # High relevance for personal involvement

        return min(score, 1.0)

    def _convert_to_legal_case(
        self, case_data: Dict[str, Any], relevance_score: float
    ) -> Optional[LegalCase]:
        """Convert case data to LegalCase object"""
        try:
            # Parse date
            case_date = datetime.now()  # Default to now
            date_text = case_data.get("date_text", "")
            if date_text:
                # Try different date formats
                for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"]:
                    try:
                        case_date = datetime.strptime(date_text, fmt)
                        break
                    except ValueError:
                        continue

            # Generate ECLI if not available
            ecli = case_data.get("ecli")
            if not ecli:
                # Generate a placeholder ECLI for cases without one
                url_hash = hashlib.md5(case_data.get("url", "").encode()).hexdigest()[
                    :8
                ]
                ecli = f"ECLI:NL:PLACEHOLDER:{case_date.year}:{url_hash.upper()}"

            # Determine case type from court or content
            case_type = self._determine_case_type(case_data)

            return LegalCase(
                ecli=ecli,
                case_number=case_data.get("case_number", "Unknown"),
                date=case_date,
                court=case_data.get("court_text", "Unknown Court"),
                type=case_type,
                parties=case_data.get("parties", []),
                summary=case_data.get("summary", "")[:500],
                outcome="unknown",  # Would need detailed parsing to determine
                url=case_data.get("url", ""),
                relevance_score=relevance_score,
            )

        except Exception as e:
            logger.error("Error converting case data to LegalCase", error=str(e))
            return None

    def _extract_parties_from_text(self, text: str) -> List[str]:
        """Extract company/party names from case text"""
        parties = []
        if not text:
            return parties

        # Look for common Dutch legal entity patterns
        import re

        patterns = [
            r"([A-Z][a-z]+ (?:B\.?V\.?|N\.?V\.?|VOF|CV|Stichting|Vereniging))",
            r"([A-Z][A-Za-z\s&]+ (?:B\.?V\.?|N\.?V\.?|VOF|CV))",
            r"((?:[A-Z][a-z]+\s?){1,4}(?:B\.?V\.?|N\.?V\.?|VOF|CV))",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            parties.extend([match.strip() for match in matches if match.strip()])

        # Remove duplicates and limit
        return list(set(parties))[:10]

    def _determine_case_type(self, case_data: Dict[str, Any]) -> str:
        """Determine case type from available data"""
        # Check if case_type is already provided by API
        if "case_type" in case_data:
            return case_data["case_type"]

        text_to_check = f"{case_data.get('title', '')} {case_data.get('summary', '')} {case_data.get('court_text', '')}"
        text_lower = text_to_check.lower()

        if any(
            word in text_lower
            for word in ["strafrecht", "straf", "criminal", "verdachte"]
        ):
            return "criminal"
        elif any(
            word in text_lower
            for word in [
                "bestuursrecht",
                "bestuur",
                "administrative",
                "gemeente",
                "ministerie",
            ]
        ):
            return "administrative"
        else:
            return "civil"  # Default assumption

    def assess_legal_risk(self, cases: List[LegalCase]) -> str:
        """
        Assess legal risk level based on found cases

        Args:
            cases: List of legal cases

        Returns:
            Risk level string (low, medium, high)
        """
        if not cases:
            return "low"

        case_count = len(cases)
        criminal_cases = sum(1 for case in cases if case.type == "criminal")
        recent_cases = sum(
            1 for case in cases if case.date > datetime.now() - timedelta(days=730)
        )

        # Risk calculation
        risk_score = 0
        risk_score += case_count * 2
        risk_score += criminal_cases * 10
        risk_score += recent_cases * 3

        if risk_score >= 20:
            return "high"
        elif risk_score >= 8:
            return "medium"
        else:
            return "low"
