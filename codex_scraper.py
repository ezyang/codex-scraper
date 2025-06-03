#!/usr/bin/env python3
"""
Complete Codex task scraper that extracts prompt and logs data from ChatGPT.
Connects to existing Chrome browser instance via CDP.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser

class CodexScraper:
    def __init__(self, cdp_url: str = "http://localhost:9222"):
        self.cdp_url = cdp_url
        self.output_dir = Path("codex_tasks")
        self.output_dir.mkdir(exist_ok=True)
        
    async def connect_to_browser(self):
        """Connect to existing Chrome browser instance via CDP."""
        self.playwright = await async_playwright().start()
        
        # Connect to existing browser instance
        self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)
        
        # Get the default context and page
        contexts = self.browser.contexts
        if not contexts:
            print("No browser contexts found. Make sure Chrome is running with --remote-debugging-port=9222")
            return None
        
        context = contexts[0]
        pages = context.pages
        
        if not pages:
            # Create new page if none exist
            self.page = await context.new_page()
        else:
            self.page = pages[0]
        
        return self.page

    async def extract_task_data(self, url: str) -> Dict:
        """Extract all task data from a Codex task URL."""
        print(f"Scraping: {url}")
        
        task_id = url.split('/')[-1]
        task_data = {
            "url": url,
            "task_id": task_id,
            "prompt": None,
            "logs": None,
            "metadata": {},
            "error": None
        }
        
        try:
            # Navigate to the page
            await self.page.goto(url, wait_until='load', timeout=60000)
            await self.page.wait_for_timeout(3000)
            
            # Extract page title and metadata
            title = await self.page.title()
            task_data["metadata"]["title"] = title
            
            # Extract the prompt
            task_data["prompt"] = await self.extract_prompt()
            
            # Extract logs
            task_data["logs"] = await self.extract_logs()
            
            # Extract additional metadata
            task_data["metadata"].update(await self.extract_metadata())
            
        except Exception as e:
            print(f"Error extracting data from {url}: {e}")
            task_data["error"] = str(e)
            
        return task_data
    
    async def extract_prompt(self) -> Optional[Dict]:
        """Extract the main prompt text from the page."""
        try:
            # Look for the prompt element
            prompt_element = await self.page.query_selector('div.px-4.text-sm.break-words.whitespace-pre-wrap')
            
            if prompt_element:
                text = await prompt_element.inner_text()
                html = await prompt_element.inner_html()
                
                return {
                    "text": text,
                    "html": html
                }
            else:
                print("Prompt element not found")
                return None
                
        except Exception as e:
            print(f"Error extracting prompt: {e}")
            return None
    
    async def extract_logs(self) -> Optional[Dict]:
        """Extract logs content by clicking on the Logs tab."""
        try:
            # Find all buttons and look for the Logs tab
            all_buttons = await self.page.query_selector_all('button')
            logs_tab = None
            
            for button in all_buttons:
                try:
                    text = await button.inner_text()
                    if text.strip() == "Logs":
                        logs_tab = button
                        break
                except:
                    continue
            
            if not logs_tab:
                print("Logs tab not found")
                return None
            
            # Click on the Logs tab
            await logs_tab.click()
            await self.page.wait_for_timeout(2000)
            
            # Look for log content in various possible containers
            log_selectors = [
                'div.react-scroll-to-bottom--css-siqfy-1n7m0yu',
                '[class*="react-scroll-to-bottom"]',
                'pre',
                'code',
                'div[class*="overflow-auto"]'
            ]
            
            logs_data = {
                "found_selector": None,
                "has_content": False
            }
            
            for selector in log_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        text = await element.inner_text()
                        if len(text.strip()) > 50:  # Only consider elements with substantial content
                            html = await element.inner_html()
                            logs_data = {
                                "found_selector": selector,
                                "has_content": True,
                                "_html": html  # Store HTML temporarily for saving
                            }
                            print(f"Found logs content using selector: {selector}")
                            return logs_data
                except Exception as e:
                    continue
            
            # If no specific log container found, try to get all text from the main content area
            try:
                # Look for the main content area after clicking logs
                main_content = await self.page.query_selector('div[class*="flex-1"]')
                if main_content:
                    text = await main_content.inner_text()
                    html = await main_content.inner_html()
                    if "ruff" in text.lower() or "pytest" in text.lower() or "error" in text.lower():
                        logs_data = {
                            "found_selector": "main_content_fallback",
                            "has_content": True,
                            "_html": html  # Store HTML temporarily for saving
                        }
                        print("Found logs content using main content fallback")
                        return logs_data
            except:
                pass
            
            print("No logs content found")
            return None
            
        except Exception as e:
            print(f"Error extracting logs: {e}")
            return None
    
    async def extract_metadata(self) -> Dict:
        """Extract additional metadata from the page."""
        metadata = {}
        
        try:
            # Look for GitHub PR URL in "View Pull Request" button
            pr_link_selectors = [
                'a:has-text("View Pull Request")',
                'a[href*="github.com"]',
                'a[href*="/pull/"]'
            ]
            
            for selector in pr_link_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        href = await element.get_attribute('href')
                        if href and 'github.com' in href and '/pull/' in href:
                            metadata["github_pr_url"] = href
                            print(f"Found GitHub PR URL: {href}")
                            break
                except:
                    continue
            
            # Look for repository information
            repo_elements = await self.page.query_selector_all('span:has-text("/")')
            for element in repo_elements:
                text = await element.inner_text()
                if "/" in text and len(text.split("/")) == 2:
                    metadata["repository"] = text
                    break
            
            # Look for dates
            date_elements = await self.page.query_selector_all('span[class*="text-token-text-secondary"]')
            for element in date_elements:
                text = await element.inner_text()
                if any(month in text for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                                                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                    metadata["date"] = text
                    break
            
            # Look for PR stats (+/- lines)
            stat_elements = await self.page.query_selector_all('span[class*="text-green-500"], span[class*="text-red-500"]')
            additions = deletions = 0
            for element in stat_elements:
                text = await element.inner_text()
                if text.startswith("+"):
                    additions = int(text[1:]) if text[1:].isdigit() else 0
                elif text.startswith("-"):
                    deletions = int(text[1:]) if text[1:].isdigit() else 0
            
            if additions or deletions:
                metadata["changes"] = {"additions": additions, "deletions": deletions}
            
        except Exception as e:
            print(f"Error extracting metadata: {e}")
        
        return metadata
    
    async def scrape_urls(self, urls: List[str], max_concurrent: int = 5) -> List[Dict]:
        """Scrape multiple URLs with concurrency control."""
        results = []
        
        # Process URLs in batches to avoid overwhelming the browser
        for i in range(0, len(urls), max_concurrent):
            batch = urls[i:i + max_concurrent]
            print(f"Processing batch {i//max_concurrent + 1}: {len(batch)} URLs")
            
            # For now, process sequentially to be safe with the shared browser instance
            batch_results = []
            for url in batch:
                result = await self.extract_task_data(url)
                batch_results.append(result)
                
                # Save individual result
                await self.save_task_data(result)
                
                # Small delay between requests
                await asyncio.sleep(1)
            
            results.extend(batch_results)
        
        return results
    
    async def save_task_data(self, task_data: Dict):
        """Save task data to individual JSON file."""
        task_id = task_data["task_id"]
        
        # Extract HTML for logs before saving JSON
        logs_html = None
        if task_data.get("logs") and task_data["logs"].get("_html"):
            logs_html = task_data["logs"].pop("_html")  # Remove HTML from logs data
        
        # Save JSON without HTML content
        output_file = self.output_dir / f"{task_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False)
        
        print(f"Saved data for {task_id}")
        
        # Also save logs as separate HTML file if available
        if logs_html:
            html_file = self.output_dir / f"{task_id}_logs.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(self._create_styled_html(logs_html, task_id))
    
    def _create_styled_html(self, logs_html: str, task_id: str) -> str:
        """Create a styled HTML document for logs."""
        css = """
        <style>
            body {
                font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                margin: 20px;
                line-height: 1.4;
            }

            .dark {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            
            .whitespace-pre-wrap {
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .whitespace-pre {
                white-space: pre;
            }
            
            /* ANSI colors */
            .ansi-black-fg { color: #000000; }
            .ansi-red-fg { color: #cd3131; }
            .ansi-green-fg { color: #0dbc79; }
            .ansi-yellow-fg { color: #e5e510; }
            .ansi-blue-fg { color: #2472c8; }
            .ansi-magenta-fg { color: #bc3fbc; }
            .ansi-cyan-fg { color: #11a8cd; }
            .ansi-white-fg { color: #e5e5e5; }
            
            .ansi-bright-black-fg { color: #666666; }
            .ansi-bright-red-fg { color: #f14c4c; }
            .ansi-bright-green-fg { color: #23d18b; }
            .ansi-bright-yellow-fg { color: #f5f543; }
            .ansi-bright-blue-fg { color: #3b8eea; }
            .ansi-bright-magenta-fg { color: #d670d6; }
            .ansi-bright-cyan-fg { color: #29b8db; }
            .ansi-bright-white-fg { color: #e5e5e5; }
            
            /* ANSI backgrounds */
            .ansi-black-bg { background-color: #000000; }
            .ansi-red-bg { background-color: #cd3131; }
            .ansi-green-bg { background-color: #0dbc79; }
            .ansi-yellow-bg { background-color: #e5e510; }
            .ansi-blue-bg { background-color: #2472c8; }
            .ansi-magenta-bg { background-color: #bc3fbc; }
            .ansi-cyan-bg { background-color: #11a8cd; }
            .ansi-white-bg { background-color: #e5e5e5; }
            
            /* ANSI styles */
            .ansi-bold { font-weight: bold; }
            .ansi-dim { opacity: 0.7; }
            .ansi-italic { font-style: italic; }
            .ansi-underline { text-decoration: underline; }
            .ansi-strikethrough { text-decoration: line-through; }
            
            /* Progress bars and other common elements */
            .progress-bar {
                display: inline-block;
                background-color: #333;
                border: 1px solid #555;
            }
            
            pre {
                background-color: #2d2d2d;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                border: 1px solid #404040;
            }
            
            .header {
                background-color: #252526;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 20px;
                border: 1px solid #404040;
            }
        </style>
        """
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Logs - {task_id}</title>
    {css}
</head>
<body>
    <div class="header">
        <h1>Codex Task Logs</h1>
        <p>Task ID: {task_id}</p>
    </div>
    <div class="logs-content">
        {logs_html}
    </div>
</body>
</html>"""
    
    async def close(self):
        """Clean up resources."""
        if hasattr(self, 'browser'):
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

async def main():
    """Main function to run the scraper."""
    # Read URLs from file
    urls = []
    with open('codex_urls.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    print(f"Found {len(urls)} URLs to scrape")
    
    scraper = CodexScraper()
    
    try:
        page = await scraper.connect_to_browser()
        if not page:
            print("Failed to connect to browser")
            return
        
        # Test with a single URL first
        test_url = "https://chatgpt.com/codex/tasks/task_e_682bcb3a96a88323b415a5326b690b26"
        print("Testing with single URL...")
        result = await scraper.extract_task_data(test_url)
        await scraper.save_task_data(result)
        
        print("Test result:")
        print(f"Prompt found: {'Yes' if result.get('prompt') else 'No'}")
        print(f"Logs found: {'Yes' if result.get('logs') else 'No'}")
        print(f"Metadata: {result.get('metadata', {})}")
        
        # Uncomment to scrape all URLs
        print("Scraping all URLs...")
        results = await scraper.scrape_urls(urls)  # Scrape all URLs
        print(f"Completed scraping {len(results)} URLs")
        
        # Save summary report
        summary = {
            "total_urls": len(urls),
            "successful_scrapes": len([r for r in results if not r.get('error')]),
            "failed_scrapes": len([r for r in results if r.get('error')]),
            "results": results
        }
        
        summary_file = Path("codex_tasks/scraping_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"Summary: {summary['successful_scrapes']} successful, {summary['failed_scrapes']} failed")
        
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main())
