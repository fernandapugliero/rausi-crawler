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

TIME_RE = re.compile(
    r"(?P<start>\d{1,2}[.:]\d{2})\s*[–-]\s*(?P<end>\d{1,2}[.:]\d{2})"
)

AGE_RE = re.compile(
    r"(?P<age>\d+\s*[-–]\s*\d+\s*(?:Jahr|Jahre|Monat|Monate))",
    re.IGNORECASE
)

BAD_TITLE_STARTS = [
    "uhr",
    "und ",
    ",",
    ".",
    "start am",
    "erster termin",
    "darüber hinaus",
]

BAD_TITLE_EXACT = {
    "",
    "uhr",
    "uhr)",
    "uhr:",
}

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


def extract_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    return [line for line in lines if len(line) > 2]


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


def find_explicit_day_in_line(line):
    stripped = line.strip()

    for day in DAY_NAMES:
        if stripped == day:
            return day

        if stripped.startswith(day + " "):
            return day

    return None


def remove_day_prefix(line):
    stripped = line.strip()

    for day in DAY_NAMES:
        if stripped == day:
            return ""
        if stripped.startswith(day + " "):
            return stripped[len(day):].strip()

    return stripped


def cleanup_title(title):
    title = title.strip(" ,:-–")
    title = re.sub(r"^Uhr\b[: ]*", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^\)+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def looks_like_bad_title(title):
    if not title:
        return True

    lower = title.lower().strip()

    if lower in BAD_TITLE_EXACT:
        return True

    if len(lower) < 4:
        return True

    for bad in BAD_TITLE_STARTS:
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

    current_day = None

    for line in lines:
        explicit_day = find_explicit_day_in_line(line)
        if explicit_day:
            current_day = explicit_day
            line = remove_day_prefix(line)

            # se a linha era só o dia, segue
            if not line:
                continue

        time_match = TIME_RE.search(line)
        if not time_match:
            continue

        start_time = time_match.group("start")
        end_time = time_match.group("end")

        title = line[time_match.end():].strip()
        title = cleanup_title(title)

        if looks_like_bad_title(title):
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group("age") if age_match else None

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
            candidate_blocks, events = parse_source(source)
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
