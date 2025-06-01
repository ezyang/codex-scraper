#!/usr/bin/env python3
"""
Scrape Codex task pages from ChatGPT using Playwright CDP connection.
Extracts prompt and logs content from each task page with flexible selectors.
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
import html

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CodexTaskScraper:
    """Scraper for Codex task pages with flexible selectors."""
    
    def __init__(self, max_concurrent: int = 5, output_dir: str = "codex_tasks"):
        self.max_concurrent = max_concurrent
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    async def extract_task_data(self, page: Page, url: str) -> Dict[str, Any]:
        """Extract data from a single task page with flexible selectors."""
        try:
            # Wait for content to load
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            # Extract task ID from URL
            task_id = url.split('/')[-1]
            
            # Extract title
            title = await page.title()
            
            # Extract prompt - try multiple selectors
            prompt = ""
            prompt_selectors = [
                'div.px-4.text-sm.break-words.whitespace-pre-wrap',
                'div[class*="whitespace-pre-wrap"]',
                'div[class*="break-words"][class*="text-sm"]',
                # Look for first div that contains substantial text
                'div:has-text("The") >> nth=0',
                'div:has-text("Fix") >> nth=0',
                'div:has-text("Add") >> nth=0',
                'div:has-text("Update") >> nth=0',
                'div:has-text("Implement") >> nth=0',
            ]
            
            for selector in prompt_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = await elem.text_content()
                        # Check if it's likely a prompt (not too short, not navigation)
                        if text and len(text) > 20 and not any(nav in text.lower() for nav in ['settings', 'environments', 'docs', 'profile']):
                            prompt = text.strip()
                            break
                except:
                    continue
            
            if not prompt:
                # Try to find prompt by structure - it's often the first substantial text block
                try:
                    all_divs = await page.query_selector_all('div')
                    for div in all_divs[:20]:  # Check first 20 divs
                        text = await div.text_content()
                        if text and len(text) > 50 and len(text) < 1000:
                            # Likely a prompt if it's a good length and not code
                            if not text.startswith('⠙') and not 'KiB' in text:
                                prompt = text.strip()
                                break
                except:
                    pass
            
            # Extract metadata with flexible selectors
            metadata = {}
            try:
                # Date - look for date patterns
                date_patterns = [
                    'div:has-text("May") >> nth=0',
                    'div:has-text("Jun") >> nth=0',
                    'div:has-text("Apr") >> nth=0',
                    'div:has-text("Mar") >> nth=0',
                    '*:has-text("ago") >> nth=0',
                    '[class*="text-gray"]:has-text("202")',
                ]
                
                for pattern in date_patterns:
                    elem = await page.query_selector(pattern)
                    if elem:
                        text = await elem.text_content()
                        if text and len(text) < 50:
                            metadata['date'] = text.strip()
                            break
                
                # Repository - look for GitHub patterns
                repo_patterns = [
                    'div:has-text("/"):has-text("ezyang")',
                    'a[href*="github.com"]',
                    '*:has-text("ezyang/")',
                    'div:has-text("/") >> nth=1',
                ]
                
                for pattern in repo_patterns:
                    elem = await page.query_selector(pattern)
                    if elem:
                        text = await elem.text_content()
                        if '/' in text and len(text) < 100:
                            metadata['repository'] = text.strip()
                            break
                
                # PR stats - look for +/- patterns
                stats_patterns = [
                    'div:has-text("+"):has-text("-")',
                    '*:has-text("+"):has-text("-")',
                    '[class*="text-green"]:has-text("+")',
                ]
                
                stats = []
                for pattern in stats_patterns:
                    elems = await page.query_selector_all(pattern)
                    for elem in elems[:3]:  # Check first 3 matches
                        text = await elem.text_content()
                        if text and '+' in text and '-' in text and len(text) < 30:
                            stats.append(text.strip())
                
                if stats:
                    metadata['pr_stats'] = stats[0]
                
                # Status (Merged, Failed, etc)
                status_patterns = [
                    'link:has-text("Merged")',
                    'link:has-text("Closed")',
                    'div:has-text("Failed")',
                    'div:has-text("Merged")',
                    '*[class*="badge"]:has-text("Merged")',
                    '*[class*="badge"]:has-text("Failed")',
                ]
                
                for pattern in status_patterns:
                    elem = await page.query_selector(pattern)
                    if elem:
                        text = await elem.text_content()
                        if text and len(text) < 20:
                            metadata['status'] = text.strip()
                            break
                
            except Exception as e:
                logger.debug(f"Metadata extraction error: {e}")
            
            # Extract logs - try multiple approaches
            logs_content = {}
            try:
                # Look for tabs first
                tabs_found = False
                for tab_text in ['Logs', 'Log', 'Output', 'Console']:
                    tab_button = await page.query_selector(f'button:has-text("{tab_text}")')
                    if tab_button:
                        await tab_button.click()
                        await page.wait_for_timeout(1500)
                        tabs_found = True
                        break
                
                # Try multiple selectors for logs container
                logs_selectors = [
                    'div.react-scroll-to-bottom--css-siqfy-1n7m0yu',
                    'div[class*="scroll"]',
                    '[role="log"]',
                    'pre',  # Sometimes logs are in pre tags
                    'code',  # Or code blocks
                    'div:has(code):has-text("Preparing packages")',
                    'div:has-text("Building"):has-text("KiB")',
                ]
                
                for selector in logs_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            html_content = await elem.inner_html()
                            text_content = await elem.text_content()
                            
                            # Check if it looks like logs
                            if text_content and ('⠙' in text_content or 'KiB' in text_content or 
                                               'Building' in text_content or 'error' in text_content.lower() or
                                               'warning' in text_content.lower() or len(text_content) > 200):
                                logs_content = {
                                    'html': html_content,
                                    'text': text_content
                                }
                                break
                    except:
                        continue
                
                # If no logs found and we found tabs, try going back to Diff tab
                if not logs_content and tabs_found:
                    diff_button = await page.query_selector('button:has-text("Diff")')
                    if diff_button:
                        await diff_button.click()
                        await page.wait_for_timeout(1000)
                
            except Exception as e:
                logger.debug(f"Logs extraction error: {e}")
            
            # Extract summary/notes - flexible approach
            summary_data = {}
            try:
                # Look for common summary patterns
                summary_patterns = {
                    'summary': ['strong:has-text("Summary")', 'h2:has-text("Summary")', 'h3:has-text("Summary")'],
                    'notes': ['strong:has-text("Notes")', 'h2:has-text("Notes")', 'h3:has-text("Notes")'],
                    'testing': ['strong:has-text("Testing")', 'h2:has-text("Testing")', 'h3:has-text("Testing")'],
                    'description': ['strong:has-text("Description")', 'h2:has-text("Description")'],
                }
                
                for key, patterns in summary_patterns.items():
                    for pattern in patterns:
                        elem = await page.query_selector(f'*:has({pattern})')
                        if elem:
                            text = await elem.text_content()
                            if text:
                                summary_data[key] = text.strip()
                                break
                
            except Exception as e:
                logger.debug(f"Summary extraction error: {e}")
            
            # Extract file changes - flexible approach
            files_changed = []
            try:
                # Look for file patterns
                file_patterns = [
                    'button:has-text(".py")',
                    'button:has-text(".html")',
                    'button:has-text(".js")',
                    'button:has-text(".css")',
                    'button:has-text(".json")',
                    'div:has-text("/"):has-text(".")',
                    'a[href*=".py"]',
                    'a[href*=".html"]',
                ]
                
                found_files = set()
                for pattern in file_patterns:
                    elems = await page.query_selector_all(pattern)
                    for elem in elems[:10]:  # Limit to prevent too many matches
                        text = await elem.text_content()
                        if text and '.' in text and len(text) < 200:
                            # Clean up the text
                            cleaned = text.strip()
                            if cleaned not in found_files:
                                found_files.add(cleaned)
                                files_changed.append(cleaned)
                
            except Exception as e:
                logger.debug(f"Files extraction error: {e}")
            
            # Extract any PR links
            pr_links = []
            try:
                pr_patterns = [
                    'a[href*="github.com"][href*="pull"]',
                    'link:has-text("View Pull Request")',
                    'a:has-text("View on GitHub")',
                ]
                
                for pattern in pr_patterns:
                    elems = await page.query_selector_all(pattern)
                    for elem in elems:
                        href = await elem.get_attribute('href')
                        if href:
                            pr_links.append(href)
                
            except:
                pass
            
            # Take a screenshot for debugging
            screenshot_path = self.output_dir / f"{task_id}_screenshot.png"
            try:
                await page.screenshot(path=str(screenshot_path))
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
                'pr_links': pr_links,
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
            
            # Create context with specific settings to avoid blocking
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Set extra headers
            await page.set_extra_http_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            
            # Navigate to the URL with retries
            max_retries = 3
            for retry in range(max_retries):
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    break
                except Exception as e:
                    if retry < max_retries - 1:
                        logger.warning(f"Retry {retry + 1} for {url}")
                        await asyncio.sleep(2)
                    else:
                        raise e
            
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
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Handle results
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Task failed with exception: {result}")
                        results.append({
                            'error': str(result),
                            'scraped_at': datetime.now().isoformat()
                        })
                    else:
                        results.append(result)
                
                logger.info(f"Completed {len(results)}/{len(urls)} tasks")
                
                # Small delay between batches
                if i + self.max_concurrent < len(urls):
                    await asyncio.sleep(2)
            
            await browser.close()
            
        return results
    
    def save_results(self, results: List[Dict[str, Any]]):
        """Save scraped results to files."""
        # Save individual task files
        for result in results:
            task_id = result.get('task_id', 'unknown')
            if task_id == 'unknown':
                # Generate ID from URL or timestamp
                task_id = f"task_{hash(result.get('url', str(datetime.now())))}"
            
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
            'with_prompt': len([r for r in results if r.get('prompt')]),
            'with_logs': len([r for r in results if r.get('logs')]),
            'tasks': [
                {
                    'task_id': r.get('task_id'),
                    'title': r.get('title'),
                    'url': r.get('url'),
                    'status': 'error' if 'error' in r else 'success',
                    'has_prompt': bool(r.get('prompt')),
                    'has_logs': bool(r.get('logs')),
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
        <div class="prompt">{prompt if prompt else 'No prompt found'}</div>
        
        <h2>Logs</h2>
        <div class="logs">
            {logs_html if logs_html else 'No logs found'}
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
    
    # Create scraper with lower concurrency to avoid rate limiting
    scraper = CodexTaskScraper(max_concurrent=2)
    
    # Scrape all tasks
    results = await scraper.scrape_all_tasks(urls)
    
    # Save results
    scraper.save_results(results)
    
    # Print summary
    successful = len([r for r in results if 'error' not in r])
    failed = len([r for r in results if 'error' in r])
    with_prompt = len([r for r in results if r.get('prompt')])
    with_logs = len([r for r in results if r.get('logs')])
    
    logger.info(f"\nScraping complete!")
    logger.info(f"Total URLs: {len(urls)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"With prompt: {with_prompt}")
    logger.info(f"With logs: {with_logs}")
    
    if failed > 0:
        logger.info(f"\nFailed tasks: {failed}")
        for r in results:
            if 'error' in r:
                logger.debug(f"  {r.get('url', 'unknown')}: {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
