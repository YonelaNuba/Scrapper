"""
Scrape ALL Discovery Insure reviews (with ratings) from HelloPeter.

The site loads new reviews with JavaScript when you click "Next",
so we use a real browser (Playwright) and read the data the site loads.

Install:
    pip install playwright beautifulsoup4
    playwright install chromium

Run:
    python hellopeter_scraper_playwright.py
"""

import csv
import json
import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://www.hellopeter.com/discovery-insure"
OUTPUT_FILE = "discovery_insure_reviews.csv"
DEBUG_FILE = "debug_first_response.json"   # lets you check the field names
MAX_PAGES = 250
HEADLESS = True        # set to False to watch the browser work

captured = []          # JSON responses collected from the site
debug_saved = False


# ---------- helpers to read the JSON the site loads ----------

def flatten(data, prefix=""):
    """Turn nested dicts into one flat dict: {'author.name': 'x'}."""
    flat = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, name + "."))
        elif isinstance(value, list):
            flat[name] = json.dumps(value, ensure_ascii=False)
        else:
            flat[name] = value
    return flat


def find_review_lists(obj):
    """Find lists of dicts that look like reviews (have a rating + text/title)."""
    found = []
    if isinstance(obj, list):
        if obj and all(isinstance(i, dict) for i in obj):
            keys = " ".join(obj[0].keys()).lower()
            if "rating" in keys and re.search(r"content|body|text|title|comment", keys):
                found.append(obj)
        for item in obj:
            found.extend(find_review_lists(item))
    elif isinstance(obj, dict):
        for value in obj.values():
            found.extend(find_review_lists(value))
    return found


def on_response(response):
    global debug_saved
    if "json" not in response.headers.get("content-type", ""):
        return
    try:
        data = response.json()
    except Exception:
        return
    lists = find_review_lists(data)
    if lists:
        captured.append(lists)
        if not debug_saved:
            with open(DEBUG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            debug_saved = True


# ---------- main scraping ----------

def click_next(page):
    """Click the Next button. Return False if there is no usable Next button."""
    button = page.get_by_role("button", name=re.compile(r"^next$", re.I))
    if button.count() == 0:
        button = page.get_by_text(re.compile(r"^next$", re.I))
    if button.count() == 0:
        return False
    button = button.first
    if button.is_disabled():
        return False
    button.scroll_into_view_if_needed()
    button.click()
    return True


def main():
    reviews = {}   # key -> flat review dict (removes duplicates)

    def collect():
        new = 0
        while captured:
            for review_list in captured.pop(0):
                for item in review_list:
                    flat = flatten(item)
                    key = str(flat.get("id") or flat.get("slug") or
                              json.dumps(flat, sort_keys=True))
                    if key not in reviews:
                        reviews[key] = flat
                        new += 1
        return new

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(locale="en-ZA")
        page.on("response", on_response)
        page.goto(URL, wait_until="networkidle")
        time.sleep(2)

        # If the first page came with the HTML (not JSON), go Next then Previous
        # so the site loads page 1 as JSON too.
        if not captured:
            if click_next(page):
                time.sleep(2)
                prev = page.get_by_role("button", name=re.compile(r"previous", re.I))
                if prev.count():
                    prev.first.click()
                    time.sleep(2)

        print(f"Page 1: {collect()} reviews")

        for page_number in range(2, MAX_PAGES + 1):
            if not click_next(page):
                print("No more Next button. Finished.")
                break
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass
            time.sleep(1.5)   # be polite

            added = collect()
            print(f"Page {page_number}: {added} new reviews (total {len(reviews)})")
            if added == 0:
                print("No new reviews. Finished.")
                break

        browser.close()

    if not reviews:
        print(
            "No reviews captured. The site may load data differently.\n"
            "Open the site in Chrome > F12 > Network > Fetch/XHR, click Next,\n"
            "and send me the request URL and a sample of the response."
        )
        return

    columns = []
    for review in reviews.values():
        for col in review:
            if col not in columns:
                columns.append(col)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(reviews.values())

    print(f"Done. Saved {len(reviews)} reviews to {OUTPUT_FILE}")
    print("Check the rating column name in the CSV (it contains the word 'rating').")


if __name__ == "__main__":
    main()
