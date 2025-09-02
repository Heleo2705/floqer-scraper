import asyncio
import re
import random
import os
from playwright.async_api import async_playwright, TimeoutError

def get_page_number(url: str) -> int:
    """
    Parses a URL to find a page number from various common pagination formats.
    """
    # Pattern 1: Look for ?p=... or ?page=... or &p=... or &page=...
    match = re.search(r'[?&](?:page|p)=(\d+)', url)
    if match:
        return int(match.group(1))

    # Pattern 2: Look for /page/...
    match = re.search(r'/page/(\d+)', url)
    if match:
        return int(match.group(1))

    # Pattern 3: Look for a number at the very end of the URL path
    match = re.search(r'/(\d+)/?$', url)
    if match:
        return int(match.group(1))
    
    return 1

async def handle_dynamic_content_loading(page):
    """
    Handles 'See More' buttons and basic 'infinite scroll' by scrolling and clicking.
    """
    see_more_selectors = [
        # TIER 1: HIGH-CONFIDENCE ATTRIBUTE SELECTORS
        '[data-testid*="load-more" i]', '[data-testid*="show-more" i]',
        '[data-action*="load-more" i]', '[data-action*="show-more" i]',
        'button[aria-label*="load more" i]', 'a[aria-label*="load more" i]',
        'button[aria-label*="show more" i]', 'a[aria-label*="show more" i]',
        # TIER 2: COMMON TEXT PATTERNS
        'button:has-text("Show More")', 'button:has-text("Load More")',
        'button:has-text("See More")', 'button:has-text("View More")',
        'a:has-text("Show More")', 'a:has-text("Load More")',
        'a:has-text("See More")', 'a:has-text("View More")',
        # TIER 3: COMMON CLASS NAME PATTERNS
        '[class*="load-more" i]', '[class*="show-more" i]',
        '[class*="see-more" i]', '[class*="view-more" i]',
        '[class*="loadmore" i]', '[class*="showmore" i]',
        # TIER 4: GENERIC FALLBACKS
        'a.more-link', '.more-button'
    ]
    
    while True:
        clicked_or_scrolled = False
        # STRATEGY 1: CLICK 'SEE MORE' BUTTONS
        for selector in see_more_selectors:
            try:
                see_more_button = page.locator(selector).first
                if await see_more_button.is_visible():
                    print(f"-> Found and clicking a '{await see_more_button.text_content()}' button.")
                    await see_more_button.click()
                    # CRITICAL FIX: Wait for content to load, don't re-navigate the page.
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    clicked_or_scrolled = True
                    break 
            except Exception:
                continue
        
        if clicked_or_scrolled:
            await asyncio.sleep(random.uniform(1.0, 2.5))
            continue

        # STRATEGY 2: HANDLE INFINITE SCROLL
        initial_height = await page.evaluate('document.body.scrollHeight')
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except TimeoutError:
            # This is okay, it just means scrolling didn't trigger network activity
            pass
        await asyncio.sleep(2)
        new_height = await page.evaluate('document.body.scrollHeight')

        if new_height > initial_height:
            print(f"-> Scrolled down to load more content (height changed from {initial_height} to {new_height}).")
            clicked_or_scrolled = True
        
        if not clicked_or_scrolled:
            print("-> No more dynamic content buttons or scroll-to-load content found.")
            break

async def scrape_with_playwright(start_url: str, existing_visited_urls: set, scraped_data: dict):
    """
    Scrapes a site and populates the scraped_data dictionary with final page HTML.
    """
    print(f"\n--- Starting new scraping session at: {start_url} ---")
    ACTION_TIMEOUT = 30000

    visited_urls = existing_visited_urls
    last_successful_url = start_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # CRITICAL FIX: Changed 'networkidle' to 'load' for reliability.
            await page.goto(start_url, timeout=60000, wait_until='load')
        except TimeoutError as e:
            print(f"[!] FATAL ERROR: Page.goto timed out: {e}")
            await browser.close()
            return start_url, visited_urls

        previous_page_number = get_page_number(start_url)
        previous_url = start_url

        while True:
            current_url = page.url
            if current_url in visited_urls:
                print(f"-> Already scraped {current_url}. Re-evaluating page...")
            else:
                print(f"Scraping URL: {current_url}")
                await handle_dynamic_content_loading(page)
                
                print(f"-> Capturing final HTML for: {current_url}")
                # NEW: Capture HTML and add it to our data dictionary
                scraped_data[current_url] = await page.content()
                
                visited_urls.add(current_url)
                last_successful_url = current_url
            
            current_page_number = get_page_number(current_url)
            if current_page_number > previous_page_number + 1:
                print("\n[!] PAGE SKIP DETECTED!")
                print(f"    Forcing a restart from the last good URL: {previous_url}")
                await browser.close()
                return previous_url, visited_urls

            try:
                # CRITICAL FIX: Restored the correct selectors for 'Next' buttons.
                next_button_selectors = [
                    'a[rel="next"]', 'button[rel="next"]',
                    'nav[aria-label*="pagination" i] a:has-text("Next")',
                    'nav[aria-label*="pagination" i] button:has-text("Next")',
                    'li.pagination-item--next a', '.pagination a:has-text("Next")',
                    '.pagination button:has-text("Next")', 'button:has-text("Next")',
                    'a[aria-label*="next" i]', 'button[aria-label*="next" i]',
                    'a[title*="next" i]', 'button[title*="next" i]'
                ]
                next_button = None
                for selector in next_button_selectors:
                    try:
                        candidate_button = page.locator(selector).first
                        await candidate_button.wait_for(state='visible', timeout=1000)
                        if await candidate_button.is_enabled():
                            next_button = candidate_button
                            print(f"Found 'Next' button with selector: '{selector}'")
                            break 
                    except Exception:
                        continue
                
                if next_button is None:
                    raise Exception("Could not find a valid 'Next' button.")

                await asyncio.sleep(random.uniform(1.5, 4.0))
                await next_button.click(timeout=ACTION_TIMEOUT)
                
                await page.wait_for_url(lambda url: url != current_url, timeout=ACTION_TIMEOUT)
                
                previous_page_number = current_page_number
                previous_url = current_url

            except Exception as e:
                print(f"\n[!] SCRAPER FAILED or finished.")
                print(f"   The last successful URL was: {last_successful_url}")
                print(f"   Reason: {repr(e)}")
                await browser.close()
                return last_successful_url, visited_urls
        
    await browser.close()
    return None, visited_urls

async def main():
    """
    Orchestrator: Manages state and saves the scraped HTML data to files.
    """
    print("--- Resilient & Adaptable Scraping Orchestrator ---")
    url_input = input("Please enter the full starting URL to scrape: ").strip()

    if not url_input:
        print("No URL entered. Exiting.")
        return

    if not re.match(r'^https?:\/\/', url_input):
        url_input = f"https://{url_input}"
        print(f"Assuming you meant: {url_input}")

    next_url_to_scrape = url_input
    master_visited_urls = set()
    # NEW: Dictionary to hold our scraped HTML data
    master_scraped_data = {}
    max_restarts = 30
    restart_count = 0

    while next_url_to_scrape is not None and restart_count < max_restarts:
        if restart_count > 0:
            print("\n----------------------------------------------------")
            print(f"RESTARTING (Attempt {restart_count}/{max_restarts}). Waiting for 10 seconds...")
            print("----------------------------------------------------")
            await asyncio.sleep(10)

        # NEW: Pass the data dictionary to the scraper function
        next_url_to_scrape, master_visited_urls = await scrape_with_playwright(
            next_url_to_scrape, 
            master_visited_urls,
            master_scraped_data
        )
        restart_count += 1
    
    print("\n--- ORCHESTRATOR FINISHED ---")
    if restart_count >= max_restarts:
        print(f"Stopped due to reaching the max restart limit of {max_restarts}.")

    print(f"\nTotal unique URLs visited: {len(master_visited_urls)}")
    
    # NEW: Save the captured HTML to files
    if master_scraped_data:
        output_dir = "scraped_pages"
        os.makedirs(output_dir, exist_ok=True)
        print(f"\nSaving {len(master_scraped_data)} captured HTML pages to '{output_dir}/' directory...")
        for url, content in master_scraped_data.items():
            # Sanitize URL to create a safe filename
            sanitized_name = re.sub(r'[^\w\-_\. ]', '_', url)
            file_path = os.path.join(output_dir, f"{sanitized_name}.html")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  - Saved {file_path}")
            except Exception as e:
                print(f"  - FAILED to save {file_path}. Reason: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting.")