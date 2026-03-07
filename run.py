import json
import re
import requests
from bs4 import BeautifulSoup


TIME_RE = re.compile(r"\b\d{1,2}[.:]\d{2}\s*[–-]\s*\d{1,2}[.:]\d{2}\b")
AGE_RE = re.compile(r"\b\d+\s*[-–]\s*\d+\s*Jahr", re.IGNORECASE)


BAD_TEXT_PARTS = [
    "Jugendwohnen im Kiez",
    "Geschäftsstelle",
    "Leitlinien",
    "Geschichte",
    "Transparenz",
    "Partner",
    "Presse und News",
    "Spenden",
    "Qualitätsmanagement",
    "Jobs",
    "Tochtergesellschaft",
    "Ambulante Hilfen",
    "Stationäre Hilfen",
    "Teilstationäre Hilfen",
    "Therapeutische Hilfen",
]


def fetch_html(url):
    headers = {
        "User-Agent": "RausiCrawler/0.1"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join(text.split()).strip()


def looks_like_noise(text):
    if len(text) < 12:
        return True

    for bad in BAD_TEXT_PARTS:
        if bad.lower() in text.lower():
            return True

    return False


def extract_candidate_blocks(html, source):
    soup = BeautifulSoup(html, "html.parser")

    results = []

    elements = soup.find_all(["h1", "h2", "h3", "h4", "p", "li"])

    for el in elements:
        text = clean_text(el.get_text(" ", strip=True))

        if looks_like_noise(text):
            continue

        has_time = bool(TIME_RE.search(text))
        has_age = bool(AGE_RE.search(text))

        if has_time or has_age or "anmeldung" in text.lower() or "baby" in text.lower() or "krabbel" in text.lower():
            results.append({
                "source_name": source["name"],
                "source_url": source["url"],
                "tag": el.name,
                "text": text,
                "has_time": has_time,
                "has_age": has_age
            })

    return results


def extract_schedule_items(blocks):
    items = []

    for block in blocks:
        text = block["text"]

        if not TIME_RE.search(text):
            continue

        items.append({
            "title_guess": text[:120],
            "raw_text": text,
            "source_name": block["source_name"],
            "source_url": block["source_url"]
        })

    return items


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    all_blocks = []
    all_schedule_items = []

    for source in sources:
        print(f"Fetching: {source['url']}")

        try:
            html = fetch_html(source["url"])

            blocks = extract_candidate_blocks(html, source)
            print(f"Found {len(blocks)} candidate blocks")

            schedule_items = extract_schedule_items(blocks)
            print(f"Found {len(schedule_items)} schedule-like items")

            all_blocks.extend(blocks)
            all_schedule_items.extend(schedule_items)

        except Exception as e:
            print(f"Error: {e}")

    output = {
        "candidate_blocks": all_blocks,
        "schedule_items": all_schedule_items
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved output.json with {len(all_blocks)} candidate blocks and {len(all_schedule_items)} schedule items")


if __name__ == "__main__":
    main()
