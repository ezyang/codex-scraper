#!/usr/bin/env python3
"""
Extract all Codex task URLs from ChatGPT using Playwright CDP connection.
Connects to Chrome instance at localhost:9222 and navigates to the Codex tab.
Extracts all URLs matching pattern: https://chatgpt.com/codex/tasks/task_e_$HASH
"""

import asyncio
import re
from playwright.async_api import async_playwright
import json


async def extract_codex_urls():
    """Connect to Chrome via CDP and extract all Codex task URLs."""
    
    # Connect to Chrome via CDP
    async with async_playwright() as p:
        # Connect to existing Chrome instance
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        
        # Get the first context and page
        contexts = browser.contexts
        if not contexts:
            print("No browser contexts found")
            return []
            
        context = contexts[0]
        pages = context.pages
        
        # Find the Codex page or navigate to it
        codex_page = None
        for page in pages:
            if "codex" in page.url:
                codex_page = page
                break
        
        if not codex_page:
            # If no Codex page is found, use the first page and navigate
            codex_page = pages[0] if pages else await context.new_page()
            await codex_page.goto("https://chatgpt.com/codex?tab=archived")
        else:
            # Make sure we're on the archived tab
            if "tab=archived" not in codex_page.url:
                await codex_page.goto("https://chatgpt.com/codex?tab=archived")
        
        # Wait for the page to load
        await codex_page.wait_for_load_state("networkidle")
        
        # Scroll to load all tasks (if lazy loading is implemented)
        print("Scrolling to load all tasks...")
        previous_height = 0
        while True:
            # Get current scroll height
            current_height = await codex_page.evaluate("document.body.scrollHeight")
            
            # Scroll to bottom
            await codex_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # Wait a bit for new content to load
            await asyncio.sleep(1)
            
            # Check if we've reached the end
            new_height = await codex_page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height
        
        print("Extracting URLs...")
        
        # Extract all links matching the pattern
        urls = await codex_page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*="/codex/tasks/task_e_"]');
                const urls = new Set();
                
                links.forEach(link => {
                    const href = link.getAttribute('href');
                    if (href) {
                        // Convert relative URLs to absolute
                        const absoluteUrl = new URL(href, window.location.origin).href;
                        urls.add(absoluteUrl);
                    }
                });
                
                return Array.from(urls);
            }
        """)
        
        # Additional validation using regex
        pattern = re.compile(r'https://chatgpt\.com/codex/tasks/task_e_[a-fA-F0-9]+')
        valid_urls = [url for url in urls if pattern.match(url)]
        
        print(f"Found {len(valid_urls)} unique Codex task URLs")
        
        # Close the browser connection
        await browser.close()
        
        return valid_urls


async def save_urls_to_file(urls, filename="codex_urls.txt"):
    """Save URLs to a text file."""
    with open(filename, 'w') as f:
        for url in sorted(urls):
            f.write(url + '\n')
    print(f"Saved {len(urls)} URLs to {filename}")


async def save_urls_to_json(urls, filename="codex_urls.json"):
    """Save URLs to a JSON file with additional metadata."""
    data = {
        "total_count": len(urls),
        "extraction_date": asyncio.get_event_loop().time(),
        "urls": sorted(urls)
    }
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(urls)} URLs to {filename}")


async def main():
    """Main function to extract and save Codex URLs."""
    try:
        # Extract URLs
        urls = await extract_codex_urls()
        
        if urls:
            # Save to both text and JSON formats
            await save_urls_to_file(urls)
            await save_urls_to_json(urls)
            
            # Print first few URLs as sample
            print("\nSample URLs:")
            for url in urls[:5]:
                print(f"  {url}")
            if len(urls) > 5:
                print(f"  ... and {len(urls) - 5} more")
        else:
            print("No URLs found!")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
