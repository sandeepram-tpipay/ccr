import hashlib
import logging
import re
from typing import List, Union, Dict, Any
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from compliance_engine.models.data_models import RegulationBlock

logger = logging.getLogger(__name__)

class RegScraper:
    """
    Handles crawling pages from Westlaw Calregs or directory sites, extracting 
    structured regulation information, and cleaning HTML documents to Markdown.
    """
    def __init__(self):
        # Dynamic import wrapper for crawl4ai to verify presence
        try:
            from crawl4ai import AsyncWebCrawler
            self.AsyncWebCrawler = AsyncWebCrawler
            self.crawl4ai_present = True
            logger.info("Crawl4AI engine integrated successfully.")
        except ImportError:
            logger.warning("Crawl4AI engine not detected in environment. Operating in HTTP fallback mode.")
            self.crawl4ai_present = False

    async def fetch_page(self, target_url: str, retry_count: int = 3, retry_delay: float = 2.0) -> Dict[str, str]:
        """
        Fetches web page data from a given URL.
        First tries Crawl4AI browser crawl, falling back to httpx if it fails or isn't installed.
        """
        import asyncio
        current_delay = 1.0
        
        for attempt in range(retry_count):
            try:
                if self.crawl4ai_present:
                    try:
                        logger.info(f"Crawl4AI scanning page (attempt {attempt+1}/{retry_count}): {target_url}")
                        async with self.AsyncWebCrawler() as crawler:
                            result = await crawler.arun(url=target_url)
                            if result and result.success:
                                logger.info(f"Crawl4AI successfully scanned: {target_url}")
                                return {
                                    "html": result.html or "",
                                    "markdown": result.markdown or ""
                                }
                            else:
                                logger.warning(f"Crawl4AI returned unsuccessful status on attempt {attempt+1}")
                    except Exception as crawler_error:
                        logger.warning(f"Crawl4AI exception raised on attempt {attempt+1}: {crawler_error}")

                # Fallback to standard HTTP GET request
                raw_html = await self._http_get_fallback(target_url)
                if raw_html:
                    return {
                        "html": raw_html,
                        "markdown": ""
                    }
            except Exception as req_error:
                logger.warning(f"Fetch failure on attempt {attempt+1} for URL {target_url}: {req_error}")
                if attempt == retry_count - 1:
                    logger.error(f"All fetch attempts failed for: {target_url}")
                    raise
            
            if attempt < retry_count - 1:
                logger.info(f"Backoff delay sleeping for {current_delay}s...")
                await asyncio.sleep(current_delay)
                current_delay *= retry_delay

        return {"html": "", "markdown": ""}

    async def _http_get_fallback(self, url: str) -> str:
        """
        Basic HTTP GET fallback using httpx.
        """
        logger.info(f"Initiating httpx fallback request: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    def convert_html_structure(self, container_element) -> str:
        """
        Walks through a BeautifulSoup DOM element and converts core markup 
        tags into clean Markdown notation.
        """
        if not container_element:
            return ""
            
        # Parse inline styling and tags into markdown
        for bold_tag in container_element.find_all(['strong', 'b']):
            bold_tag.replace_with(f"**{bold_tag.get_text()}**")
            
        for italic_tag in container_element.find_all(['em', 'i']):
            italic_tag.replace_with(f"*{italic_tag.get_text()}*")
            
        for anchor_tag in container_element.find_all('a'):
            link_ref = anchor_tag.get('href', '')
            anchor_tag.replace_with(f"[{anchor_tag.get_text()}]({link_ref})")
            
        for list_item in container_element.find_all('li'):
            list_item.replace_with(f"\n* {list_item.get_text()}")
            
        for block_tag in container_element.find_all(['p', 'div', 'br']):
            block_tag.insert_before('\n')
            
        cleaned_text = container_element.get_text()
        # Remove extra whitespace runs and duplicate newlines
        cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text)
        return cleaned_text.strip()

    def parse_regulations(self, document_content: Union[dict, str], source_url: str) -> List[RegulationBlock]:
        """
        Processes content payload (HTML/Markdown) to parse and structure CCR sections.
        Returns a list of RegulationBlock elements.
        """
        utc_now = datetime.now(timezone.utc).isoformat()

        if isinstance(document_content, dict):
            html_content = document_content.get("html", "")
            markdown_content = document_content.get("markdown", "")
        else:
            html_content = ""
            markdown_content = document_content

        # Case A: Parse HTML DOM structures with BeautifulSoup
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract breadcrumbs
            bc_container = soup.find(class_=re.compile(r'breadcrumbs', re.IGNORECASE))
            breadcrumbs = []
            if bc_container:
                breadcrumbs = [
                    elem.strip() for elem in bc_container.find_all(text=True)
                    if elem.strip() and elem.strip() not in (">", "/", "|")
                ]
            else:
                list_items = soup.select(".co_breadcrumbsList li, .co_breadcrumbs span, div.breadcrumbs a")
                breadcrumbs = [item.get_text().strip() for item in list_items if item.get_text().strip()]

            logger.info(f"Parsed breadcrumb paths: {breadcrumbs}")

            title_num = ""
            title_name = ""
            division = ""
            chapter = ""
            subchapter = ""
            section_num = ""
            section_head = ""
            citation = ""

            for part in breadcrumbs:
                t_match = re.search(r'Title\s*(?P<num>[0-9]+)[\.\s-]*(?P<name>.*)', part, re.IGNORECASE)
                if t_match:
                    title_num = t_match.group('num').strip()
                    title_name = t_match.group('name').strip()
                    continue
                if re.search(r'Division\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    division = part.strip()
                    continue
                if re.search(r'Chapter\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    chapter = part.strip()
                    continue
                if re.search(r'Article\s*[0-9A-Za-z]+|Subchapter\s*[0-9A-Za-z]+', part, re.IGNORECASE):
                    subchapter = part.strip()
                    continue

            # Fallback search from page Title
            html_title = soup.find('title') or soup.find('TITLE')
            if html_title:
                page_text = html_title.get_text().strip()
                t_match = re.search(r'Title\s*(?P<num>[0-9]+)', page_text, re.IGNORECASE)
                if t_match and not title_num:
                    title_num = t_match.group('num').strip()
                    
                s_match = re.search(r'Section\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<head>.*)', page_text, re.IGNORECASE)
                if s_match:
                    if not section_num:
                        section_num = s_match.group('num').strip()
                    if not section_head:
                        section_head = s_match.group('head').strip()

            # Page content headers fallback
            if not title_name:
                header_elem = soup.find(string=re.compile(r'Title\s*[0-9]+', re.IGNORECASE))
                if header_elem:
                    title_name = header_elem.strip()
                    
            if not chapter:
                chapter_elem = soup.find(string=re.compile(r'Chapter\s*[0-9]+', re.IGNORECASE))
                if chapter_elem:
                    chapter = chapter_elem.strip()
                    
            if not subchapter:
                sub_elem = soup.find(string=re.compile(r'Article\s*[0-9]+|Subchapter\s*[0-9]+', re.IGNORECASE))
                if sub_elem:
                    subchapter = sub_elem.strip()

            # Resolve from URL segment path
            if not title_num:
                path_segments = urlparse(source_url).path
                url_t_match = re.search(r'title\s*([0-9]+)', path_segments, re.IGNORECASE)
                if url_t_match:
                    title_num = url_t_match.group(1)

            # Section headers parsing
            title_node = soup.find(class_=re.compile(r'co_documentTitle|co_title', re.IGNORECASE)) or soup.find('h1')
            if title_node:
                text_heading = title_node.get_text().strip()
                s_match = re.search(r'(?:§|Section|Sec\.)\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<head>.*)', text_heading, re.IGNORECASE)
                if s_match:
                    if not section_num:
                        section_num = s_match.group('num').strip()
                    if not section_head:
                        section_head = s_match.group('head').strip()
                else:
                    if not section_head:
                        section_head = text_heading
                    if not section_num:
                        num_regex = re.search(r'([0-9]+[a-zA-Z0-9\.\-]*)', text_heading)
                        if num_regex:
                            section_num = num_regex.group(1)

            # Ensure breadcrumbs contains at least something if parsed empty
            if not breadcrumbs:
                if title_num:
                    breadcrumbs.append(f"Title {title_num}" + (f". {title_name}" if title_name else ""))
                if division:
                    breadcrumbs.append(division)
                if chapter:
                    breadcrumbs.append(chapter)
                if subchapter:
                    breadcrumbs.append(subchapter)
                if section_num:
                    breadcrumbs.append(f"Section {section_num}" + (f". {section_head}" if section_head else ""))

            # Rebuild citation schema
            if title_num and section_num:
                citation = f"{title_num} CCR § {section_num}"
            else:
                cit_node = soup.find(class_=re.compile(r'co_citation', re.IGNORECASE))
                if cit_node:
                    citation = cit_node.get_text().strip()
                else:
                    citation = f"CCR Section {section_num or 'Unknown'}"

            # Extract main markdown text
            body_node = soup.find(class_=re.compile(r'co_documentText|co_body|co_paragraph|co_content', re.IGNORECASE))
            main_markdown = ""
            if body_node:
                main_markdown = self.convert_html_structure(body_node)
            
            if not main_markdown or len(main_markdown) < 50:
                main_markdown = markdown_content or soup.get_text().strip()

            if section_num or main_markdown:
                uid = hashlib.md5(f"{source_url}_{section_num}_{section_head}".encode()).hexdigest()
                return [
                    RegulationBlock(
                        id=uid,
                        title_number=title_num or None,
                        title_name=title_name or None,
                        division=division or None,
                        chapter=chapter or None,
                        subchapter=subchapter or None,
                        section_number=section_num or "unknown",
                        section_heading=section_head or "California Code of Regulations Section",
                        citation=citation,
                        breadcrumb_path=breadcrumbs,
                        source_url=source_url,
                        content_markdown=main_markdown,
                        retrieved_at=utc_now,
                        metadata={"origin": "beautifulsoup_dom"}
                    )
                ]

        # Case B: Fallback Regex splitter on raw text
        logger.warning("No HTML available or DOM parse yielded nothing. Splitting via regular expressions.")
        pattern = re.compile(
            r'(?:^|\n)(?P<header>#*\s*(?:§|Section|Sec\.)\s*(?P<section_num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[ \t\.\-\–]*(?P<head>[^\n]*))',
            re.IGNORECASE
        )
        
        matches = list(pattern.finditer(markdown_content))
        blocks: List[RegulationBlock] = []
        
        if not matches:
            # Paragraph chunking
            paragraphs = [p.strip() for p in markdown_content.split("\n\n") if len(p.strip()) > 30]
            for i, paragraph in enumerate(paragraphs):
                dummy_num = f"chunk-{i+1}"
                dummy_head = f"Document Section Segment {i+1}"
                uid = hashlib.md5(f"{source_url}_{i}_{paragraph[:30]}".encode()).hexdigest()
                blocks.append(
                    RegulationBlock(
                        id=uid,
                        section_number=dummy_num,
                        section_heading=dummy_head,
                        citation=f"Section {dummy_num}",
                        source_url=source_url,
                        content_markdown=paragraph,
                        retrieved_at=utc_now,
                        metadata={"chunk_index": i, "origin": "paragraph_split"}
                    )
                )
            
            if not blocks and markdown_content.strip():
                uid = hashlib.md5(f"{source_url}_fulltext".encode()).hexdigest()
                blocks.append(
                    RegulationBlock(
                        id=uid,
                        section_number="full-page",
                        section_heading="California Code of Regulations Page Content",
                        citation="CCR Full Page",
                        source_url=source_url,
                        content_markdown=markdown_content.strip(),
                        retrieved_at=utc_now,
                        metadata={"origin": "full_text_fallback"}
                    )
                )
            return blocks

        for i, match in enumerate(matches):
            section_num = match.group('section_num').strip()
            section_head = match.group('head').strip() or f"Section {section_num}"
            header_line = match.group('header').strip()
            
            start_idx = match.end()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_content)
            
            content_body = markdown_content[start_idx:end_idx].strip()
            full_markdown = f"{header_line}\n\n{content_body}"
            uid = hashlib.md5(f"{source_url}_{section_num}_{section_head}".encode()).hexdigest()
            
            blocks.append(
                RegulationBlock(
                    id=uid,
                    section_number=section_num,
                    section_heading=section_head,
                    citation=f"CCR § {section_num}",
                    source_url=source_url,
                    content_markdown=full_markdown,
                    retrieved_at=utc_now,
                    metadata={"regex_index": i, "origin": "regex_split"}
                )
            )
            
        return blocks

    def extract_links(self, document_text: str, current_url: str) -> List[str]:
        """
        Discovers anchor tag hrefs and markdown URLs from text blocks.
        Restricts links to the same domain to prevent runaway spidering.
        """
        markdown_urls = re.findall(r'\[[^\]]*\]\(([^)]+)\)', document_text)
        html_urls = re.findall(r'href=["\']([^"\']+)["\']', document_text)
        
        candidates = set(markdown_urls + html_urls)
        discovered = set()
        
        parsed_base = urlparse(current_url)
        allowed_domain = parsed_base.netloc
        
        for url in candidates:
            url = url.strip()
            if not url or url.startswith("#") or url.lower().startswith("javascript:"):
                continue
                
            absolute_url = urljoin(current_url, url)
            parsed_candidate = urlparse(absolute_url)
            
            if parsed_candidate.netloc == allowed_domain:
                # Remove URL hashes and query params to normalize
                normalized = absolute_url.split("#")[0].split("?")[0]
                discovered.add(normalized)
                
        logger.info(f"Scanned {len(discovered)} unique matching domain links from: {current_url}")
        return sorted(list(discovered))
