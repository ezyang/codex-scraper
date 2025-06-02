#!/usr/bin/env python3
"""
Connect to remote Chrome instance via CDP and perform simple navigation.
Run this after launching Chrome with launch_chrome.py
"""

import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Connecting to remote Chrome at localhost:9222...")
    
    async with async_playwright() as p:
        try:
            # Connect to the existing Chrome instance
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            
            # Get existing contexts or create a new one
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                print(f"Using existing context with {len(context.pages)} pages")
            else:
                context = await browser.new_context()
                print("Created new browser context")
            
            # Get existing page or create new one
            pages = context.pages
            if pages:
                page = pages[0]
                print("Using existing page")
            else:
                page = await context.new_page()
                print("Created new page")
            
            # Navigate to ChatGPT
            print("Navigating to chatgpt.com...")
            await page.goto("https://chatgpt.com", wait_until="domcontentloaded")
            
            # Wait a moment to see the page load
            await asyncio.sleep(2)
            
            print(f"Successfully navigated to: {page.url}")
            print("Page title:", await page.title())
            
            # Keep the connection alive for a moment
            print("Connection successful! Keeping alive for 5 seconds...")
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"Error connecting to Chrome: {e}")
            print("Make sure Chrome is running with: python launch_chrome.py")
        
        finally:
            print("Disconnecting...")

if __name__ == "__main__":
    asyncio.run(main())