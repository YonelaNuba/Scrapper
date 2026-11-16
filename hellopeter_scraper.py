"""
Scrape Discovery Insure reviews from HelloPeter and save them to a CSV file.

Install:  pip install requests beautifulsoup4
Run:      python hellopeter_scraper.py
"""

import csv
import re
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.hellopeter.com/discovery-insure"
REVIEW_PATH = "/discovery-insure/reviews/"
OUTPUT_FILE = "discovery_insure_reviews.csv"
MAX_PAGES = 200          # safety limit
DELAY_SECONDS = 2        # be polite to the server

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-ZA,en;q=0.9",
}

DATE_PATTERN = re.compile(r"\d{1,2} \w{3} \d{4}, \d{2}:\d{2}")


def get_page(page_number):
    """Download one page and return a BeautifulSoup object (or None)."""
    params = {"page": page_number} if page_number > 1 else {}
    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    if response.status_code != 200:
        print(f"Page {page_number}: HTTP {response.status_code}")
        return None
    return BeautifulSoup(response.text, "html.parser")


def find_review_container(link):
    """Walk up from a review link until we reach the whole review block."""
    node = link
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        if node.find("h3") and node.find("a", href=re.compile(r"/profile/")):
            return node
    return None


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_review(container, url):
    title_tag = container.find("h3")
    title = clean(title_tag.get_text()) if title_tag else ""

    author_tag = container.find("a", href=re.compile(r"/profile/"))
    author = clean(author_tag.get_text()) if author_tag else ""

    date_match = DATE_PATTERN.search(container.get_text(" "))
    date = date_match.group(0) if date_match else ""

    # The review text is the longest text block that is not the title.
    body = ""
    for tag in container.find_all(["p", "div", "span"]):
        if tag.find(["p", "div", "h3"]):  # skip wrappers, keep leaf blocks
            continue
        text = clean(tag.get_text())
        if text != title and len(text) > len(body):
            body = text

    return {"author": author, "date": date, "title": title, "review": body, "url": url}


def parse_page(soup):
    reviews = {}
    for link in soup.find_all("a", href=re.compile(re.escape(REVIEW_PATH))):
        url = link["href"]
        if url.startswith("/"):
            url = "https://www.hellopeter.com" + url
        if url in reviews:  # the page repeats each review (mobile/desktop)
            continue
        container = find_review_container(link)
        if container:
            reviews[url] = parse_review(container, url)
    return list(reviews.values())


def main():
    all_reviews = {}

    for page in range(1, MAX_PAGES + 1):
        soup = get_page(page)
        if soup is None:
            break

        page_reviews = parse_page(soup)
        new_reviews = [r for r in page_reviews if r["url"] not in all_reviews]

        if not new_reviews:
            print(f"Page {page}: no new reviews. Stopping.")
            break

        for review in new_reviews:
            all_reviews[review["url"]] = review

        print(f"Page {page}: {len(new_reviews)} new reviews (total {len(all_reviews)})")
        time.sleep(DELAY_SECONDS)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["author", "date", "title", "review", "url"]
        )
        writer.writeheader()
        writer.writerows(all_reviews.values())

    print(f"Done. Saved {len(all_reviews)} reviews to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
