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

DAY_ALIASES = {
    "mo": "Montag",
    "di": "Dienstag",
    "mi": "Mittwoch",
    "do": "Donnerstag",
    "fr": "Freitag",
    "sa": "Samstag",
    "so": "Sonntag",
}

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
    if not address:
        return None, None

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
            geocode_cache[address] = (None, None)
            return None, None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        geocode_cache[address] = (lat, lon)

        time.sleep(1)
        return lat, lon

    except Exception:
        geocode_cache[address] = (None, None)
        return None, None


def extract_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = text.split("\n")

    cleaned = []
    for line in lines:
        line = clean_text(line)
        if len(line) > 2:
            cleaned.append(line)

    return cleaned


def find_day_in_text(text):
    lower = text.lower().strip()

    for day in DAY_NAMES:
        if lower == day.lower():
            return day

    for alias, full_day in DAY_ALIASES.items():
        if lower == alias:
            return full_day

    return None


def find_recent_day(lines, current_index, lookback=6):
    start = max(0, current_index - lookback)

    for i in range(current_index - 1, start - 1, -1):
        candidate = lines[i]
        day = find_day_in_text(candidate)
        if day:
            return day

    return None


def cleanup_title(title):
    title = title.strip(" ,:-")
    title = re.sub(r"^Uhr\b[: ]*", "", title).strip()
    title = re.sub(r"^\)+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def looks_like_bad_title(title):
    if len(title) < 4:
        return True

    bad_starts = [
        "uhr",
        "und ",
        ",",
        ".",
        "start am",
        "erster termin",
    ]

    lower = title.lower()

    for bad in bad_starts:
        if lower.startswith(bad):
            return True

    return False


def build_event(source, title, start_time, end_time, day_of_week=None, age=None):
    lat, lon = geocode(source["address"])

    return {
        "title": title,
        "start_time": normalize_time(start_time),
        "end_time": normalize_time(end_time),
        "age": age,
        "day_of_week": day_of_week,
        "district": source["district"],
        "address": source["address"],
        "latitude": lat,
        "longitude": lon,
        "source_name": source["name"],
        "source_url": source["url"],
        "venue_name": source["name"]
    }


def parse_source(source):
    html = fetch_html(source["url"])
    lines = extract_lines(html)

    events = []
    candidate_blocks = []

    for idx, line in enumerate(lines):
        match = TIME_RE.search(line)
        if not match:
            continue

        start, end = match.groups()
        title = line[match.end():].strip()
        title = cleanup_title(title)

        if looks_like_bad_title(title):
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        day_of_week = find_recent_day(lines, idx, lookback=6)

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": day_of_week,
            "district": source["district"],
            "address": source["address"]
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start,
                end_time=end,
                day_of_week=day_of_week,
                age=age
            )
        )

    return candidate_blocks, events


def dedupe(events):
    seen = set()
    clean = []

    for e in events:
        key = (
            e["title"],
            e["start_time"],
            e["end_time"],
            e["venue_name"],
            e.get("day_of_week")
        )

        if key in seen:
            continue

        seen.add(key)
        clean.append(e)

    return clean


def main():
    with open("sources.json", encoding="utf-8") as f:
        sources = json.load(f)

    all_candidate_blocks = []
    all_events = []

    for source in sources:
        print("Crawling:", source["name"])

        try:
            candidate_blocks, events = parse_source(source)
            print("found", len(events), "events")

            all_candidate_blocks.extend(candidate_blocks)
            all_events.extend(events)

        except Exception as e:
            print("error:", e)

    all_events = dedupe(all_events)

    output = {
        "candidate_blocks": all_candidate_blocks,
        "events": all_events
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("saved", len(all_events), "events")


if __name__ == "__main__":
    main()
