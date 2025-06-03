#!/usr/bin/env python3
"""
Playwright script to scrape Codex task data from ChatGPT.
Connects to existing Chrome browser instance via CDP.
"""

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Sample URL for testing
SAMPLE_URL = "https://chatgpt.com/codex/tasks/task_e_682bcb3a96a88323b415a5326b690b26"

async def connect_to_browser():
    """Connect to existing Chrome browser instance via CDP."""
    playwright = await async_playwright().start()
    
    # Connect to existing browser instance
    browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")
    
    # Get the default context and page
    contexts = browser.contexts
    if not contexts:
        print("No browser contexts found. Make sure Chrome is running with --remote-debugging-port=9222")
        return None, None, None
    
    context = contexts[0]
    pages = context.pages
    
    if not pages:
        # Create new page if none exist
        page = await context.new_page()
    else:
        page = pages[0]
    
    return playwright, browser, page

async def analyze_page_structure(page, url):
    """Navigate to URL and analyze the page structure."""
    print(f"Navigating to: {url}")
    
    try:
        # Navigate to the page with a longer timeout and different strategy
        await page.goto(url, wait_until='load', timeout=60000)
        
        # Wait for page to load
        await page.wait_for_timeout(5000)
        
        # Take a screenshot for debugging
        await page.screenshot(path=f"debug_screenshot_{url.split('/')[-1]}.png")
        
        # Check if we're on the correct page
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Get page title
        title = await page.title()
        print(f"Page title: {title}")
        
        # Look for the prompt element
        print("\n--- Searching for prompt element ---")
        prompt_selectors = [
            'div.px-4.text-sm.break-words.whitespace-pre-wrap',
            '[class*="px-4"][class*="text-sm"][class*="break-words"]',
            'div:has-text("View Settings")',
            'div:has-text("toggle")',
        ]
        
        for selector in prompt_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    html = await element.inner_html()
                    print(f"Found element with selector '{selector}':")
                    print(f"Text: {text}")
                    print(f"HTML: {html}")
                    print()
            except Exception as e:
                print(f"Error with selector '{selector}': {e}")
        
        # Look for tabs and logs
        print("\n--- Searching for tabs and logs ---")
        
        # First, let's find all buttons on the page
        all_buttons = await page.query_selector_all('button')
        print(f"Found {len(all_buttons)} buttons on the page")
        
        logs_tab = None
        for i, button in enumerate(all_buttons):
            try:
                text = await button.inner_text()
                if 'Logs' in text:
                    print(f"Button {i} contains 'Logs': {text}")
                    logs_tab = button
                    break
            except:
                continue
        
        if logs_tab:
            print("Clicking on Logs tab...")
            await logs_tab.click()
            await page.wait_for_timeout(2000)
            
            # Take screenshot after clicking logs
            await page.screenshot(path=f"debug_logs_{url.split('/')[-1]}.png")
            
            # Now look for the scrollable logs container
            log_selectors = [
                'div.react-scroll-to-bottom--css-siqfy-1n7m0yu',
                '[class*="react-scroll-to-bottom"]',
                'div[class*="scroll"]',
                'pre',
                'code',
            ]
            
            for selector in log_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for j, element in enumerate(elements):
                        text = await element.inner_text()
                        if len(text) > 100:  # Only show elements with substantial content
                            html = await element.inner_html()
                            print(f"Found logs element {j} with selector '{selector}':")
                            print(f"Text length: {len(text)} chars")
                            print(f"HTML length: {len(html)} chars")
                            print(f"First 200 chars of text: {text[:200]}")
                            print()
                except Exception as e:
                    print(f"Error with logs selector '{selector}': {e}")
        else:
            print("Could not find Logs tab")
        
        # Get all elements that might contain task data
        print("\n--- General page analysis ---")
        
        # Get all divs with text content
        all_divs = await page.query_selector_all('div')
        print(f"Found {len(all_divs)} div elements")
        
        # Look for elements with substantial text
        for i, div in enumerate(all_divs[:20]):  # Check first 20 divs
            try:
                text = await div.inner_text()
                if len(text) > 50 and 'View Settings' in text:
                    classes = await div.get_attribute('class')
                    print(f"Div {i} with target text:")
                    print(f"Classes: {classes}")
                    print(f"Text: {text}")
                    print()
            except:
                continue
        
        return True
        
    except Exception as e:
        print(f"Error analyzing page: {e}")
        return False

async def main():
    """Main function to run the scraper."""
    playwright, browser, page = await connect_to_browser()
    
    if not page:
        print("Failed to connect to browser")
        return
    
    try:
        # Analyze the sample URL first
        success = await analyze_page_structure(page, SAMPLE_URL)
        
        if success:
            print("Page analysis completed successfully")
        else:
            print("Page analysis failed")
            
    finally:
        await browser.close()
        await playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())