import asyncio
import re
import random
from playwright.async_api import async_playwright

def get_page_number_from_url(url: str) -> int:
    """
    Parses a URL to find the page number from a query parameter like '?p=XX'.
    Returns 0 if it's the base directory URL without a page number.
    """
    match = re.search(r'p=(\d+)', url)
    if match:
        return int(match.group(1))
    # The base URL (e.g., /directory/) is considered page 0 for sequencing.
    return 0

async def scrape_with_playwright(start_url: str, existing_visited_urls: set):
    """
    Scrapes a site in a single browser session with robust selectors and page-skip detection.
    """
    print(f"\n--- Starting new scraping session at: {start_url} ---")
    ACTION_TIMEOUT = 30000  # 30 seconds

    visited_urls = existing_visited_urls
    last_successful_url = start_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(start_url, timeout=60000, wait_until='networkidle')
            
        previous_page_number = get_page_number_from_url(start_url)
        previous_url = start_url

        while True:
            current_url = page.url
            if current_url in visited_urls:
                print(f"-> Already scraped {current_url} in a previous session. Re-evaluating page...")
            else:
                print(f"Scraping URL: {current_url}")
                visited_urls.add(current_url)
                last_successful_url = current_url
            
            # --- PAGE SKIP DETECTION ---
            current_page_number = get_page_number_from_url(current_url)
            if current_page_number > previous_page_number + 1:
                print("\n[!] PAGE SKIP DETECTED!")
                print(f"    Jumped from page {previous_page_number} to {current_page_number}.")
                print(f"    Forcing a restart from the last good URL: {previous_url}")
                await browser.close()
                return previous_url, visited_urls # Trigger restart

            try:
                next_button_selectors = [
                    'li.pagination-item--next a',
                    'nav[aria-label*="pagination" i] a:has-text("Next")',
                    'a[href][onclick]:has-text("Next")',
                    'a[rel="next"]',
                    '.pagination a:has-text("Next")'
                ]
                next_button = None
                for selector in next_button_selectors:
                    try:
                        candidate_button = page.locator(selector).first
                        await candidate_button.wait_for(state='visible', timeout=1000)
                        next_button = candidate_button
                        break 
                    except Exception:
                        continue
                
                if next_button is None:
                    raise Exception("Could not find a valid 'Next' button.")

                delay = random.uniform(1.5, 4.0)
                await asyncio.sleep(delay)
                await next_button.click(timeout=ACTION_TIMEOUT)
                
                await page.wait_for_load_state('domcontentloaded', timeout=ACTION_TIMEOUT)
                
                # Update state for the next loop iteration
                previous_page_number = current_page_number
                previous_url = current_url

            except Exception as e:
                print(f"\n[!] SCRAPER FAILED or finished.")
                print(f"   The last successful URL was: {last_successful_url}")
                print(f"   Reason: {repr(e)}")
                await browser.close()
                return last_successful_url, visited_urls
        
    print("\n✅ Scraping finished successfully without interruption.")
    await browser.close()
    return None, visited_urls

async def main():
    """
    The Orchestrator. Manages the scraping state and restarts the worker if needed.
    """
    print("--- Resilient Scraping Orchestrator ---")
    url_input = input("Please enter the full starting URL to scrape: ").strip()

    if not url_input:
        print("No URL entered. Exiting.")
        return

    if not re.match(r'^https?:\/\/', url_input):
        url_input = f"https://{url_input}"
        print(f"Assuming you meant: {url_input}")

    next_url_to_scrape = url_input
    master_visited_urls = set()
    max_restarts = 30
    restart_count = 0

    while next_url_to_scrape is not None and restart_count < max_restarts:
        if restart_count > 0:
            print("\n----------------------------------------------------")
            print(f"RESTARTING (Attempt {restart_count}/{max_restarts}). Waiting for 10 seconds...")
            print("----------------------------------------------------")
            await asyncio.sleep(10)

        next_url_to_scrape, master_visited_urls = await scrape_with_playwright(
            next_url_to_scrape, 
            master_visited_urls
        )
        restart_count += 1
    
    print("\n--- ORCHESTRATOR FINISHED ---")
    if restart_count >= max_restarts:
        print(f"Stopped due to reaching the max restart limit of {max_restarts}.")

    print(f"\nTotal unique URLs visited: {len(master_visited_urls)}")
    print("Final list of all visited URLs:")
    for url in sorted(list(master_visited_urls)):
        print(url)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting.")