# Codex Export Project

## Overview
This project is designed to scrape and export task data from ChatGPT's Codex system. It uses Chrome DevTools Protocol (CDP) to connect to a running Chrome browser instance and extract task prompts and logs from Codex task pages.

## Components

### URL Extraction (`get_urls.py`)
- Connects to Chrome via CDP at localhost:9222
- Navigates to ChatGPT Codex archived tasks page
- Scrolls through the page to load all tasks via lazy loading
- Extracts all task URLs matching pattern: `https://chatgpt.com/codex/tasks/task_e_$HASH`
- Saves URLs to both text and JSON formats

### Task Scraping (`scrape_urls.py` and `scrape_urls_v2.py`)
- Takes the extracted URLs and visits each task page
- Extracts key data from each task:
  - Task prompt (the main instruction text)
  - Logs (build/execution output)
  - Metadata (date, repository, PR stats)
  - File changes
  - Summary/notes sections
- Saves extracted data as JSON files and formatted HTML logs

## Usage
1. Start Chrome with CDP enabled: `chrome --remote-debugging-port=9222`
2. Navigate to ChatGPT Codex in the browser and log in
3. Run `python get_urls.py` to extract task URLs
4. Run `python scrape_urls_v2.py` to scrape task data

## Current Issues
The scraper has navigation issues where it fails to properly load task pages, staying on the front page instead of navigating to specific task URLs. This results in timeouts and screenshots of the wrong page.

## Dependencies
- playwright: Browser automation
- Python 3.12+

## Output
- `codex_urls.txt`: List of extracted task URLs
- `codex_urls.json`: URLs with metadata
- `codex_tasks/`: Directory containing scraped task data
  - Individual JSON files per task
  - HTML formatted logs
  - Screenshots for debugging
  - Summary JSON with success/failure stats