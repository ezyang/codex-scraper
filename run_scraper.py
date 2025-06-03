#!/usr/bin/env python3
"""
Script to run the Codex scraper with various options.
"""

import asyncio
import argparse
from pathlib import Path
from codex_scraper import CodexScraper

async def main():
    parser = argparse.ArgumentParser(description='Scrape Codex task data from ChatGPT')
    parser.add_argument('--test', action='store_true', help='Test with single URL only')
    parser.add_argument('--limit', type=int, help='Limit number of URLs to scrape')
    parser.add_argument('--start', type=int, default=0, help='Start index for URL list')
    parser.add_argument('--batch-size', type=int, default=5, help='Batch size for processing')
    
    args = parser.parse_args()
    
    # Read URLs from file
    urls = []
    with open('codex_urls.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    # Apply start and limit
    if args.start > 0:
        urls = urls[args.start:]
    if args.limit:
        urls = urls[:args.limit]
    
    print(f"Found {len(urls)} URLs to scrape")
    
    scraper = CodexScraper()
    
    try:
        page = await scraper.connect_to_browser()
        if not page:
            print("Failed to connect to browser")
            return
        
        if args.test:
            # Test with a single URL
            test_url = "https://chatgpt.com/codex/tasks/task_e_682bcb3a96a88323b415a5326b690b26"
            print("Testing with single URL...")
            result = await scraper.extract_task_data(test_url)
            await scraper.save_task_data(result)
            
            print("Test result:")
            print(f"Prompt found: {'Yes' if result.get('prompt') else 'No'}")
            print(f"Logs found: {'Yes' if result.get('logs') else 'No'}")
            print(f"Metadata: {result.get('metadata', {})}")
        else:
            # Scrape specified URLs
            print(f"Scraping {len(urls)} URLs...")
            results = await scraper.scrape_urls(urls, max_concurrent=args.batch_size)
            print(f"Completed scraping {len(results)} URLs")
            
            # Save summary report
            summary = {
                "total_urls": len(urls),
                "successful_scrapes": len([r for r in results if not r.get('error')]),
                "failed_scrapes": len([r for r in results if r.get('error')]),
                "start_index": args.start,
                "results": results
            }
            
            summary_file = Path("codex_tasks/scraping_summary.json")
            with open(summary_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            print(f"Summary: {summary['successful_scrapes']} successful, {summary['failed_scrapes']} failed")
            
            # Show some sample results
            if results:
                successful = [r for r in results if not r.get('error')]
                if successful:
                    sample = successful[0]
                    print(f"\nSample result from {sample['task_id']}:")
                    print(f"  Prompt: {sample.get('prompt', {}).get('text', 'N/A')[:100]}...")
                    print(f"  Logs found: {'Yes' if sample.get('logs') and sample.get('logs', {}).get('has_content') else 'No'}")
                    print(f"  Metadata: {sample.get('metadata', {})}")
        
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main())