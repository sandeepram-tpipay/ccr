#!/usr/bin/env python
import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Set, Tuple, Dict
from datetime import datetime, timezone

# Resolve python module lookup in root path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from compliance_engine.config import settings
from compliance_engine.logger import configure_logging
from compliance_engine.core.crawler_service import RegScraper
from compliance_engine.core.embedding_service import FastEmbedService
from compliance_engine.core.qdrant_service import VectorStoreManager

# Set up logging configuration
configure_logging(settings.log_level)
logger = logging.getLogger("load_data")

class IndexingPipeline:
    """
    Coordinates recursive crawler discovery, document parsing,
    local embedding computations, and Qdrant ingestion.
    """
    def __init__(self, backup_file: str, max_limit: int = 50):
        self.scraper = RegScraper()
        self.embedder = FastEmbedService()
        self.db = VectorStoreManager(embed_service=self.embedder)
        
        self.backup_file = backup_file
        self.max_limit = max_limit
        self.url_discovery_file = "output/discovered_urls.json"
        self.checkpoint_tracker_file = "output/crawl_checkpoints.json"
        self.checkpoints: Dict[str, dict] = {}
        
        # Ensure target folder structures exist
        target_dir = os.path.dirname(backup_file)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
            
        self.recover_checkpoints()

    def recover_checkpoints(self):
        """
        Restores indexing state tracker from local checkpoints json.
        """
        if os.path.exists(self.checkpoint_tracker_file):
            try:
                with open(self.checkpoint_tracker_file, "r", encoding="utf-8") as f:
                    self.checkpoints = json.load(f)
                logger.info(f"Restored {len(self.checkpoints)} index checkpoints.")
            except Exception as err:
                logger.error(f"Failed loading checkpoint status: {err}")
                self.checkpoints = {}
        else:
            self.checkpoints = {}

    def commit_checkpoint(self):
        """
        Saves indexing state tracker to disk.
        """
        try:
            with open(self.checkpoint_tracker_file, "w", encoding="utf-8") as f:
                json.dump(self.checkpoints, f, indent=2)
        except Exception as err:
            logger.error(f"Failed persisting checkpoint: {err}")

    def append_backup_store(self, blocks: list):
        """
        Logs processed RegulationBlocks inside JSONL file backup for audits.
        """
        logger.info(f"Backing up {len(blocks)} blocks into JSONL database backup: {self.backup_file}")
        with open(self.backup_file, "a", encoding="utf-8") as f:
            for block in blocks:
                f.write(json.dumps(block.model_dump()) + "\n")

    async def ingest_single_url(self, target_url: str) -> Tuple[list, str]:
        """
        Orchestrates single-page flow: fetch page, extract blocks, vectorize content,
        write to Qdrant, write to backup JSONL.
        """
        logger.info(f"Starting ingestion process: {target_url}")
        
        # 1. Fetch
        page_data = await self.scraper.fetch_page(target_url)
        html_code = page_data.get("html", "")
        markdown_code = page_data.get("markdown", "")
        
        if not html_code and not markdown_code:
            logger.warning(f"Fetch failed: No data retrieved for URL: {target_url}")
            return [], ""
            
        # 2. Parse
        blocks = self.scraper.parse_regulations(page_data, target_url)
        if not blocks:
            logger.warning(f"Extraction yield empty for URL: {target_url}")
            return [], html_code or markdown_code
            
        # 3. Vectorize
        logger.info(f"Generating FastEmbed embeddings for {len(blocks)} blocks.")
        texts = [b.content_markdown for b in blocks]
        vectors = self.embedder.vectorize_list(texts)
        
        # 4. Ingest into Qdrant
        logger.info(f"Upserting {len(blocks)} blocks to vector collection '{self.db.collection_name}'")
        await self.db.index_blocks(blocks, vectors)
        
        # 5. Append to local backup
        self.append_backup_store(blocks)
        
        return blocks, html_code or markdown_code

    async def execute_pipeline(self, seed_url: str, crawl_depth: int = 1):
        """
        Starts the two-stage crawl discovery and DB loader loop.
        """
        # Ensure database is active
        logger.info("Pinging vector store connectivity...")
        if not self.db.check_connection():
            logger.critical("Vector store offline. Terminating data pipeline run.")
            return

        self.db.provision_collection()

        # ==========================================
        # STAGE 1: SCAN & LINK DISCOVERY
        # ==========================================
        discovered_list = []
        is_restored = False
        
        if os.path.exists(self.url_discovery_file):
            try:
                with open(self.url_discovery_file, "r", encoding="utf-8") as f:
                    discovered_list = json.load(f)
                logger.info(f"Restored {len(discovered_list)} discovered target URLs from {self.url_discovery_file}")
                is_restored = True
            except Exception as err:
                logger.error(f"Unable to read discovered URLs catalog: {err}")
                discovered_list = []

        # If discovery list is empty or doesn't have our seed_url, scan links
        if not is_restored or not discovered_list or seed_url not in discovered_list:
            logger.info(f"Stage 1: Beginning URL scanner discovery from seed: {seed_url} (depth={crawl_depth})")
            
            queue: List[Tuple[str, int]] = [(seed_url, 0)]
            visited_urls: Set[str] = set()
            sections_catalog: Set[str] = set(discovered_list)
            
            while queue and len(visited_urls) < self.max_limit:
                curr_url, depth = queue.pop(0)
                if curr_url in visited_urls:
                    continue
                visited_urls.add(curr_url)
                
                logger.info(f"Scanning target node (depth {depth}): {curr_url}")
                try:
                    # If direct document, catalogue it
                    if "/calregs/Document/" in curr_url or "dir.ca.gov/title8/" in curr_url:
                        sections_catalog.add(curr_url)
                        
                    raw_data = await self.scraper.fetch_page(curr_url)
                    text_content = raw_data.get("html", "") or raw_data.get("markdown", "")
                    
                    if depth < crawl_depth and text_content:
                        discovered_links = self.scraper.extract_links(text_content, curr_url)
                        for url in discovered_links:
                            if url not in visited_urls and url not in [item[0] for item in queue]:
                                queue.append((url, depth + 1))
                                
                except Exception as err:
                    logger.error(f"Error executing discovery on URL {curr_url}: {err}")
            
            # Seed fallback check
            if not sections_catalog and ("/calregs/Document/" in seed_url or "dir.ca.gov/title8/" in seed_url):
                sections_catalog.add(seed_url)

            discovered_list = sorted(list(sections_catalog))
            with open(self.url_discovery_file, "w", encoding="utf-8") as f:
                json.dump(discovered_list, f, indent=2)
            logger.info(f"Stage 1 complete: Merged URL discovery list. Catalogued {len(discovered_list)} targets.")
        else:
            logger.info("Seed URL already exists in discovery manifest. Skipping Stage 1 link scan.")

        # ==========================================
        # STAGE 2: PARSE, VECTORIZE AND INDEX
        # ==========================================
        logger.info("Stage 2: Processing URLs into Vector DB collections...")
        pages_processed = 0
        total_blocks_loaded = 0
        
        for idx, url in enumerate(discovered_list):
            if idx >= self.max_limit:
                logger.warning(f"Exceeded max iteration limit configuration of {self.max_limit} URLs. Stopping.")
                break
                
            # Skip if checkpoint is already done
            url_tracker = self.checkpoints.get(url, {})
            if url_tracker.get("status") == "success":
                logger.info(f"URL already indexed (checkpoint hit): {url}")
                total_blocks_loaded += url_tracker.get("blocks_count", 0)
                continue

            try:
                blocks, _ = await self.ingest_single_url(url)
                blocks_count = len(blocks)
                total_blocks_loaded += blocks_count
                pages_processed += 1
                
                self.checkpoints[url] = {
                    "status": "success",
                    "error_log": None,
                    "blocks_count": blocks_count,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            except Exception as err:
                logger.error(f"Ingestion aborted for target {url}: {err}", exc_info=True)
                self.checkpoints[url] = {
                    "status": "failed",
                    "error_log": str(err),
                    "blocks_count": 0,
                    "retry_count": url_tracker.get("retry_count", 0) + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            # Commit tracker changes to prevent data loss on failures
            self.commit_checkpoint()
            # Polite wait delay
            await asyncio.sleep(1.0)

        logger.info("=" * 60)
        logger.info("Ingestion Execution Wrap Up Summary:")
        logger.info(f"  Discovered Target Manifest Size : {len(discovered_list)}")
        logger.info(f"  Pages Loaded This Run           : {pages_processed}")
        logger.info(f"  Total Active Blocks Indexed     : {total_blocks_loaded}")
        logger.info(f"  Checkpoints Database File       : {self.checkpoint_tracker_file}")
        logger.info(f"  Audit File Location             : {self.backup_file}")
        logger.info("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCR Ingestion and Indexing Pipeline CLI")
    parser.add_argument(
        "--url", 
        type=str, 
        required=True, 
        help="Seed URL of the regulation document page or chapter index"
    )
    parser.add_argument(
        "--depth", 
        type=int, 
        default=1, 
        help="Depth range for page discovery indexing (default: 1)"
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
        help="File path to save the indexed section logs (default: output/crawled_sections.jsonl)"
    )

    args = parser.parse_args()

    asyncio.run(
        IndexingPipeline(backup_file=args.output, max_limit=args.limit).execute_pipeline(
            seed_url=args.url,
            crawl_depth=args.depth
        )
    )
