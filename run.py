import json
import re
import time
import requests
from bs4 import BeautifulSoup

DAY_NAMES = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]

TIME_EVENT_RE = re.compile(
    r"(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})\s+(.+)"
)

AGE_RE = re.compile(
    r"(\d+\s*[-–]\s*\d+\s*(?:Jahr|Jahre|Monat|Monate))",
    re.IGNORECASE
)

geocode_cache = {}


def fetch_html(url):
    headers = {"User-Agent": "RausiCrawler/0.1"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join(text.split()).strip()


def normalize_time(value):
    return value.replace(".", ":")


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
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

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


def parse_fann(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    # localizar início da agenda
    start_index = None
    end_index = None

    for i, line in enumerate(lines):
        if "Angebote im FaNN" in line:
            start_index = i
            break

    if start_index is None:
        return [], []

    # tenta parar antes da próxima seção grande
    for i in range(start_index + 1, len(lines)):
        if lines[i].startswith("Das FaNN ist ein Ort") or lines[i].startswith("Beratungsangebote"):
            end_index = i
            break

    if end_index is None:
        end_index = min(len(lines), start_index + 120)

    agenda_lines = lines[start_index:end_index]

    candidate_blocks = []
    events = []
    current_day = None

    for line in agenda_lines:
        line = line.strip()

        # detectar dia
        for day in DAY_NAMES:
            if line == day or line.startswith(day + ":"):
                current_day = day
                line = line.replace(day, "").replace(":", "").strip()
                break

        if not line:
            continue

        match = TIME_EVENT_RE.match(line)
        if not match:
            continue

        start_time, end_time, title = match.groups()
        title = title.strip(" ,:-")

        if len(title) < 4:
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": current_day,
            "district": source["district"],
            "address": source["address"]
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start_time,
                end_time=end_time,
                day_of_week=current_day,
                age=age
            )
        )

    return candidate_blocks, events


def parse_generic(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    candidate_blocks = []
    events = []

    for line in lines:
        match = TIME_EVENT_RE.match(line)
        if not match:
            continue

        start_time, end_time, title = match.groups()
        title = title.strip(" ,:-")

        if len(title) < 4:
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": None,
            "district": source["district"],
            "address": source["address"]
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start_time,
                end_time=end_time,
                day_of_week=None,
                age=age
            )
        )

    return candidate_blocks, events


def dedupe(events):
    seen = set()
    result = []

    for event in events:
        key = (
            event["title"].strip().lower(),
            event["start_time"],
            event["end_time"],
            event["venue_name"].strip().lower(),
            event.get("day_of_week")
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    all_candidate_blocks = []
    all_events = []

    for source in sources:
        print("Crawling:", source["name"])

        try:
            if "fann" in source["name"].lower():
                candidate_blocks, events = parse_fann(source)
            else:
                candidate_blocks, events = parse_generic(source)

            print("found", len(events), "events")
            all_candidate_blocks.extend(candidate_blocks)
            all_events.extend(events)

        except Exception as e:
            print("error:", e)

    all_events = dedupe(all_events)

    output = {
        "events": all_events,
        "candidate_blocks": all_candidate_blocks
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("saved", len(all_events), "events")


if __name__ == "__main__":
    main()
