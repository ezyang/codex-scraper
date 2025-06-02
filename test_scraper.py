#!/usr/bin/env python3
"""
Test script to verify the scraper works with a few URLs.
"""

import asyncio
import logging
from scrape_urls_v2 import CodexTaskScraper

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test URLs - replace these with actual URLs from your codex_urls.txt
TEST_URLS = [
    # Add 1-2 actual URLs here for testing
    # "https://chatgpt.com/codex/tasks/task_e_XXXXXXXX",
    # "https://chatgpt.com/codex/tasks/task_e_YYYYYYYY",
]

async def test_scraper():
    """Test the scraper with a few URLs."""
    
    if not TEST_URLS:
        # Try to load URLs from file
        try:
            with open("codex_urls.txt", 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
                test_urls = urls[:2]  # Take first 2 URLs
        except FileNotFoundError:
            logger.error("No test URLs provided and codex_urls.txt not found")
            logger.info("Please add some test URLs to the TEST_URLS list in this script")
            return
    else:
        test_urls = TEST_URLS
    
    logger.info(f"Testing scraper with {len(test_urls)} URLs")
    
    # Create scraper
    scraper = CodexTaskScraper(max_concurrent=1, output_dir="test_output")
    
    # Scrape test URLs
    results = await scraper.scrape_all_tasks(test_urls)
    
    # Save results
    scraper.save_results(results)
    
    # Print summary
    for result in results:
        logger.info(f"\nTask: {result.get('task_id', 'unknown')}")
        logger.info(f"URL: {result.get('url', 'unknown')}")
        logger.info(f"Title: {result.get('title', 'unknown')}")
        logger.info(f"Has prompt: {bool(result.get('prompt'))}")
        logger.info(f"Prompt length: {len(result.get('prompt', ''))}")
        logger.info(f"Has logs: {bool(result.get('logs'))}")
        if result.get('logs'):
            logger.info(f"Logs length: {len(result.get('logs', {}).get('text', ''))}")
        if 'error' in result:
            logger.error(f"Error: {result['error']}")
    
    logger.info(f"\nTest completed. Results saved to test_output/")

if __name__ == "__main__":
    asyncio.run(test_scraper())