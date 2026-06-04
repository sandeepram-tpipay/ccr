#!/usr/bin/env python
import argparse
import asyncio
import json
import logging
import os
import re
import sys
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("crawler_cli")

class CalregsCLI:
    """
    Standalone crawling tool for downloading and writing Westlaw Calregs 
    document sections to a structured JSONL archive.
    """
    def __init__(self, output_path: str, max_limit: int = 50):
        self.output_path = output_path
        self.max_limit = max_limit
        self.visited = set()
        self.downloaded_count = 0
        
        # Verify output directory path
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    def write_block_to_jsonl(self, payload: dict):
        """
        Appends regulation record dictionary to JSONL file.
        """
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        logger.info(f"Archived citation {payload['citation']} to JSONL: {self.output_path}")

    def convert_html_structure(self, container_node) -> str:
        """
        Formats standard BeautifulSoup element styles into markdown notations.
        """
        if not container_node:
            return ""
        
        for b_tag in container_node.find_all(['strong', 'b']):
            b_tag.replace_with(f"**{b_tag.get_text()}**")
        for i_tag in container_node.find_all(['em', 'i']):
            i_tag.replace_with(f"*{i_tag.get_text()}*")
        for a_tag in container_node.find_all('a'):
            href = a_tag.get('href', '')
            a_tag.replace_with(f"[{a_tag.get_text()}]({href})")
        for li_tag in container_node.find_all('li'):
            li_tag.replace_with(f"\n* {li_tag.get_text()}")
        for p_tag in container_node.find_all(['p', 'div', 'br']):
            p_tag.insert_before('\n')
            
        text = container_node.get_text()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def parse_calregs_document(self, html_text: str, target_url: str, crawl4ai_text: str = "") -> dict:
        """
        Extracts structured regulation fields from Westlaw calregs HTML content.
        """
        soup = BeautifulSoup(html_text, 'html.parser')
        
        title_num = ""
        title_name = ""
        chapter = ""
        article = ""
        section_num = ""
        section_head = ""
        citation = ""
        content_md = ""

        # Parse Breadcrumbs
        bc_element = soup.find(class_=re.compile(r'breadcrumbs', re.IGNORECASE))
        breadcrumbs = []
        if bc_element:
            breadcrumbs = [
                item.strip() for item in bc_element.find_all(text=True)
                if item.strip() and item.strip() != ">" and item.strip() != "/"
            ]
        else:
            bc_items = soup.select(".co_breadcrumbsList li, .co_breadcrumbs span, div.breadcrumbs a")
            breadcrumbs = [item.get_text().strip() for item in bc_items if item.get_text().strip()]

        logger.info(f"Target breadcrumbs list: {breadcrumbs}")

        for part in breadcrumbs:
            # Search Title
            t_match = re.search(r'Title\s*(?P<num>[0-9]+)[\.\s-]*(?P<name>.*)', part, re.IGNORECASE)
            if t_match:
                title_num = t_match.group('num').strip()
                title_name = t_match.group('name').strip()
                continue
            # Search Chapter
            if re.search(r'Chapter\s*[0-9]+', part, re.IGNORECASE):
                chapter = part.strip()
                continue
            # Search Article
            if re.search(r'Article\s*[0-9]+', part, re.IGNORECASE):
                article = part.strip()
                continue

        # Segment fallbacks
        if not title_num:
            url_path = urlparse(target_url).path
            url_t_match = re.search(r'title\s*([0-9]+)', url_path, re.IGNORECASE)
            if url_t_match:
                title_num = url_t_match.group(1)
                
        if not title_name:
            t_elem = soup.find(string=re.compile(r'Title\s*[0-9]+', re.IGNORECASE))
            if t_elem:
                title_name = t_elem.strip()
                
        if not chapter:
            ch_elem = soup.find(string=re.compile(r'Chapter\s*[0-9]+', re.IGNORECASE))
            if ch_elem:
                chapter = ch_elem.strip()
                
        if not article:
            art_elem = soup.find(string=re.compile(r'Article\s*[0-9]+', re.IGNORECASE))
            if art_elem:
                article = art_elem.strip()

        # Section and Heading details
        heading_node = soup.find(class_=re.compile(r'co_documentTitle|co_title', re.IGNORECASE)) or soup.find('h1')
        if heading_node:
            node_text = heading_node.get_text().strip()
            sec_match = re.search(r'(?:§|Section|Sec\.)\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<head>.*)', node_text, re.IGNORECASE)
            if sec_match:
                section_num = sec_match.group('num').strip()
                section_head = sec_match.group('head').strip()
            else:
                section_head = node_text
                num_only = re.search(r'([0-9]+[a-zA-Z0-9\.\-]*)', node_text)
                if num_only:
                    section_num = num_only.group(1)

        # Build Citation
        if title_num and section_num:
            citation = f"{title_num} CCR § {section_num}"
        else:
            cit_node = soup.find(class_=re.compile(r'co_citation', re.IGNORECASE))
            if cit_node:
                citation = cit_node.get_text().strip()
            else:
                citation = f"CCR Section {section_num or 'Unknown'}"

        # Markdown body
        body_node = soup.find(class_=re.compile(r'co_documentText|co_body|co_paragraph|co_content', re.IGNORECASE))
        if body_node:
            content_md = self.convert_html_structure(body_node)
        
        if not content_md or len(content_md) < 50:
            content_md = crawl4ai_text or soup.get_text().strip()

        return {
            "title_number": title_num,
            "title_name": title_name,
            "chapter": chapter,
            "article": article,
            "section_number": section_num,
            "section_heading": section_head,
            "citation": citation,
            "source_url": target_url,
            "content_markdown": content_md
        }

    async def scrape_section_node(self, crawler, url: str) -> bool:
        """
        Downloads a single Document page, parses structured fields, and writes to output JSONL.
        """
        if url in self.visited:
            return False
        self.visited.add(url)
        
        logger.info(f"Scraping document URL target: {url}")
        try:
            result = await crawler.arun(
                url=url,
                css_selector=".co_documentText,#co_docContentContainer,.co_body"
            )
            
            if not result or not result.success:
                logger.error(f"Scrape request unsuccessful for target: {url}")
                return False
                
            payload = self.parse_calregs_document(
                html_text=result.html, 
                target_url=url, 
                crawl4ai_text=result.markdown
            )
            
            self.write_block_to_jsonl(payload)
            self.downloaded_count += 1
            return True
            
        except Exception as err:
            logger.error(f"Error scraping section target {url}: {err}")
            return False

    async def run_scraper(self, seed_url: str):
        """
        Initializes Crawl4AI crawler framework and starts scanning targets recursively.
        """
        from crawl4ai import AsyncWebCrawler
        
        logger.info("Initializing Crawl4AI engine for standalone crawl...")
        async with AsyncWebCrawler() as crawler:
            parsed_seed = urlparse(seed_url)
            
            # Check direct vs browse seed
            if "/calregs/Document/" in seed_url or "dir.ca.gov/title8/" in seed_url:
                logger.info("Running direct scan for individual target page.")
                await self.scrape_section_node(crawler, seed_url)
            else:
                logger.info("Running recursive link scan from table of contents index...")
                scan_queue = [seed_url]
                
                while scan_queue and self.downloaded_count < self.max_limit:
                    current_url = scan_queue.pop(0)
                    if current_url in self.visited:
                        continue
                        
                    logger.info(f"Scanning index page: {current_url}")
                    self.visited.add(current_url)
                    
                    try:
                        result = await crawler.arun(url=current_url)
                        if not result or not result.success:
                            continue
                            
                        # Extract matches
                        soup = BeautifulSoup(result.html, 'html.parser')
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link['href'].strip()
                            abs_url = urljoin(current_url, href)
                            
                            # Stay on domain
                            if urlparse(abs_url).netloc != parsed_seed.netloc:
                                continue
                                
                            # If document node, crawl
                            if "/calregs/Document/" in abs_url:
                                if abs_url not in self.visited and abs_url not in scan_queue:
                                    success = await self.scrape_section_node(crawler, abs_url)
                                    if success and self.downloaded_count >= self.max_limit:
                                        break
                                        
                            # If index directory node, queue
                            elif "/calregs/Browse/" in abs_url:
                                if abs_url not in self.visited and abs_url not in scan_queue:
                                    scan_queue.append(abs_url)
                                    
                        # Respect rate limiting
                        await asyncio.sleep(1.0)
                        
                    except Exception as err:
                        logger.error(f"Error scanning index page {current_url}: {err}")
                        
        logger.info(f"Crawler CLI script run finalized. Gathered {self.downloaded_count} documents.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebranded California Code of Regulations Scraper CLI")
    parser.add_argument(
        "--url", 
        type=str, 
        default="https://govt.westlaw.com/calregs/Document/I905C8C80D48411DEBC02831C6D6C108C?viewType=FullText",
        help="Seed URL target"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=5, 
        help="Max documents limit to fetch"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="output/ccr_extracted.jsonl", 
        help="File path to save the crawl output JSONL"
    )

    args = parser.parse_args()
    
    asyncio.run(CalregsCLI(output_path=args.output, max_limit=args.limit).run_scraper(args.url))
