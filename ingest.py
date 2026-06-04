#!/usr/bin/env python
import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Set, Tuple, Dict
from datetime import datetime, timezone

# Add current directory to python path to ensure app imports resolve when run directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.logging_config import setup_logging
from app.services.crawler import CCRWebCrawler
from app.services.embedder import LocalEmbedder
from app.services.qdrant import QdrantService

# Configure logging
setup_logging()
logger = logging.getLogger("ingest")

class IngestionPipeline:
    def __init__(self, output_file: str, max_pages_limit: int = 50):
        self.crawler = CCRWebCrawler()
        self.embedder = LocalEmbedder()
        self.qdrant = QdrantService(embedder=self.embedder)
        self.output_file = output_file
        self.max_pages_limit = max_pages_limit
        self.visited_urls: Set[str] = set()

        self.discovered_file = "output/discovered_urls.json"
        self.checkpoints_file = "output/crawl_checkpoints.json"
        self.checkpoints: Dict[str, dict] = {}

        # Ensure output directory exists
        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
        self.load_checkpoints()

    def load_checkpoints(self):
        """
        Loads crawl checkpoints from the JSON checkpoints file.
        """
        if os.path.exists(self.checkpoints_file):
            try:
                with open(self.checkpoints_file, "r", encoding="utf-8") as f:
                    self.checkpoints = json.load(f)
                logger.info(f"Loaded {len(self.checkpoints)} checkpoints from {self.checkpoints_file}")
            except Exception as e:
                logger.error(f"Error loading checkpoints file: {e}")
                self.checkpoints = {}
        else:
            self.checkpoints = {}

    def save_checkpoints(self):
        """
        Saves current checkpoints dictionary to JSON checkpoints file.
        """
        try:
            with open(self.checkpoints_file, "w", encoding="utf-8") as f:
                json.dump(self.checkpoints, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoints file: {e}")

    def write_to_jsonl(self, sections: list):
        """
        Appends the extracted sections into a local JSONL output file for auditing.
        """
        logger.info(f"Writing {len(sections)} sections to JSONL file: {self.output_file}")
        with open(self.output_file, "a", encoding="utf-8") as f:
            for section in sections:
                data = section.model_dump()
                f.write(json.dumps(data) + "\n")

    async def ingest_url(self, url: str) -> Tuple[list, str]:
        """
        Processes a single URL: crawls content, extracts sections, generates embeddings,
        stores in Qdrant, and appends to local JSONL backup.
        """
        logger.info(f"Processing URL: {url}")
        
        # 1. Crawl URL
        raw_content = await self.crawler.crawl_url(url)
        html_data = raw_content.get("html", "")
        markdown_data = raw_content.get("markdown", "")
        
        if not html_data and not markdown_data:
            logger.warning(f"No content retrieved for URL: {url}")
            return [], ""

        # 2. Extract sections
        sections = self.crawler.extract_sections(raw_content, url)
        if not sections:
            logger.warning(f"No regulation sections extracted from URL: {url}")
            return [], html_data or markdown_data

        # 3. Generate embeddings
        logger.info(f"Generating embeddings for {len(sections)} sections from {url}")
        texts_to_embed = [sec.content for sec in sections]
        embeddings = self.embedder.embed_texts(texts_to_embed)

        # 4. Store in Qdrant
        logger.info(f"Indexing {len(sections)} sections in Qdrant collection '{self.qdrant.collection_name}'")
        await self.qdrant.upsert_sections(sections, embeddings)

        # 5. Append results to JSONL
        self.write_to_jsonl(sections)

        return sections, html_data or markdown_data

    async def run(self, seed_url: str, max_depth: int = 1):
        """
        Runs the crawling and ingestion loop starting from a seed URL,
        performing URL discovery and deduplication.
        """
        # Verify Qdrant status before starting
        logger.info("Verifying Qdrant DB health...")
        if not self.qdrant.is_healthy():
            logger.error("Cannot proceed: Qdrant service is unhealthy or offline.")
            return

        # Auto create collection if missing
        self.qdrant.ensure_collection()

        # ==========================================
        # STAGE 1: URL DISCOVERY
        # ==========================================
        discovered_urls_list = []
        loaded_from_file = False
        if os.path.exists(self.discovered_file):
            try:
                with open(self.discovered_file, "r", encoding="utf-8") as f:
                    discovered_urls_list = json.load(f)
                logger.info(f"Loaded {len(discovered_urls_list)} discovered URLs from {self.discovered_file}")
                loaded_from_file = True
            except Exception as e:
                logger.error(f"Error loading discovered URLs file: {e}")
                discovered_urls_list = []

        # Run discovery if file didn't exist, was empty, or if seed_url is not in the loaded list
        if not loaded_from_file or not discovered_urls_list or seed_url not in discovered_urls_list:
            logger.info(f"Starting Stage 1: URL Discovery from seed: {seed_url} (Max Depth: {max_depth})")
            
            queue: List[Tuple[str, int]] = [(seed_url, 0)]
            visited_discovery: Set[str] = set()
            discovered_sections_set: Set[str] = set(discovered_urls_list) # Keep already discovered URLs
            
            while queue and len(visited_discovery) < self.max_pages_limit:
                current_url, depth = queue.pop(0)
                if current_url in visited_discovery:
                    continue
                visited_discovery.add(current_url)
                
                logger.info(f"Scanning for links on (depth {depth}): {current_url}")
                try:
                    # Direct section validation
                    if "/calregs/Document/" in current_url or "dir.ca.gov/title8/" in current_url:
                        discovered_sections_set.add(current_url)
                        
                    raw_content = await self.crawler.crawl_url(current_url)
                    html_data = raw_content.get("html", "")
                    markdown_data = raw_content.get("markdown", "")
                    text_to_scan = html_data or markdown_data
                    
                    if depth < max_depth and text_to_scan:
                        discovered_links = self.crawler.discover_urls(text_to_scan, current_url)
                        for d_url in discovered_links:
                            if d_url not in visited_discovery and d_url not in [q[0] for q in queue]:
                                queue.append((d_url, depth + 1))
                                
                except Exception as e:
                    logger.error(f"Error during link discovery on URL {current_url}: {e}")
                    
            # If seed was a direct document and no other URLs were discovered, add it
            if not discovered_sections_set and ("/calregs/Document/" in seed_url or "dir.ca.gov/title8/" in seed_url):
                discovered_sections_set.add(seed_url)

            discovered_urls_list = sorted(list(discovered_sections_set))
            with open(self.discovered_file, "w", encoding="utf-8") as f:
                json.dump(discovered_urls_list, f, indent=2)
            logger.info(f"Stage 1 complete: Discovered and merged URLs. Saved {len(discovered_urls_list)} URLs to {self.discovered_file}")
        else:
            logger.info(f"Seed URL {seed_url} already exists in discovered URLs list. Skipping discovery stage.")


        # ==========================================
        # STAGE 2: EXTRACTION AND INGESTION
        # ==========================================
        logger.info("Starting Stage 2: Section Extraction and Database Ingestion...")
        total_sections_count = 0
        total_pages_crawled = 0
        
        for idx, url in enumerate(discovered_urls_list):
            if idx >= self.max_pages_limit:
                logger.warning(f"Reached ingestion limit of {self.max_pages_limit} pages. Stopping.")
                break
                
            # Persistent Checkpoint Check
            checkpoint = self.checkpoints.get(url, {})
            if checkpoint.get("status") == "completed":
                logger.info(f"Skipping already ingested URL (checkpoint completed): {url}")
                total_sections_count += checkpoint.get("sections_count", 0)
                continue

            try:
                sections, raw_content = await self.ingest_url(url)
                sections_count = len(sections)
                total_sections_count += sections_count
                total_pages_crawled += 1
                
                # Update checkpoint as completed
                self.checkpoints[url] = {
                    "status": "completed",
                    "error": None,
                    "sections_count": sections_count,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}", exc_info=True)
                # Update checkpoint as failed
                self.checkpoints[url] = {
                    "status": "failed",
                    "error": str(e),
                    "sections_count": 0,
                    "retries": checkpoint.get("retries", 0) + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            # Save checkpoint state after each page to prevent progress loss
            self.save_checkpoints()
            # Polite delay between crawler downloads
            await asyncio.sleep(1.0)

        logger.info("=" * 60)
        logger.info("Ingestion Pipeline Run Summary:")
        logger.info(f"  Total Discovered Sections: {len(discovered_urls_list)}")
        logger.info(f"  Pages Crawled This Run: {total_pages_crawled}")
        logger.info(f"  Total Sections Indexed in Qdrant: {total_sections_count}")
        logger.info(f"  Checkpoints Saved: {self.checkpoints_file}")
        logger.info(f"  Structured Output Backup: {self.output_file}")
        logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCR Compliance Agent Ingestion Pipeline CLI")
    parser.add_argument(
        "--url", 
        type=str, 
        required=True, 
        help="Seed URL of the California Code of Regulations page to start crawling"
    )
    parser.add_argument(
        "--max-depth", 
        type=int, 
        default=1, 
        help="Maximum depth to crawl from seed URL (default: 1)"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=50, 
        help="Limit of max pages to crawl (default: 50)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="output/crawled_sections.jsonl", 
        help="File path to save the crawled sections as JSONL (default: output/crawled_sections.jsonl)"
    )

    args = parser.parse_args()

    asyncio.run(
        IngestionPipeline(output_file=args.output, max_pages_limit=args.limit).run(
            seed_url=args.url, 
            max_depth=args.max_depth
        )
    )
