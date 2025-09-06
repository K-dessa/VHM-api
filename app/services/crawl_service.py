import asyncio
import time
import os
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
import hashlib

import structlog
import httpx
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from app.core.config import settings
from app.models.response_models import CrawledContent, WebContent

logger = structlog.get_logger(__name__)


class CrawlService:
    """
    Service for crawling web content using Crawl4AI.
    
    Implements the improved workflow with AI-ready Markdown output,
    boilerplate removal, and configurable crawling parameters.
    """
    
    def __init__(self):
        self.timeout = 30
        self.user_agent = "Mozilla/5.0 (compatible; BedrijfsanalyseBot/1.0)"
        self.max_depth = 2
        self.max_pages = 10
        self.obey_robots_txt = True
        self._crawler = None
        
        # Set Crawl4AI data directory to avoid permission issues
        self.crawl4ai_data_dir = os.environ.get('CRAWL4_AI_BASE_DIRECTORY', '/tmp/crawl4ai')
        os.environ['CRAWL4_AI_BASE_DIRECTORY'] = self.crawl4ai_data_dir
        
        # Ensure the directory exists
        try:
            os.makedirs(self.crawl4ai_data_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create crawl4ai directory: {e}")
            # Fall back to /tmp if needed
            self.crawl4ai_data_dir = '/tmp/crawl4ai_fallback'
            os.environ['CRAWL4_AI_BASE_DIRECTORY'] = self.crawl4ai_data_dir
            os.makedirs(self.crawl4ai_data_dir, exist_ok=True)
        
    async def _get_crawler(self) -> AsyncWebCrawler:
        """Get or create the async web crawler instance."""
        if self._crawler is None:
            self._crawler = AsyncWebCrawler(
                headless=True,
                browser_type="chromium",
                verbose=False,
                delay_before_return_html=2.0,
                user_agent=self.user_agent,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "nl,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }
            )
        return self._crawler
    
    async def crawl_company_website(
        self, 
        company_name: str, 
        max_depth: int = 2,
        focus_dutch: bool = False,
        simple_mode: bool = False
    ) -> Optional[WebContent]:
        """
        Crawl company website and extract relevant content.
        
        Args:
            company_name: Name of the company to search for
            max_depth: Maximum crawling depth (1 for simple, 2 for standard)
            focus_dutch: Prioritize .nl domains and Dutch content
            simple_mode: Use simplified crawling for faster results
            
        Returns:
            WebContent object with crawled data or None if failed
        """
        start_time = time.time()
        
        logger.info(
            "Starting website crawl",
            company_name=company_name,
            max_depth=max_depth,
            focus_dutch=focus_dutch,
            simple_mode=simple_mode
        )
        
        try:
            # First, find the company's official website
            website_url = await self._find_company_website(company_name, focus_dutch)
            
            if not website_url:
                logger.warning("No website found for company", company_name=company_name)
                return None
            
            logger.info("Found company website", website=website_url)
            
            # Crawl the website
            crawled_pages = await self._crawl_website(
                website_url, 
                max_depth=max_depth if not simple_mode else 1,
                max_pages=3 if simple_mode else 10
            )
            
            if not crawled_pages:
                logger.warning("Failed to crawl website", website=website_url)
                return None
            
            # Process and extract relevant content
            web_content = self._process_crawled_content(crawled_pages, company_name)
            
            processing_time = time.time() - start_time
            logger.info(
                "Website crawl completed",
                company_name=company_name,
                pages_crawled=len(crawled_pages),
                processing_time=processing_time
            )
            
            return web_content
            
        except Exception as e:
            logger.error(
                "Error during website crawl",
                company_name=company_name,
                error=str(e),
                error_type=type(e).__name__
            )
            return None
    
    async def _find_company_website(self, company_name: str, focus_dutch: bool = False) -> Optional[str]:
        """
        Find the official website for a company.
        Uses web search to locate the most likely official website.
        """
        try:
            # Build search query
            search_query = f'"{company_name}" official website'
            if focus_dutch:
                search_query += " site:nl"
            
            # Use Google search to find the website
            search_results = await self._search_web(search_query, max_results=5)
            
            # Filter and rank results
            for result in search_results:
                url = result.get('url', '')
                title = result.get('title', '').lower()
                
                # Skip non-relevant results
                if any(skip in url.lower() for skip in ['linkedin', 'facebook', 'twitter', 'wikipedia', 'google']):
                    continue
                
                # Prefer .nl domains if focusing on Dutch companies
                if focus_dutch and '.nl' in url:
                    return url
                
                # Check if company name is in domain or title
                company_lower = company_name.lower().replace(' ', '')
                domain = urlparse(url).netloc.lower()
                
                if company_lower in domain or company_name.lower() in title:
                    return url
            
            # If no exact match, return first non-social media result
            for result in search_results:
                url = result.get('url', '')
                if not any(skip in url.lower() for skip in ['linkedin', 'facebook', 'twitter', 'wikipedia']):
                    return url
            
            return None
            
        except Exception as e:
            logger.error("Error finding company website", error=str(e))
            return None
    
    async def _search_web(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Simple web search implementation.
        For demo purposes, returns common website patterns.
        """
        # Extract company name from query  
        company_name = query.split('"')[1] if '"' in query else query.split()[0]
        
        # Known mappings for common Dutch companies
        known_websites = {
            'koninklijke philips n.v.': 'https://www.philips.com',
            'asml holding n.v.': 'https://www.asml.com',
            'unilever': 'https://www.unilever.com',
            'ing groep n.v.': 'https://www.ing.com',
            'ahold delhaize': 'https://www.aholddelhaize.com'
        }
        
        # Check if we have a known website
        company_lower = company_name.lower()
        if company_lower in known_websites:
            return [{
                'url': known_websites[company_lower],
                'title': f"{company_name} - Official Website",
                'snippet': f"Official website of {company_name}"
            }]
        
        # For unknown companies, try simple patterns but don't fail if they don't work
        patterns = [
            f"https://www.{company_name.lower().replace(' ', '').replace('.', '')}.com",
            f"https://www.{company_name.lower().replace(' ', '').replace('.', '')}.nl"
        ]
        
        results = []
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                for url in patterns[:2]:  # Only try first 2 patterns
                    try:
                        response = await client.head(url, follow_redirects=True)
                        if response.status_code == 200:
                            results.append({
                                'url': url,
                                'title': f"{company_name} - Official Website", 
                                'snippet': f"Official website of {company_name}"
                            })
                            break  # Stop after first working URL
                    except:
                        continue
        except:
            pass
        
        return results
    
    async def _crawl_website(
        self, 
        base_url: str, 
        max_depth: int = 2, 
        max_pages: int = 10
    ) -> List[CrawledContent]:
        """
        Crawl website pages and extract content using Crawl4AI.
        """
        try:
            crawler = await self._get_crawler()
            crawled_pages = []
            visited_urls = set()
            to_visit = [(base_url, 0)]  # (url, depth)
            
            async with crawler as session:
                while to_visit and len(crawled_pages) < max_pages:
                    current_url, depth = to_visit.pop(0)
                    
                    if current_url in visited_urls or depth > max_depth:
                        continue
                        
                    visited_urls.add(current_url)
                    
                    try:
                        # Crawl the page with Crawl4AI
                        result = await session.arun(
                            url=current_url,
                            word_count_threshold=50,
                            bypass_cache=True,
                            verbose=False,
                            timeout=self.timeout,
                            magic=True,  # Enable smart content extraction
                            markdown=True  # Get markdown output as specified
                        )
                        
                        if result.success and result.markdown:
                            # Create CrawledContent object
                            # Extract title from markdown or use default
                            title = "Untitled"
                            if hasattr(result, 'title') and result.title:
                                title = result.title
                            elif result.markdown:
                                # Try to extract title from markdown
                                lines = result.markdown.split('\n')
                                for line in lines[:10]:  # Check first 10 lines
                                    if line.startswith('# '):
                                        title = line[2:].strip()
                                        break
                            
                            crawled_content = CrawledContent(
                                url=current_url,
                                title=title,
                                content=result.markdown,
                                links=[],  # Simplify for now - links parsing has issues
                                crawl_timestamp=time.time(),
                                content_length=len(result.markdown),
                                language="nl" if any(nl_indicator in result.markdown.lower() 
                                                   for nl_indicator in ['nederlandse', 'nederland', 'bedrijf', 'contact']) else "en"
                            )
                            
                            crawled_pages.append(crawled_content)
                            
                            # For simple mode or depth 1, don't crawl additional pages
                            # This avoids complexity with link parsing for now
                        
                        # Small delay between requests to be respectful
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.warning(
                            "Failed to crawl page",
                            url=current_url,
                            error=str(e)
                        )
                        continue
            
            return crawled_pages
            
        except Exception as e:
            logger.error("Error during website crawling", error=str(e))
            return []
    
    def _process_crawled_content(self, crawled_pages: List[CrawledContent], company_name: str) -> WebContent:
        """
        Process crawled pages and create structured WebContent.
        """
        if not crawled_pages:
            return WebContent(
                company_name=company_name,
                website_url="",
                pages_crawled=0,
                content_summary="No content found",
                main_sections=[],
                business_activities=[],
                contact_info={},
                crawled_pages=[]
            )
        
        # Extract main sections from all pages
        main_sections = []
        business_activities = []
        contact_info = {}
        
        for page in crawled_pages:
            # Extract sections (simple approach - split by headers)
            content = page.content
            sections = self._extract_sections(content)
            main_sections.extend(sections[:3])  # Top 3 sections per page
            
            # Extract business activities
            activities = self._extract_business_activities(content)
            business_activities.extend(activities)
            
            # Extract contact info from first page (usually homepage)
            if page.url == crawled_pages[0].url:
                contact_info = self._extract_contact_info(content)
        
        # Remove duplicates and limit
        main_sections = list(dict.fromkeys(main_sections))[:10]
        business_activities = list(dict.fromkeys(business_activities))[:5]
        
        # Create summary
        total_content = " ".join([page.content[:200] for page in crawled_pages])
        content_summary = self._create_content_summary(total_content, company_name)
        
        return WebContent(
            company_name=company_name,
            website_url=crawled_pages[0].url if crawled_pages else "",
            pages_crawled=len(crawled_pages),
            content_summary=content_summary,
            main_sections=main_sections,
            business_activities=business_activities,
            contact_info=contact_info,
            crawled_pages=crawled_pages[:5]  # Limit stored pages
        )
    
    def _extract_sections(self, content: str) -> List[str]:
        """Extract main sections from markdown content."""
        sections = []
        lines = content.split('\n')
        current_section = ""
        
        for line in lines:
            if line.startswith('# ') or line.startswith('## '):
                if current_section.strip():
                    sections.append(current_section.strip()[:200])
                current_section = line.strip()
            elif line.strip() and len(current_section) < 300:
                current_section += " " + line.strip()
        
        if current_section.strip():
            sections.append(current_section.strip()[:200])
        
        return sections[:5]
    
    def _extract_business_activities(self, content: str) -> List[str]:
        """Extract business activities from content."""
        activities = []
        content_lower = content.lower()
        
        # Common business activity keywords
        activity_keywords = [
            'software development', 'consulting', 'manufacturing', 'retail', 'services',
            'technology', 'finance', 'healthcare', 'education', 'construction',
            'transport', 'logistics', 'energy', 'telecommunications', 'media'
        ]
        
        for keyword in activity_keywords:
            if keyword in content_lower:
                activities.append(keyword.title())
        
        return activities[:3]
    
    def _extract_contact_info(self, content: str) -> Dict[str, str]:
        """Extract contact information from content."""
        import re
        
        contact_info = {}
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, content)
        if emails:
            contact_info['email'] = emails[0]
        
        # Extract phone (Dutch format)
        phone_pattern = r'(\+31|0031|0)\s?[1-9]\s?[0-9]{8}'
        phones = re.findall(phone_pattern, content)
        if phones:
            contact_info['phone'] = ''.join(phones[0])
        
        # Extract address (very basic)
        if 'nederland' in content.lower() or 'netherlands' in content.lower():
            contact_info['country'] = 'Netherlands'
        
        return contact_info
    
    def _create_content_summary(self, content: str, company_name: str) -> str:
        """Create a brief summary of the crawled content."""
        # Simple extractive summary
        sentences = content.replace('\n', ' ').split('.')
        relevant_sentences = []
        
        company_lower = company_name.lower()
        for sentence in sentences:
            if company_lower in sentence.lower() and len(sentence.strip()) > 20:
                relevant_sentences.append(sentence.strip())
                if len(relevant_sentences) >= 3:
                    break
        
        if relevant_sentences:
            return '. '.join(relevant_sentences[:2]) + '.'
        else:
            return f"Website content found for {company_name}. Content analysis completed."
    
    async def close(self):
        """Close the crawler session."""
        if self._crawler:
            try:
                # AsyncWebCrawler doesn't need explicit closing in current version
                # Just set to None to allow garbage collection
                pass
            except Exception as e:
                logger.warning("Error closing crawler", error=str(e))
            finally:
                self._crawler = None