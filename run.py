import json
import re
import time
import requests
from bs4 import BeautifulSoup

TIME_RE = re.compile(r"(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})")
AGE_RE = re.compile(r"(\d+\s*[-–]\s*\d+\s*(?:Jahr|Jahre|Monat|Monate))", re.IGNORECASE)

DAY_NAMES = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]

geocode_cache = {}


def fetch_html(url):
    headers = {"User-Agent": "RausiCrawler/0.1"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def clean_text(text):
    return " ".join(text.split()).strip()


def normalize_time(t):
    return t.replace(".", ":")


def geocode(address):

    if address in geocode_cache:
        return geocode_cache[address]

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }

    headers = {"User-Agent": "RausiCrawler/0.1"}

    try:

        r = requests.get(url, params=params, headers=headers, timeout=20)
        data = r.json()

        if not data:
            return None, None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])

        geocode_cache[address] = (lat, lon)

        time.sleep(1)

        return lat, lon

    except:
        return None, None


def extract_lines(html):

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")

    lines = text.split("\n")

    cleaned = []

    for l in lines:
        l = clean_text(l)

        if len(l) > 3:
            cleaned.append(l)

    return cleaned


def parse_source(source):

    html = fetch_html(source["url"])

    lines = extract_lines(html)

    current_day = None

    events = []

    lat, lon = geocode(source["address"])

    for line in lines:

        if line in DAY_NAMES:
            current_day = line
            continue

        match = TIME_RE.search(line)

        if not match:
            continue

        start, end = match.groups()

        title = line[match.end():].strip(" ,:-")

        if len(title) < 4:
            continue

        age_match = AGE_RE.search(title)

        age = age_match.group(1) if age_match else None

        event = {
            "title": title,
            "start_time": normalize_time(start),
            "end_time": normalize_time(end),
            "age": age,
            "day_of_week": current_day,
            "district": source["district"],
            "address": source["address"],
            "latitude": lat,
            "longitude": lon,
            "source_name": source["name"],
            "source_url": source["url"],
            "venue_name": source["name"]
        }

        events.append(event)

    return events


def dedupe(events):

    seen = set()

    clean = []

    for e in events:

        key = (
            e["title"],
            e["start_time"],
            e["end_time"],
            e["venue_name"]
        )

        if key in seen:
            continue

        seen.add(key)

        clean.append(e)

    return clean


def main():

    with open("sources.json", encoding="utf-8") as f:
        sources = json.load(f)

    all_events = []

    for source in sources:

        print("Crawling:", source["name"])

        try:

            events = parse_source(source)

            print("found", len(events), "events")

            all_events.extend(events)

        except Exception as e:

            print("error:", e)

    all_events = dedupe(all_events)

    output = {
        "events": all_events
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("saved", len(all_events), "events")


if __name__ == "__main__":
    main()
