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
logger = logging.getLogger("ccr_crawler")

class CCRScraper:
    def __init__(self, output_file: str, limit: int = 50):
        self.output_file = output_file
        self.limit = limit
        self.visited_urls = set()
        self.crawled_count = 0
        
        # Ensure output directory exists
        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    def write_to_jsonl(self, data: dict):
        """
        Appends the parsed regulatory section data to the JSONL output file.
        """
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")
        logger.info(f"Written section {data['citation']} to JSONL: {self.output_file}")

    def clean_html_to_markdown(self, element) -> str:
        """
        Simple, clean converter that turns HTML tag structures into clean markdown formatting.
        Used as a fallback or refinement.
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

    def parse_document_page(self, html_content: str, url: str, crawl4ai_markdown: str = "") -> dict:
        """
        Parses a Westlaw Calregs Document page to extract structured fields.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        title_number = ""
        title_name = ""
        chapter = ""
        article = ""
        section_number = ""
        section_heading = ""
        citation = ""
        content_markdown = ""

        # 1. Parse Breadcrumbs
        # Breadcrumbs are usually in a container containing 'breadcrumbs' or 'co_breadcrumbs' in class
        breadcrumbs_elem = soup.find(class_=re.compile(r'breadcrumbs', re.IGNORECASE))
        breadcrumbs = []
        if breadcrumbs_elem:
            # Gather all plain text elements within breadcrumbs, ignoring '>' separator symbols
            breadcrumbs = [
                item.strip() for item in breadcrumbs_elem.find_all(text=True)
                if item.strip() and item.strip() != ">" and item.strip() != "/"
            ]
        else:
            # Fallback list items breadcrumbs
            breadcrumb_items = soup.select(".co_breadcrumbsList li, .co_breadcrumbs span, div.breadcrumbs a")
            breadcrumbs = [item.get_text().strip() for item in breadcrumb_items if item.get_text().strip()]

        logger.info(f"Detected breadcrumb hierarchy: {breadcrumbs}")

        for part in breadcrumbs:
            # Search for Title (e.g. "Title 8. Industrial Relations")
            title_match = re.search(r'Title\s*(?P<num>[0-9]+)[\.\s-]*(?P<name>.*)', part, re.IGNORECASE)
            if title_match:
                title_number = title_match.group('num').strip()
                title_name = title_match.group('name').strip()
                continue
            # Search for Chapter
            if re.search(r'Chapter\s*[0-9]+', part, re.IGNORECASE):
                chapter = part.strip()
                continue
            # Search for Article
            if re.search(r'Article\s*[0-9]+', part, re.IGNORECASE):
                article = part.strip()
                continue

        # --- Fallback Heuristics for Simple/Alternative layouts (like dir.ca.gov) ---
        # A. Resolve Title Number from URL path
        if not title_number:
            url_path = urlparse(url).path
            title_url_match = re.search(r'title\s*([0-9]+)', url_path, re.IGNORECASE)
            if title_url_match:
                title_number = title_url_match.group(1)
                
        # B. Resolve Title Name, Chapter, and Article from page content headers
        if not title_name:
            title_tag = soup.find(string=re.compile(r'Title\s*[0-9]+', re.IGNORECASE))
            if title_tag:
                title_name = title_tag.strip()
                
        if not chapter:
            chapter_tag = soup.find(string=re.compile(r'Chapter\s*[0-9]+', re.IGNORECASE))
            if chapter_tag:
                chapter = chapter_tag.strip()
                
        if not article:
            article_tag = soup.find(string=re.compile(r'Article\s*[0-9]+', re.IGNORECASE))
            if article_tag:
                article = article_tag.strip()
        # ----------------------------------------------------------------------------

        # 2. Extract Section Title & Heading
        # Main heading is usually .co_documentTitle or h1 element
        title_elem = soup.find(class_=re.compile(r'co_documentTitle|co_title', re.IGNORECASE))
        if not title_elem:
            title_elem = soup.find('h1')

        if title_elem:
            title_text = title_elem.get_text().strip()
            # Parse prefix like '§ 3203.' or 'Section 3203.'
            sec_match = re.search(r'(?:§|Section|Sec\.)\s*(?P<num>[0-9]+[a-zA-Z0-9\.\-\:\(\)]*)[\.\s\–\-]*(?P<heading>.*)', title_text, re.IGNORECASE)
            if sec_match:
                section_number = sec_match.group('num').strip()
                section_heading = sec_match.group('heading').strip()
            else:
                section_heading = title_text
                # Fallback to extract number from URL or title text
                num_only = re.search(r'([0-9]+[a-zA-Z0-9\.\-]*)', title_text)
                if num_only:
                    section_number = num_only.group(1)

        # 3. Construct Citation
        if title_number and section_number:
            citation = f"{title_number} CCR § {section_number}"
        else:
            # Fallback to locate a citation node in the DOM
            cit_elem = soup.find(class_=re.compile(r'co_citation', re.IGNORECASE))
            if cit_elem:
                citation = cit_elem.get_text().strip()
            else:
                citation = f"CCR Section {section_number or 'Unknown'}"

        # 4. Extract Content Markdown
        # Target the main document body container to avoid header/footer noise
        content_elem = soup.find(class_=re.compile(r'co_documentText|co_body|co_paragraph|co_content', re.IGNORECASE))
        if content_elem:
            content_markdown = self.clean_html_to_markdown(content_elem)
        
        # If Crawl4AI provided clean markdown, we can fallback to it if our custom DOM parsing yielded empty results
        if not content_markdown or len(content_markdown) < 50:
            content_markdown = crawl4ai_markdown or soup.get_text().strip()

        return {
            "title_number": title_number,
            "title_name": title_name,
            "chapter": chapter,
            "article": article,
            "section_number": section_number,
            "section_heading": section_heading,
            "citation": citation,
            "source_url": url,
            "content_markdown": content_markdown
        }

    async def crawl_section(self, crawler, url: str) -> bool:
        """
        Crawls a single Section page, extracts all fields, and writes to JSONL.
        """
        if url in self.visited_urls:
            return False
        self.visited_urls.add(url)
        
        logger.info(f"Scraping document section: {url}")
        try:
            # We target the main text container class if possible to get clean default markdown
            result = await crawler.arun(
                url=url,
                css_selector=".co_documentText,#co_docContentContainer,.co_body"
            )
            
            if not result or not result.success:
                logger.error(f"Failed to crawl document page: {url}")
                return False
                
            # Perform structured extraction
            section_data = self.parse_document_page(
                html_content=result.html, 
                url=url, 
                crawl4ai_markdown=result.markdown
            )
            
            self.write_to_jsonl(section_data)
            self.crawled_count += 1
            return True
            
        except Exception as e:
            logger.error(f"Error scraping section {url}: {e}")
            return False

    async def run(self, seed_url: str):
        """
        Initializes Crawl4AI AsyncWebCrawler and executes crawls recursively.
        """
        from crawl4ai import AsyncWebCrawler
        
        logger.info(f"Initializing Crawl4AI scraper for CCR...")
        async with AsyncWebCrawler() as crawler:
            parsed_url = urlparse(seed_url)
            
            # Determine if seed is direct document or a browse node
            if "/calregs/Document/" in seed_url or "dir.ca.gov/title8/" in seed_url:
                logger.info(f"Detected direct Document URL. Scraping single target...")
                await self.crawl_section(crawler, seed_url)
            else:
                # Browse mode
                logger.info(f"Detected Browse/TOC URL. Starting crawl traversal...")
                queue = [seed_url]
                
                while queue and self.crawled_count < self.limit:
                    current_url = queue.pop(0)
                    if current_url in self.visited_urls:
                        continue
                        
                    logger.info(f"Crawling Browse TOC Page: {current_url}")
                    self.visited_urls.add(current_url)
                    
                    try:
                        result = await crawler.arun(url=current_url)
                        if not result or not result.success:
                            continue
                            
                        # Discover links on page
                        soup = BeautifulSoup(result.html, 'html.parser')
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link['href'].strip()
                            abs_url = urljoin(current_url, href)
                            
                            # Filter: only keep calregs links from the same domain to avoid external redirections
                            if urlparse(abs_url).netloc != parsed_url.netloc:
                                continue
                                
                            # If it's a Document Section, crawl it
                            if "/calregs/Document/" in abs_url:
                                if abs_url not in self.visited_urls and abs_url not in queue:
                                    success = await self.crawl_section(crawler, abs_url)
                                    if success and self.crawled_count >= self.limit:
                                        break
                                        
                            # If it's a sub-browse node, queue it
                            elif "/calregs/Browse/" in abs_url:
                                if abs_url not in self.visited_urls and abs_url not in queue:
                                    queue.append(abs_url)
                                    
                        # Small polite delay between browse pages
                        await asyncio.sleep(1.0)
                        
                    except Exception as e:
                        logger.error(f"Error crawling browse page {current_url}: {e}")
                        
        logger.info(f"Crawl finished. Extracted and saved {self.crawled_count} sections.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="California Code of Regulations Crawl4AI Scraper")
    parser.add_argument(
        "--url", 
        type=str, 
        default="https://govt.westlaw.com/calregs/Document/I905C8C80D48411DEBC02831C6D6C108C?viewType=FullText",
        help="Target URL (Document page or Browse node)"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=5, 
        help="Max number of sections to crawl"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="output/ccr_extracted.jsonl", 
        help="JSONL output file path"
    )

    args = parser.parse_args()
    
    asyncio.run(CCRScraper(output_file=args.output, limit=args.limit).run(args.url))
