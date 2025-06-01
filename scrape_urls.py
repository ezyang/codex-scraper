#!/usr/bin/env python3
"""
Scrape Codex task pages from ChatGPT using Playwright CDP connection.
Extracts prompt and logs content from each task page.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
from datetime import datetime
from playwright.async_api import async_playwright, Page
import logging
from concurrent.futures import ThreadPoolExecutor
import html

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CodexTaskScraper:
    """Scraper for Codex task pages."""
    
    def __init__(self, max_concurrent: int = 5, output_dir: str = "codex_tasks"):
        self.max_concurrent = max_concurrent
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    async def extract_task_data(self, page: Page, url: str) -> Dict[str, Any]:
        """Extract data from a single task page."""
        try:
            # Wait for content to load
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            # Extract task ID from URL
            task_id = url.split('/')[-1]
            
            # Extract title
            title = await page.title()
            
            # Extract prompt - look for the specific div
            prompt = ""
            try:
                prompt_element = await page.wait_for_selector(
                    'div.px-4.text-sm.break-words.whitespace-pre-wrap',
                    timeout=5000
                )
                if prompt_element:
                    prompt = await prompt_element.text_content()
            except:
                logger.warning(f"Could not find prompt for {task_id}")
            
            # Extract metadata (date, repo, stats)
            metadata = {}
            try:
                # Date
                date_elem = await page.query_selector('div:has-text("May") >> nth=0')
                if date_elem:
                    metadata['date'] = await date_elem.text_content()
                
                # Repository
                repo_elem = await page.query_selector('div:has-text("ezyang/")')
                if repo_elem:
                    metadata['repository'] = await repo_elem.text_content()
                
                # PR stats (+X -Y)
                stats_elem = await page.query_selector_all('div:has-text("+") >> has-text("-")')
                if stats_elem:
                    stats_text = await stats_elem[0].text_content()
                    metadata['pr_stats'] = stats_text
            except:
                logger.warning(f"Could not extract metadata for {task_id}")
            
            # Click on Logs tab if present
            logs_content = {}
            try:
                logs_button = await page.query_selector('button:has-text("Logs")')
                if logs_button:
                    await logs_button.click()
                    await page.wait_for_timeout(1000)  # Wait for logs to load
                    
                    # Extract logs content - get the full HTML to preserve structure
                    logs_container = await page.query_selector('div.react-scroll-to-bottom--css-siqfy-1n7m0yu')
                    if logs_container:
                        # Get inner HTML to preserve formatting
                        logs_html = await logs_container.inner_html()
                        logs_text = await logs_container.text_content()
                        
                        logs_content = {
                            'html': logs_html,
                            'text': logs_text
                        }
                    else:
                        # Try alternative selector
                        logs_elem = await page.query_selector('[role="log"]')
                        if logs_elem:
                            logs_html = await logs_elem.inner_html()
                            logs_text = await logs_elem.text_content()
                            logs_content = {
                                'html': logs_html,
                                'text': logs_text
                            }
            except Exception as e:
                logger.warning(f"Could not extract logs for {task_id}: {e}")
            
            # Extract summary/notes if on main tab
            summary_data = {}
            try:
                # Click back to main tab if we clicked logs
                diff_button = await page.query_selector('button:has-text("Diff")')
                if diff_button:
                    await diff_button.click()
                    await page.wait_for_timeout(1000)
                
                # Extract summary sections
                summary_elem = await page.query_selector('div:has(strong:has-text("Summary"))')
                if summary_elem:
                    summary_data['summary'] = await summary_elem.text_content()
                
                notes_elem = await page.query_selector('div:has(strong:has-text("Notes"))')
                if notes_elem:
                    summary_data['notes'] = await notes_elem.text_content()
                
                testing_elem = await page.query_selector('div:has(strong:has-text("Testing"))')
                if testing_elem:
                    summary_data['testing'] = await testing_elem.text_content()
            except:
                logger.warning(f"Could not extract summary for {task_id}")
            
            # Extract file changes info
            files_changed = []
            try:
                file_elems = await page.query_selector_all('button[class*="hover"]:has-text(".html"), button[class*="hover"]:has-text(".py")')
                for elem in file_elems:
                    file_text = await elem.text_content()
                    files_changed.append(file_text)
            except:
                pass
            
            return {
                'url': url,
                'task_id': task_id,
                'title': title,
                'prompt': prompt,
                'metadata': metadata,
                'summary_data': summary_data,
                'files_changed': files_changed,
                'logs': logs_content,
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error extracting data from {url}: {e}")
            return {
                'url': url,
                'task_id': url.split('/')[-1],
                'error': str(e),
                'scraped_at': datetime.now().isoformat()
            }
    
    async def scrape_task(self, browser, url: str) -> Dict[str, Any]:
        """Scrape a single task URL."""
        context = None
        page = None
        try:
            logger.info(f"Scraping {url}")
            context = await browser.new_context()
            page = await context.new_page()
            
            # Navigate to the URL
            await page.goto(url, wait_until='domcontentloaded')
            
            # Extract data
            data = await self.extract_task_data(page, url)
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return {
                'url': url,
                'task_id': url.split('/')[-1],
                'error': str(e),
                'scraped_at': datetime.now().isoformat()
            }
        finally:
            if page:
                await page.close()
            if context:
                await context.close()
    
    async def scrape_all_tasks(self, urls: List[str]):
        """Scrape all task URLs with parallel processing."""
        async with async_playwright() as p:
            # Connect to Chrome via CDP
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            
            # Process URLs in batches
            results = []
            for i in range(0, len(urls), self.max_concurrent):
                batch = urls[i:i + self.max_concurrent]
                
                # Create tasks for this batch
                tasks = [self.scrape_task(browser, url) for url in batch]
                
                # Run batch concurrently
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                
                logger.info(f"Completed {len(results)}/{len(urls)} tasks")
                
                # Small delay between batches
                if i + self.max_concurrent < len(urls):
                    await asyncio.sleep(1)
            
            await browser.close()
            
        return results
    
    def save_results(self, results: List[Dict[str, Any]]):
        """Save scraped results to files."""
        # Save individual task files
        for result in results:
            task_id = result.get('task_id', 'unknown')
            
            # Save JSON data
            json_path = self.output_dir / f"{task_id}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Save logs HTML if available
            if result.get('logs', {}).get('html'):
                html_path = self.output_dir / f"{task_id}_logs.html"
                self.save_logs_as_html(result, html_path)
        
        # Save summary file
        summary_path = self.output_dir / "summary.json"
        summary = {
            'total_tasks': len(results),
            'successful': len([r for r in results if 'error' not in r]),
            'failed': len([r for r in results if 'error' in r]),
            'tasks': [
                {
                    'task_id': r.get('task_id'),
                    'title': r.get('title'),
                    'url': r.get('url'),
                    'status': 'error' if 'error' in r else 'success',
                    'error': r.get('error', '')
                }
                for r in results
            ]
        }
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved {len(results)} results to {self.output_dir}")
    
    def save_logs_as_html(self, result: Dict[str, Any], output_path: Path):
        """Save logs as a standalone HTML file with styling."""
        logs_html = result.get('logs', {}).get('html', '')
        title = result.get('title', 'Codex Task')
        prompt = html.escape(result.get('prompt', ''))
        
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title} - Logs</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .prompt {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            white-space: pre-wrap;
        }}
        .logs {{
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 14px;
            line-height: 1.4;
        }}
        code {{
            background: #2d2d2d;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .metadata {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="metadata">
            Task ID: {result.get('task_id', '')}<br>
            URL: <a href="{result.get('url', '')}">{result.get('url', '')}</a><br>
            Scraped: {result.get('scraped_at', '')}
        </div>
        
        <h2>Prompt</h2>
        <div class="prompt">{prompt}</div>
        
        <h2>Logs</h2>
        <div class="logs">
            {logs_html}
        </div>
    </div>
</body>
</html>"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_template)


async def main():
    """Main function to scrape Codex tasks."""
    # Load URLs from file
    urls_file = "codex_urls.txt"
    if not os.path.exists(urls_file):
        logger.error(f"URLs file not found: {urls_file}")
        logger.info("Please run the extract_codex_urls.py script first")
        return
    
    with open(urls_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    logger.info(f"Found {len(urls)} URLs to scrape")
    
    # Create scraper
    scraper = CodexTaskScraper(max_concurrent=3)  # Adjust concurrency as needed
    
    # Scrape all tasks
    results = await scraper.scrape_all_tasks(urls)
    
    # Save results
    scraper.save_results(results)
    
    # Print summary
    successful = len([r for r in results if 'error' not in r])
    failed = len([r for r in results if 'error' in r])
    
    logger.info(f"\nScraping complete!")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    
    if failed > 0:
        logger.info("\nFailed tasks:")
        for r in results:
            if 'error' in r:
                logger.info(f"  {r['url']}: {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
