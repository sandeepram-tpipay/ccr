import hashlib
import logging
import re
from typing import List, Union
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from app.schemas.models import CCRSection

logger = logging.getLogger(__name__)

class CCRWebCrawler:
    def __init__(self):
        # Dynamically load Crawl4AI so system is resilient even if dependencies are downloading
        try:
            from crawl4ai import AsyncWebCrawler
            self.AsyncWebCrawler = AsyncWebCrawler
            self.crawl4ai_available = True
            logger.info("Crawl4AI is loaded and available for use.")
        except ImportError:
            logger.warning("Crawl4AI library not found. Falling back to manual HTTP parser.")
            self.crawl4ai_available = False

    async def crawl_url(self, url: str, retries: int = 3, backoff_factor: float = 2.0) -> dict:
        """
        Crawls a California Code of Regulations page URL with a retry mechanism.
        Attempts to use Crawl4AI first, then falls back to httpx-based crawler if Crawl4AI fails.
        Returns a dict: {"html": str, "markdown": str}
        """
        import asyncio
        delay = 1.0
        
        for attempt in range(retries):
            try:
                if self.crawl4ai_available:
                    try:
                        logger.info(f"Crawling URL with Crawl4AI (attempt {attempt+1}/{retries}): {url}", extra={"url": url})
                        async with self.AsyncWebCrawler() as crawler:
                            result = await crawler.arun(url=url)
                            if result and result.success:
                                logger.info("Successfully crawled page with Crawl4AI.")
                                return {
                                    "html": result.html or "",
                                    "markdown": result.markdown or ""
                                }
                            else:
                                logger.warning(
                                    f"Crawl4AI returned failure on attempt {attempt+1}. "
                                    f"Success status: {result.success if result else False}"
                                )
                    except Exception as e:
                        logger.warning(f"Crawl4AI exception on attempt {attempt+1}: {e}")
                
                # Falling back to raw HTTP call
                content_html = await self._fallback_crawl(url)
                if content_html:
                    return {
                        "html": content_html,
                        "markdown": ""
                    }
            except Exception as e:
                logger.warning(f"Crawl attempt {attempt+1} encountered error for URL {url}: {e}")
                if attempt == retries - 1:
                    logger.error(f"All crawl retries failed for URL: {url}")
                    raise
                    
            if attempt < retries - 1:
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                delay *= backoff_factor
                
        return {"html": "", "markdown": ""}

    async def _fallback_crawl(self, url: str) -> str:
        """
        Fallback web page scraper returning raw HTML content.
        """
        logger.info(f"Initiating fallback HTTP crawl for URL: {url}", extra={"url": url})
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    def clean_html_to_markdown(self, element) -> str:
        """
        Simple, clean converter that turns HTML tag structures into clean markdown formatting.
        """
        if not element:
            return ""
        
        # We replace some common tag formatting to make it clean markdown
        for tag in element.find_all(['strong', 'b']):
            tag.replace_with(f"**{tag.get_text()}**")
        for tag in element.find_all(['em', 'i']):
            tag.replace_with(f"*{tag.get_text()}*")
        for tag in element.find_all('a'):
            href = tag.get('href', '')
            tag.replace_with(f"[{tag.get_text()}]({href})")
        for tag in element.find_all('li'):
            tag.replace_with(f"\n* {tag.get_text()}")
        for tag in element.find_all(['p', 'div', 'br']):
            tag.insert_before('\n')
            
        text = element.get_text()
        # Clean up excess spaces and carriage returns
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def extract_sections(self, content_data: Union[dict, str], url: str) -> List[CCRSection]:
        """
        Parses text/markdown content to extract California Code of Regulations sections.
        If HTML is provided, extracts full metadata (title_number, chapter, citation, etc.).
        """
        from datetime import datetime, timezone
        retrieved_at = datetime.now(timezone.utc).isoformat()

        if isinstance(content_data, dict):
            html_content = content_data.get("html", "")
            markdown_content = content_data.get("markdown", "")
        else:
            html_content = ""
            markdown_content = content_data

        # Check if we have HTML to parse via DOM
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 1. Parse Breadcrumbs
            breadcrumbs_elem = soup.find(class_=re.compile(r'breadcrumbs', re.IGNORECASE))
            breadcrumbs = []
            if breadcrumbs_elem:
                breadcrumbs = [
                    item.strip() for item in breadcrumbs_elem.find_all(text=True)
                    if item.strip() and item.strip() not in (">", "/", "|")
                ]
            else:
                breadcrumb_items = soup.select(".co_breadcrumbsList li, .co_breadcrumbs span, div.breadcrumbs a")
                breadcrumbs = [item.get_text().strip() for item in breadcrumb_items if item.get_text().strip()]

            logger.info(f"Detected breadcrumb hierarchy: {breadcrumbs}")

            title_number = ""
            title_name = ""
            division = ""
            chapter = ""
            article = ""
            section_number = ""
            section_heading = ""
            citation = ""

            for part in breadcrumbs:
                title_match = re.search(r'Title\s*(?P<num>[0-9]+)[\.\s-]*(?P<name>.*)', part, re.IGNORECASE)
                if title_match:
                    title_number = title_match.group('num').strip()
                    title_name = title_match.group('name').strip()
                    continue
                if re.search(r'Division\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    division = part.strip()
                    continue
                if re.search(r'Chapter\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    chapter = part.strip()
                    continue
                if re.search(r'Article\s*[0-9A-Za-z]+|Subchapter\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    article = part.strip()
                    continue

            # Fallbacks from HTML <title> tag if breadcrumbs are sparse/missing
            title_tag = soup.find('title') or soup.find('TITLE')
            if title_tag:
                page_title = title_tag.get_text().strip()
                title_match = re.search(r'Title\s*(?P<num>[0-9]+)', page_title, re.IGNORECASE)
                if title_match and not title_number:
                    title_number = title_match.group('num').strip()
                    
                sec_match = re.search(r'Section\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<heading>.*)', page_title, re.IGNORECASE)
                if sec_match:
                    if not section_number:
                        section_number = sec_match.group('num').strip()
                    if not section_heading:
                        section_heading = sec_match.group('heading').strip()

            # B. Resolve Title Name, Chapter, and Article from page content headers
            if not title_name:
                title_tag_body = soup.find(string=re.compile(r'Title\s*[0-9]+', re.IGNORECASE))
                if title_tag_body:
                    title_name = title_tag_body.strip()
                    
            if not chapter:
                chapter_tag = soup.find(string=re.compile(r'Chapter\s*[0-9]+', re.IGNORECASE))
                if chapter_tag:
                    chapter = chapter_tag.strip()
                    
            if not article:
                article_tag = soup.find(string=re.compile(r'Article\s*[0-9]+|Subchapter\s*[0-9]+', re.IGNORECASE))
                if article_tag:
                    article = article_tag.strip()

            # Fallback for title_number from URL path
            if not title_number:
                url_path = urlparse(url).path
                title_url_match = re.search(r'title\s*([0-9]+)', url_path, re.IGNORECASE)
                if title_url_match:
                    title_number = title_url_match.group(1)

            # 2. Extract Section Title & Heading
            title_elem = soup.find(class_=re.compile(r'co_documentTitle|co_title', re.IGNORECASE))
            if not title_elem:
                title_elem = soup.find('h1')

            if title_elem:
                title_text = title_elem.get_text().strip()
                sec_match = re.search(r'(?:§|Section|Sec\.)\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<heading>.*)', title_text, re.IGNORECASE)
                if sec_match:
                    if not section_number:
                        section_number = sec_match.group('num').strip()
                    if not section_heading:
                        section_heading = sec_match.group('heading').strip()
                else:
                    if not section_heading:
                        section_heading = title_text
                    if not section_number:
                        num_only = re.search(r'([0-9]+[a-zA-Z0-9\.\-]*)', title_text)
                        if num_only:
                            section_number = num_only.group(1)

            # Build breadcrumbs list dynamically if empty
            if not breadcrumbs:
                if title_number:
                    breadcrumbs.append(f"Title {title_number}" + (f". {title_name}" if title_name else ""))
                if division:
                    breadcrumbs.append(division)
                if chapter:
                    breadcrumbs.append(chapter)
                if article:
                    breadcrumbs.append(article)
                if section_number:
                    breadcrumbs.append(f"Section {section_number}" + (f". {section_heading}" if section_heading else ""))

            # 3. Construct Citation
            if title_number and section_number:
                citation = f"{title_number} CCR § {section_number}"
            else:
                cit_elem = soup.find(class_=re.compile(r'co_citation', re.IGNORECASE))
                if cit_elem:
                    citation = cit_elem.get_text().strip()
                else:
                    citation = f"CCR Section {section_number or 'Unknown'}"

            # 4. Extract Content Markdown
            content_elem = soup.find(class_=re.compile(r'co_documentText|co_body|co_paragraph|co_content', re.IGNORECASE))
            content_markdown = ""
            if content_elem:
                content_markdown = self.clean_html_to_markdown(content_elem)
            
            if not content_markdown or len(content_markdown) < 50:
                content_markdown = markdown_content or soup.get_text().strip()

            # If we found a valid section, return it as a single-item list
            if section_number or content_markdown:
                sec_id = hashlib.md5(f"{url}_{section_number}_{section_heading}".encode()).hexdigest()
                return [
                    CCRSection(
                        id=sec_id,
                        title=section_heading or "California Code of Regulations Section",
                        section_number=section_number or "unknown",
                        content=content_markdown,
                        url=url,
                        citation=citation,
                        title_number=title_number or None,
                        title_name=title_name or None,
                        division=division or None,
                        chapter=chapter or None,
                        article=article or None,
                        breadcrumb_path=breadcrumbs,
                        retrieved_at=retrieved_at,
                        metadata={"extraction_method": "beautifulsoup_dom"}
                    )
                ]

        # FALLBACK: Regex parsing (if html is empty or DOM parsing returned nothing)
        logger.warning("Falling back to regex split on markdown text.")
        section_pattern = re.compile(
            r'(?:^|\n)(?P<header>#*\s*(?:§|Section|Sec\.)\s*(?P<section_num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[ \t\.\-\–]*(?P<title>[^\n]*))',
            re.IGNORECASE
        )
        
        matches = list(section_pattern.finditer(markdown_content))
        sections: List[CCRSection] = []
        
        if not matches:
            paragraphs = [p.strip() for p in markdown_content.split("\n\n") if len(p.strip()) > 30]
            for idx, p in enumerate(paragraphs):
                section_num = f"chunk-{idx+1}"
                title = f"Document Chunk {idx+1}"
                sec_id = hashlib.md5(f"{url}_{idx}_{p[:30]}".encode()).hexdigest()
                sections.append(CCRSection(
                    id=sec_id,
                    title=title,
                    section_number=section_num,
                    content=p,
                    url=url,
                    citation=f"Section {section_num}",
                    breadcrumb_path=[],
                    retrieved_at=retrieved_at,
                    metadata={"chunk_index": idx, "extraction_method": "paragraph_chunking"}
                ))
            
            if not sections and markdown_content.strip():
                sec_id = hashlib.md5(f"{url}_full".encode()).hexdigest()
                sections.append(CCRSection(
                    id=sec_id,
                    title="California Code of Regulations Page Content",
                    section_number="full-page",
                    content=markdown_content.strip(),
                    url=url,
                    citation="CCR Full Page",
                    breadcrumb_path=[],
                    retrieved_at=retrieved_at,
                    metadata={"extraction_method": "full_page_fallback"}
                ))
            return sections

        for i, match in enumerate(matches):
            section_num = match.group('section_num').strip()
            title = match.group('title').strip() or f"Section {section_num}"
            header = match.group('header').strip()
            
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_content)
            
            section_content = markdown_content[start_pos:end_pos].strip()
            full_section_content = f"{header}\n\n{section_content}"
            sec_id = hashlib.md5(f"{url}_{section_num}_{title}".encode()).hexdigest()
            
            sections.append(CCRSection(
                id=sec_id,
                title=title,
                section_number=section_num,
                content=full_section_content,
                url=url,
                citation=f"CCR § {section_num}",
                breadcrumb_path=[],
                retrieved_at=retrieved_at,
                metadata={"index": i, "extraction_method": "regex_section_split"}
            ))
            
        return sections

    def discover_urls(self, content_text: str, base_url: str) -> List[str]:
        """
        Discovers and extracts absolute URLs from raw content text, resolving relative links.
        Restricts links to the same domain to prevent runaway crawls.
        """
        markdown_links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', content_text)
        html_links = re.findall(r'href=["\']([^"\']+)["\']', content_text)
        
        raw_links = set(markdown_links + html_links)
        discovered = set()
        
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        
        for link in raw_links:
            link = link.strip()
            if not link or link.startswith("#") or link.lower().startswith("javascript:"):
                continue
                
            absolute_url = urljoin(base_url, link)
            parsed_abs = urlparse(absolute_url)
            if parsed_abs.netloc == base_domain:
                normalized_url = absolute_url.split("#")[0].split("?")[0]
                discovered.add(normalized_url)
                
        logger.info(f"Discovered {len(discovered)} matching domain URLs from base URL: {base_url}")
        return sorted(list(discovered))
