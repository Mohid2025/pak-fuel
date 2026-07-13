"""
Scrapes notified petroleum prices from Pakistan State Oil's public archive.

Why PSO and not OGRA?
  OGRA (the regulator) is the ultimate source, but ogra.org.pk sits behind bot
  detection and blocks automated requests. PSO is state-owned and publishes the
  same notified prices as plain server-rendered HTML, with a paginated archive
  going back years. It is a primary source, and it is reachable.

Why not scrape news sites?
  Because they contradict each other. While researching this, three "fuel price"
  sites reported three different current petrol prices, and one was a spam farm.
  Never let an aggregator between you and the source.

Usage:
    python scrape_pso.py --backfill     # walk every archive page (do this once)
    python scrape_pso.py                # page 1 only (the daily job)

Output:
    public/data/prices.json  -- structured, for the frontend
    public/data/prices.csv   -- flat, so other people can reuse your dataset
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "https://psopk.com/fuel-prices/pol/archives"
OUT_DIR = os.path.join("public", "data")
UA = "pak-fuel-tracker/1.0 (+https://github.com/Mohid2025/pak-fuel)"

# PSO's product labels have changed over the years (MOGAS -> PMG -> PREMIER
# EURO 5, etc). Map raw labels onto stable keys. Anything unmapped gets LOUDLY
# reported rather than silently dropped -- across ~400 revisions spanning many
# years, unknown labels are a certainty, not an edge case.
PRODUCT_MAP = {
    "PREMIER EURO 5": "petrol",
    "PREMIER": "petrol",
    "MOGAS": "petrol",
    "PMG": "petrol",
    "HI-CETANE DIESEL EURO 5": "hsd",
    "HI-CETANE DIESEL": "hsd",
    "HSD": "hsd",
    "HIGH SPEED DIESEL": "hsd",
    "LDO": "ldo",
    "SKO": "sko",
    "KEROSENE": "sko",
    "JP-1": "jp1",
    "E10 GASOLINE": "e10",
    "HOBC": "hobc",
    "OCTANE + EURO 5": "hobc",
}

unmapped_labels = set()


def parse_price(text):
    """'Rs.310.71/Ltr' or '340.00' -> 310.71 / 340.0. None if unparseable."""
    m = re.search(r"(\d[\d,]*\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def parse_date(text):
    """PSO mixes formats: 'July 11, 2026' and '2026-07-11'. Handle both."""
    text = re.sub(r"Effective\s*From\s*:?\s*", "", text, flags=re.I).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def scrape_page(page):
    """Return a list of revisions found on one archive page."""
    url = ARCHIVE_URL if page == 1 else f"{ARCHIVE_URL}?page={page}"
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    revisions = []

    # Structure-based, not class-based: find every node whose text announces an
    # effective date, then take the next table after it. This survives CSS and
    # markup reshuffles that would break a selector like ".price-card .value".
    for node in soup.find_all(string=re.compile(r"Effective\s*From", re.I)):
        date = parse_date(node.strip())
        if not date:
            continue

        table = node.find_next("table")
        if table is None:
            continue

        products = {}
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            label = cells[0].upper().strip()
            if label in ("PRODUCT NAME", "PRODUCT", ""):
                continue  # header row

            key = PRODUCT_MAP.get(label)
            if key is None:
                unmapped_labels.add(cells[0])
                continue

            price = parse_price(cells[1])
            # PSO writes Rs.0/Ltr for products it isn't currently selling.
            # That is "not offered", not "free" -- don't record it as a price.
            if price is not None and price > 0:
                products[key] = price

        if products:
            revisions.append({"effective_from": date, "products": products})

    return revisions


def discover_last_page(soup_text):
    """Find the highest ?page=N link so we don't hardcode the page count."""
    pages = [int(n) for n in re.findall(r"\?page=(\d+)", soup_text)]
    return max(pages) if pages else 1


def load_existing(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("revisions", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true",
                    help="walk every archive page instead of just page 1")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    json_path = os.path.join(OUT_DIR, "prices.json")

    if args.backfill:
        first = requests.get(ARCHIVE_URL, headers={"User-Agent": UA}, timeout=30)
        first.raise_for_status()
        last_page = discover_last_page(first.text)
        print(f"Archive has {last_page} pages. Backfilling all of them.")
        pages = range(1, last_page + 1)
    else:
        pages = [1]

    scraped = []
    for p in pages:
        try:
            found = scrape_page(p)
        except requests.HTTPError as e:
            print(f"  page {p}: HTTP error {e} -- skipping", file=sys.stderr)
            continue
        print(f"  page {p}: {len(found)} revisions")
        scraped.extend(found)
        if len(list(pages)) > 1:
            time.sleep(1)  # be a polite citizen of someone else's server

    if not scraped:
        # Fail loudly. A fuel price site serving stale numbers because the
        # scraper silently broke is worse than one that's honestly down.
        print("ERROR: scraped zero revisions. The page structure probably "
              "changed. Not writing output.", file=sys.stderr)
        sys.exit(1)

    # Upsert by effective date; newly scraped values win.
    merged = {r["effective_from"]: r for r in load_existing(json_path)}
    for r in scraped:
        merged[r["effective_from"]] = r
    revisions = sorted(merged.values(), key=lambda r: r["effective_from"])

    # Derive the change vs the previous revision -- this is what people
    # actually care about ("did it go up?"), so compute it once here rather
    # than in the frontend.
    for i, rev in enumerate(revisions):
        rev["change"] = {}
        if i == 0:
            continue
        prev = revisions[i - 1]["products"]
        for key, price in rev["products"].items():
            if key in prev:
                rev["change"][key] = round(price - prev[key], 2)

    now = datetime.now(timezone.utc).isoformat()
    with open(json_path, "w") as f:
        json.dump({
            "updated_at": now,
            "source": "Pakistan State Oil (psopk.com) -- notified POL prices",
            "note": "Prices exclude freight from shipping point to retail "
                    "outlet; pump price may differ slightly by location.",
            "revision_count": len(revisions),
            "revisions": revisions,
        }, f, indent=2)

    # Flat CSV. Costs you nothing and makes the dataset genuinely reusable --
    # which is the difference between a demo and a public good.
    csv_path = os.path.join(OUT_DIR, "prices.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["effective_from", "product", "price_pkr_per_litre", "change"])
        for rev in revisions:
            for key, price in sorted(rev["products"].items()):
                w.writerow([rev["effective_from"], key, price,
                            rev["change"].get(key, "")])

    print(f"\nWrote {len(revisions)} revisions "
          f"({revisions[0]['effective_from']} -> {revisions[-1]['effective_from']})")

    if unmapped_labels:
        print("\nUNMAPPED PRODUCT LABELS -- add these to PRODUCT_MAP:")
        for label in sorted(unmapped_labels):
            print(f"  {label!r}")


if __name__ == "__main__":
    main()
