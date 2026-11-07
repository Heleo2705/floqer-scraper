import asyncio
import re
import random
import os
from playwright.async_api import async_playwright, TimeoutError


def get_page_number(url: str) -> int:
    match = re.search(r"[?&]page=(\d+)", url)
    if match:
        return int(match.group(1))
    match = re.search(r"/page/(\d+)", url)
    if match:
        return int(match.group(1))
    return 1


async def handle_overlays(page):
    """
    Systematically finds and closes cookie banners or other pop-ups,
    including those inside iframes. Now updated for more banner types.
    """
    print("-> Searching for potential overlays...")
    # Add new selectors for ACCEPT/REFUSE buttons to the list
    reject_selectors = [
        'button:has-text("REFUSE")',
        'button:has-text("Reject all")',
        'button:has-text("Reject All")',
        'button:has-text("Decline")',
        'button:has-text("ACCEPT")',  # As a last resort, accept
        "#ccc-reject-settings",
    ]
    clicked = False
    for selector in reject_selectors:
        try:
            button = page.locator(selector).first
            await button.wait_for(state="visible", timeout=2500)
            print(f"   -> Found button with selector '{selector}'. Clicking...")
            await button.click()
            clicked = True
            break
        except Exception:
            continue

    if clicked:
        print("   -> Overlay click sent. Allowing a moment for it to disappear.")
        await page.wait_for_timeout(1500)
        return

    # Fallback to check inside iframes
    try:
        for frame in page.frames:
            for selector in reject_selectors:
                try:
                    button = frame.locator(selector).first
                    await button.wait_for(state="visible", timeout=2500)
                    await button.click()
                    clicked = True
                    break
                except Exception:
                    continue
            if clicked:
                break
    except Exception:
        pass

    if not clicked:
        print("-> No actionable overlays found.")


async def scrape_with_playwright(
    start_url: str, existing_visited_urls: set, scraped_data: dict
):
    print(f"\n--- Starting new scraping session at: {start_url} ---")
    ACTION_TIMEOUT = 30000
    visited_urls, last_successful_url = existing_visited_urls, start_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print(f"-> Navigating to {start_url}...")
            await page.goto(start_url, timeout=90000, wait_until="domcontentloaded")
            await handle_overlays(page)
            print("-> Waiting for main content to be ready...")
            # Wait for a generic body selector OR a specific content selector if known
            await page.wait_for_selector(
                'body:has-text("exhibitors"), #items-list', timeout=60000
            )
            print("-> Page is ready.")
        except TimeoutError as e:
            print(f"[!] FATAL ERROR: Initial page load failed: {e}")
            await browser.close()
            return start_url, visited_urls

        while True:
            current_url = page.url
            if current_url in visited_urls:
                print(f"-> Already scraped {current_url}.")
            else:
                print(f"Scraping URL: {current_url}")
                print(f"-> Capturing final HTML for: {current_url}")
                scraped_data[current_url] = await page.content()
                visited_urls.add(current_url)
                last_successful_url = current_url

            try:
                print("-> Searching for 'Next' button...")
                next_button_selectors = [
                    "a.next",  # Specific for techforretail.com
                    'button:has(i[class*="fa-arrow-right"])',  # Specific for websummit.com
                    'a[rel="next"]',
                    'button[rel="next"]',
                    'a[aria-label*="next" i]',
                    'button:has-text("Next")',
                ]
                next_button = None
                for selector in next_button_selectors:
                    try:
                        candidate_button = page.locator(selector).first
                        await candidate_button.wait_for(state="visible", timeout=5000)
                        if await candidate_button.is_enabled():
                            next_button = candidate_button
                            print(
                                f"   -> Found 'Next' button with selector: '{selector}'"
                            )
                            break
                    except Exception:
                        continue

                if next_button is None:
                    raise Exception("Could not find a valid 'Next' button.")
                if await next_button.is_disabled():
                    raise Exception("'Next' button is disabled, likely the last page.")

                # --- HYBRID WAIT LOGIC ---
                print("-> Clicking 'Next'. Preparing to wait for page update...")
                try:
                    # ATTEMPT 1: Wait for a background network response (for SPAs)
                    print("   -> Waiting for SPA-style network response...")
                    async with page.expect_response(
                        lambda r: "page=" in r.url and r.status == 200, timeout=10000
                    ):
                        await next_button.click()
                    print("   -> Network response received. Page has updated.")
                    await page.wait_for_timeout(1500)  # Pause for SPA to re-render
                except TimeoutError:
                    # FALLBACK: If no network response, it's a traditional site.
                    print(
                        "   -> No SPA response detected. Assuming traditional navigation."
                    )
                    if page.url == current_url:
                        await next_button.click()
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=ACTION_TIMEOUT
                    )
                    print(f"   -> Page successfully loaded: {page.url}")

            except Exception as e:
                print(f"\n[!] SCRAPER FAILED or finished.")
                print(f"   The last successful URL was: {last_successful_url}")
                print(f"   Reason: {repr(e)}")
                await browser.close()
                return last_successful_url, visited_urls

    await browser.close()
    return None, visited_urls


async def main():
    print("--- Resilient & Adaptable Scraping Orchestrator ---")
    url_input = input("Please enter the full starting URL to scrape: ").strip()
    if not url_input:
        # url_input = "https://websummit.com/featured-attendees"
        url_input = "https://techforretail.com/en/partners?searchtext="
    if not re.match(r"^https?:\/\/", url_input):
        url_input = f"https://{url_input}"
    print(f"Starting with URL: {url_input}")
    next_url_to_scrape = url_input
    master_visited_urls, master_scraped_data = set(), {}
    max_restarts, restart_count = 30, 0
    while next_url_to_scrape is not None and restart_count < max_restarts:
        if restart_count > 0:
            print(
                "\n"
                + "-" * 52
                + f"\nRESTARTING (Attempt {restart_count}/{max_restarts}). Waiting for 10 seconds...\n"
                + "-" * 52
            )
            await asyncio.sleep(10)
        next_url_to_scrape, master_visited_urls = await scrape_with_playwright(
            next_url_to_scrape, master_visited_urls, master_scraped_data
        )
        restart_count += 1
    print("\n--- ORCHESTRATOR FINISHED ---")
    if restart_count >= max_restarts:
        print(f"Stopped due to reaching the max restart limit of {max_restarts}.")
    print(f"\nTotal unique URLs visited: {len(master_visited_urls)}")
    if master_scraped_data:
        output_dir = "scraped_pages"
        os.makedirs(output_dir, exist_ok=True)
        print(
            f"\nSaving {len(master_scraped_data)} captured HTML pages to '{output_dir}/' directory..."
        )
        for url, content in master_scraped_data.items():
            sanitized_name = re.sub(r"[^\w\-_\. ]", "_", url)
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
