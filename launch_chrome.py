#!/usr/bin/env python3
"""
Launch Playwright's Chrome with remote debugging enabled and persistent profile.
This script starts Chrome non-headless with automation indicators disabled.
"""

import subprocess
import sys
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    # Set environment variables to disable Google services
    os.environ["GOOGLE_API_KEY"] = "no"
    os.environ["GOOGLE_DEFAULT_CLIENT_ID"] = "no"
    os.environ["GOOGLE_DEFAULT_CLIENT_SECRET"] = "no"
    # Get Playwright's Chrome executable path
    with sync_playwright() as p:
        browser_path = p.chromium.executable_path
    
    # Create a persistent profile directory
    profile_dir = Path.home() / ".playwright_chrome_profile"
    profile_dir.mkdir(exist_ok=True)
    
    # Chrome arguments for remote debugging with automation indicators disabled
    chrome_args = [
        str(browser_path),
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-first-run",
    ]
    
    print(f"Launching Chrome with profile at: {profile_dir}")
    print("Remote debugging available at: http://localhost:9222")
    print("Press Ctrl+C to stop")
    
    try:
        # Launch Chrome with modified environment
        env = os.environ.copy()
        process = subprocess.Popen(chrome_args, env=env)
        process.wait()
    except KeyboardInterrupt:
        print("\nShutting down Chrome...")
        process.terminate()
        process.wait()

if __name__ == "__main__":
    main()
