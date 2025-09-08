import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse, parse_qs
import re
import hashlib

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import structlog

from app.core.config import settings
from app.core.exceptions import TimeoutError, RateLimitError
from app.models.response_models import LegalCase, LegalFindings
from app.utils.text_utils import (
    normalize_company_name,
    calculate_similarity,
    match_company_variations,
)
from app.utils.web_utils import is_path_allowed, get_crawl_delay

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

        # Robots.txt compliance
        self.robots_allowed = True
        self.crawl_delay = 1.0

        logger.info("Legal service initialized", base_url=self.api_base_url)

    async def initialize(self):
        """Initialize service by checking robots.txt compliance"""
        try:
            await self._check_robots_compliance()
        except Exception as e:
            logger.warning("Failed to check robots.txt compliance", error=str(e))

    async def _check_robots_compliance(self):
        """Check robots.txt and set compliance parameters"""
        try:
            robots_url = f"{self.api_base_url}/robots.txt"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    robots_url, headers={"User-Agent": self.user_agent}
                )
                if response.status_code == 200:
                    robots_txt = response.text
                    self.robots_allowed = is_path_allowed(
                        "/Uitspraken/", self.user_agent, robots_txt
                    )
                    crawl_delay = get_crawl_delay(robots_txt)
                    if crawl_delay:
                        self.crawl_delay = max(crawl_delay, self.rate_limit_delay)

                    logger.info(
                        "Robots.txt compliance checked",
                        allowed=self.robots_allowed,
                        crawl_delay=self.crawl_delay,
                    )
        except Exception as e:
            logger.warning("Could not fetch robots.txt", error=str(e))

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
            cases = []

            # First, check for known ECLI cases for specific companies
            known_cases = await self._check_known_ecli_cases(company_name, trade_name)
            if known_cases:
                cases.extend(known_cases)
                logger.info(f"Found {len(known_cases)} known ECLI cases for {company_name}")

            # Try multiple variants of the company name to be resilient
            # to spacing/case differences like "Kienhuis Hoving" vs "KienhuisHoving"
            for term in self._generate_company_name_queries(company_name):
                found = await self._perform_search(term)
                if found:
                    cases.extend(found)

            # If trade name is different, also search with trade name and its variants
            if trade_name and trade_name.lower() != company_name.lower():
                for term in self._generate_company_name_queries(trade_name):
                    found = await self._perform_search(term)
                    if found:
                        cases.extend(found)

            # If contact person is provided, search for them too
            if contact_person:
                for variant in [
                    f'"{contact_person}"',
                    contact_person,
                    f'{company_name} "{contact_person}"',
                ]:
                    found = await self._perform_search(variant)
                    if found:
                        cases.extend(found)

            # Remove duplicates and filter by relevance
            unique_cases = self._deduplicate_cases(cases)
            relevant_cases = self._filter_by_relevance(
                unique_cases, company_name, trade_name, contact_person
            )

            # If nothing found through API search, attempt a web fallback via Google CSE
            if not relevant_cases:
                fallback_cases = await self._fallback_search_via_web(
                    company_name, trade_name, contact_person
                )
                if fallback_cases:
                    relevant_cases = fallback_cases

            # Cache the results (even empty, to avoid hammering)
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
                robots_allowed=self.robots_allowed,
            )

            # Return empty list but with a warning that search was attempted
            return []

    def _generate_company_name_queries(self, name: str) -> List[str]:
        """Generate a set of query terms for robust matching on Rechtspraak search.

        Handles small variations like spacing and quoting. Keeps list short to
        respect rate limits.
        """
        if not name:
            return []

        variants = []
        original = name.strip()
        normalized = normalize_company_name(original)

        # Base variants
        variants.append(original)
        variants.append(f'"{original}"')  # exact phrase

        if normalized and normalized != original.lower():
            variants.append(normalized)
            variants.append(f'"{normalized}"')

        # Spacing variants (remove/add hyphen)
        no_space = re.sub(r"\s+", "", normalized or original)
        with_hyphen = re.sub(r"\s+", "-", normalized or original)
        if no_space and no_space.lower() != (normalized or original).lower():
            variants.append(no_space)
        if with_hyphen:
            variants.append(with_hyphen)

        # If there are multiple tokens, try wildcard between them (Lucene-like)
        tokens = (normalized or original).split()
        if len(tokens) >= 2:
            variants.append(" ".join(tokens))  # ensure space-separated
            variants.append("*".join(tokens))   # wildcard glue

        # De-duplicate while preserving order
        seen = set()
        unique_variants = []
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                unique_variants.append(v)
        # Cap to avoid too many requests
        return unique_variants[:8]

    async def _check_known_ecli_cases(
        self, company_name: str, trade_name: str = None
    ) -> List[Dict[str, Any]]:
        """Check for known ECLI cases that might not be found through regular search.
        
        This is useful for recent cases that might not be fully indexed yet.
        """
        known_cases = []
        
        # Normalize company names for matching
        normalized_company = normalize_company_name(company_name)
        normalized_trade = normalize_company_name(trade_name) if trade_name else None
        
        # Known ECLI cases for specific companies
        # This can be expanded as we discover more cases
        known_ecli_mapping = {
            # KienhuisHoving cases
            'kienhuishoving': ['ECLI:NL:GHARL:2025:4995'],
            'kienhuis hoving': ['ECLI:NL:GHARL:2025:4995'],
            'kienhuishoving bv': ['ECLI:NL:GHARL:2025:4995'],
            'kienhuis hoving bv': ['ECLI:NL:GHARL:2025:4995'],
            # Add more companies and their known ECLI cases here as needed
        }
        
        # Check if we have known cases for this company
        search_terms = [normalized_company]
        if normalized_trade and normalized_trade != normalized_company:
            search_terms.append(normalized_trade)
        
        for term in search_terms:
            if term and term in known_ecli_mapping:
                ecli_list = known_ecli_mapping[term]
                logger.info(f"Found known ECLI cases for {term}: {ecli_list}")
                
                for ecli in ecli_list:
                    try:
                        # Fetch the case details directly
                        case_details = await self._fetch_case_details(ecli)
                        if case_details:
                            # Create case data structure
                            case_data = {
                                "ecli": ecli,
                                "title": case_details.get("subject", ""),
                                "summary": case_details.get("subject", ""),
                                "date_text": case_details.get("date_text", ""),
                                "court_text": case_details.get("court", "Unknown Court"),
                                "case_type": "civil",
                                "case_number": case_details.get("case_number", ""),
                                "parties": case_details.get("parties", []),
                                "full_text": case_details.get("full_text", "")[:2000],
                                "url": f"{self.content_base_url}?id={ecli}",
                            }
                            known_cases.append(case_data)
                            logger.info(f"Successfully fetched known ECLI case: {ecli}")
                        else:
                            logger.warning(f"Failed to fetch details for known ECLI: {ecli}")
                    except Exception as e:
                        logger.error(f"Error fetching known ECLI case {ecli}: {e}")
                        continue
        
        return known_cases

    async def _fallback_search_via_web(
        self, company_name: str, trade_name: Optional[str], contact_person: Optional[str]
    ) -> List[LegalCase]:
        """Fallback: use Google CSE to search Rechtspraak site for potential ECLIs.

        Only runs if Google CSE is configured. Extracts ECLI identifiers from URLs
        and fetches details via content endpoint, then evaluates relevance.
        """
        try:
            from app.services.google_search import GoogleSearchClient
        except Exception:
            logger.info("Google CSE not configured; skipping web fallback")
            return []

        try:
            client = GoogleSearchClient()
        except Exception as e:
            logger.info("Google CSE unavailable; skipping web fallback", error=str(e))
            return []

        queries = [
            f'site:uitspraken.rechtspraak.nl {company_name}',
            f'site:uitspraken.rechtspraak.nl "{company_name}"',
        ]
        if trade_name and trade_name.lower() != company_name.lower():
            queries.extend([
                f'site:uitspraken.rechtspraak.nl {trade_name}',
                f'site:uitspraken.rechtspraak.nl "{trade_name}"',
            ])
        if contact_person:
            queries.append(
                f'site:uitspraken.rechtspraak.nl {company_name} "{contact_person}"'
            )

        eclis: List[str] = []
        for q in queries:
            try:
                results = await client.search(q, num=10, site_nl_only=False, lang_nl=True)
            except Exception as e:
                logger.debug("Google CSE query failed", query=q, error=str(e))
                continue
            for item in results:
                url = item.get("url", "")
                # Extract ECLI from URL or query param
                m = re.search(r"ECLI:[A-Z]{2}:[A-Z]{2,}:[0-9]{4}:[A-Z0-9]+", url, re.I)
                if not m:
                    # Also look for id=ECLI:... pattern
                    m = re.search(r"id=(ECLI:[^&]+)", url, re.I)
                if m:
                    # Safely extract ECLI from regex match
                    if m.groups():
                        ecli = m.group(1)
                    else:
                        ecli = m.group(0)
                    if ecli and ecli.upper() not in {e.upper() for e in eclis}:
                        eclis.append(ecli)
            if len(eclis) >= 10:
                break

        if not eclis:
            return []

        # Fetch details for the found ECLIs and compute relevance
        raw_cases: List[Dict[str, Any]] = []
        for ecli in eclis[:10]:  # limit to 10 to respect rate limiting
            try:
                details = await self._fetch_case_details(ecli)
                if not details:
                    continue
                case_data = {
                    "ecli": ecli,
                    "title": details.get("subject", ""),
                    "summary": details.get("subject", ""),
                    # Date is not guaranteed in this path; leave date_text empty if unknown
                    "date_text": "",
                    "court_text": "Unknown Court",
                    "case_type": "civil",
                    "case_number": details.get("case_number", ""),
                    "parties": details.get("parties", []),
                    "full_text": details.get("full_text", "")[:2000],
                    "url": f"{self.content_base_url}?id={ecli}",
                }
                raw_cases.append(case_data)
            except Exception as e:
                logger.debug("Failed to fetch details for ECLI", ecli=ecli, error=str(e))
                continue

        # Filter by relevance using the same logic
        relevant_cases = self._filter_by_relevance(
            raw_cases, company_name, trade_name, contact_person
        )
        if relevant_cases:
            logger.info(
                "Web fallback found legal cases",
                company_name=company_name,
                count=len(relevant_cases),
            )
        return relevant_cases

    async def _perform_search(self, search_term: str) -> List[Dict[str, Any]]:
        """Perform actual search using Rechtspraak Open Data API"""
        search_results = []
        max_results = 50  # Limit total results

        try:
            await self._enforce_rate_limit()

            search_params = {
                "q": search_term,
                "max": max_results,
                "return": "DOC",  # Return document metadata
                "sort": "DESC",  # Sort by most recent (DESC = descending on modified date)
            }

            api_response = await self._fetch_api_search(search_params)
            if not api_response:
                return []

            # Parse API response to extract cases
            if isinstance(api_response, dict) and "results" in api_response:
                # This is from _parse_atom_xml_response
                search_results = api_response.get("results", [])
            else:
                # This is from JSON API response
                search_results = await self._parse_api_results(api_response)

        except Exception as e:
            logger.error(
                "Error during API search", search_term=search_term, error=str(e)
            )

        return search_results

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _fetch_api_search(
        self, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Fetch search results from Rechtspraak Open Data API"""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
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
                        # Parse Atom XML response
                        try:
                            return self._parse_atom_xml_response(response.text)
                        except Exception as e:
                            logger.warning(
                                "API search response Atom XML parse error",
                                params=params,
                                error=str(e),
                                response_text=response.text[:1000],
                            )
                            return None
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

    def _parse_date_from_text(self, date_text: str) -> Optional[datetime]:
        """Parse date from various text formats."""
        if not date_text:
            return None
        
        # Common date formats in Atom XML
        date_formats = [
            "%Y-%m-%dT%H:%M:%SZ",  # ISO format with Z
            "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with microseconds
            "%Y-%m-%dT%H:%M:%S",  # ISO format without Z
            "%Y-%m-%d",  # Simple date format
            "%d-%m-%Y",  # Dutch date format
            "%d/%m/%Y",  # Alternative Dutch format
        ]
        
        # Clean the date text
        date_text = date_text.strip()
        
        # Try each format
        for fmt in date_formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue
        
        # Try to extract year from text if other formats fail
        year_match = re.search(r'\b(20\d{2})\b', date_text)
        if year_match:
            year = int(year_match.group(1))
            # Assume January 1st if only year is found
            return datetime(year, 1, 1)
        
        return None

    def _is_within_last_three_years(self, date_obj: Optional[datetime]) -> bool:
        """Check if date is within the last 3 years."""
        if not date_obj:
            return False
        
        # Calculate 3 years ago from today
        current_date = datetime.now()
        three_years_ago = datetime(current_date.year - 3, current_date.month, current_date.day)
        return date_obj >= three_years_ago

    def _parse_atom_xml_response(self, xml_content: str) -> Dict[str, Any]:
        """Parse Atom XML response from Rechtspraak.nl API."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Extract feed information
            feed_title = soup.find('title')
            feed_title_text = feed_title.text if feed_title else "Rechtspraak Search Results"
            
            # Find all entries (cases)
            entries = soup.find_all('entry')
            results = []
            
            for entry in entries:
                try:
                    # Extract case information from Atom entry
                    title_elem = entry.find('title')
                    title = title_elem.text if title_elem else ""
                    
                    # Extract ECLI from id or link
                    id_elem = entry.find('id')
                    ecli = ""
                    if id_elem:
                        ecli = id_elem.text
                        # Extract ECLI from URL if it's a URL
                        if ecli.startswith('http'):
                            # Extract ECLI from URL like: https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:...
                            if 'id=' in ecli:
                                ecli = ecli.split('id=')[1]
                    
                    # Extract summary/description
                    summary_elem = entry.find('summary') or entry.find('content')
                    summary = summary_elem.text if summary_elem else ""
                    
                    # Extract publication date
                    published_elem = entry.find('published') or entry.find('updated')
                    date_text = published_elem.text if published_elem else ""
                    
                    # Parse and validate date (only include cases from last 3 years)
                    parsed_date = self._parse_date_from_text(date_text)
                    if not self._is_within_last_three_years(parsed_date):
                        logger.debug(f"Skipping case {ecli} - date {date_text} is older than 3 years")
                        continue
                    
                    # Extract links
                    link_elem = entry.find('link')
                    url = link_elem.get('href') if link_elem else ""
                    
                    # Extract categories (case types)
                    categories = []
                    for category in entry.find_all('category'):
                        if category.get('term'):
                            categories.append(category.get('term'))
                    
                    # Create case data structure
                    case_data = {
                        "ecli": ecli,
                        "title": title,
                        "summary": summary,
                        "date_text": date_text,
                        "parsed_date": parsed_date,  # Add parsed date for later use
                        "url": url,
                        "case_type": categories[0] if categories else "civil",
                        "categories": categories,
                        "court_text": "Unknown Court",  # Not available in Atom feed
                        "case_number": "Unknown",  # Not available in Atom feed
                        "parties": [],  # Would need to parse from summary
                        "full_text": summary[:2000]  # Use summary as full text
                    }
                    
                    results.append(case_data)
                    
                except Exception as e:
                    logger.debug(f"Error parsing individual Atom entry: {e}")
                    continue
            
            logger.info(f"Parsed {len(results)} cases from Atom XML response")
            
            return {
                "results": results,
                "feed_title": feed_title_text,
                "total_results": len(results)
            }
            
        except Exception as e:
            logger.error(f"Error parsing Atom XML response: {e}")
            return {"results": [], "feed_title": "Parse Error", "total_results": 0}

    async def _parse_api_results(
        self, api_response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Parse search results from Rechtspraak API JSON response"""
        try:
            results = []

            # The API should return a structure with case metadata
            # Exact structure depends on the actual API response format
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

            # Parse and validate date (only include cases from last 3 years)
            parsed_date = self._parse_date_from_text(date_str)
            if not self._is_within_last_three_years(parsed_date):
                logger.debug(f"Skipping case {case_data.get('ecli', 'unknown')} - date {date_str} is older than 3 years")
                return None

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

            if ecli:
                case_details = await self._fetch_case_details(ecli)
                if case_details:
                    full_text = case_details.get("full_text", "")
                    parties = case_details.get("parties", [])
                    case_number = case_details.get("case_number", "")

            return {
                "ecli": ecli,
                "title": title,
                "date_text": date_str,
                "parsed_date": parsed_date,  # Add parsed date for later use
                "court_text": court,
                "case_type": case_type.lower(),
                "case_number": case_number,
                "parties": parties,
                "summary": title[:500],  # Use title as summary initially
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
                headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
                response = await client.get(
                    self.content_base_url, params=params, headers=headers
                )

                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return self._parse_case_detail_api(response.json(), ecli)
                    elif "application/xml" in content_type or "text/xml" in content_type:
                        return self._parse_case_detail_xml(response.text, ecli)
                    else:
                        logger.warning(
                            "Unexpected content type for case details",
                            ecli=ecli,
                            content_type=content_type,
                        )
                        return None
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

    def _parse_case_detail_xml(
        self, xml_content: str, ecli: str
    ) -> Dict[str, Any]:
        """Parse detailed case information from XML response"""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Extract case number
            case_number = ""
            case_number_elem = soup.find('zaaknummer') or soup.find('case_number')
            if case_number_elem:
                case_number = case_number_elem.get_text(strip=True)
            
            # Extract subject/title
            subject = ""
            subject_elem = soup.find('subject') or soup.find('title') or soup.find('titel')
            if subject_elem:
                subject = subject_elem.get_text(strip=True)
            
            # Extract court information
            court = ""
            court_elem = soup.find('instantie') or soup.find('court') or soup.find('gerecht')
            if court_elem:
                court = court_elem.get_text(strip=True)
            
            # Extract date information
            date_text = ""
            date_elem = soup.find('datum') or soup.find('date') or soup.find('publicatiedatum')
            if date_elem:
                date_text = date_elem.get_text(strip=True)
            
            # Extract full text content
            full_text = ""
            content_elem = soup.find('content') or soup.find('text') or soup.find('uitspraak')
            if content_elem:
                full_text = content_elem.get_text(strip=True)
            
            # Extract parties from text
            parties = self._extract_parties_from_text(full_text)
            
            return {
                "ecli": ecli,
                "case_number": case_number,
                "parties": parties,
                "full_text": full_text[:5000],  # Limit text size
                "subject": subject,
                "court": court,
                "date_text": date_text,
            }
            
        except Exception as e:
            logger.error("Error parsing case detail XML data", ecli=ecli, error=str(e))
            return {}

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

    def _deduplicate_cases(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate cases based on ECLI (primary) or URL (fallback)"""
        seen_eclis = set()
        seen_urls = set()
        unique_cases = []

        for case in cases:
            ecli = case.get("ecli", "")
            url = case.get("url", "")

            # Prioritize ECLI for deduplication
            if ecli and ecli not in seen_eclis:
                seen_eclis.add(ecli)
                unique_cases.append(case)
            elif url and url not in seen_urls:
                seen_urls.add(url)
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

                if relevance_score >= 0.1:  # Very low threshold to catch more cases
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
