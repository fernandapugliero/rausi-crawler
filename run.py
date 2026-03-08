import json
import re
import time
import requests
from bs4 import BeautifulSoup


TIME_RANGE_RE = re.compile(r"(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})")
AGE_RE = re.compile(r"(\d+\s*[-–]\s*\d+\s*(?:Jahr(?:e)?|Monat(?:e)?))", re.IGNORECASE)

DAY_NAMES = {
    "Montag": "Montag",
    "Dienstag": "Dienstag",
    "Mittwoch": "Mittwoch",
    "Donnerstag": "Donnerstag",
    "Freitag": "Freitag",
    "Samstag": "Samstag",
    "Sonntag": "Sonntag",
}

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

_geocode_cache = {}


def fetch_html(url):
    headers = {"User-Agent": "RausiCrawler/0.1"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join(text.split()).strip()


def normalize_time(value):
    return value.replace(".", ":")


def cleanup_title(title):
    title = title.strip(" -–,:;")
    title = re.sub(r"^(Uhr\b[: ]*)", "", title).strip()
    title = re.sub(r"^(und\s+\w+\b)", "", title).strip()
    title = re.sub(r"^\)+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def looks_like_noise(text):
    if len(text) < 8:
        return True

    for bad in BAD_TEXT_PARTS:
        if bad.lower() in text.lower():
            return True

    return False


def extract_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.splitlines()]
    return [line for line in lines if line]


def geocode_address(address):
    if not address:
        return None, None

    if address in _geocode_cache:
        return _geocode_cache[address]

    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "RausiCrawler/0.1"
        }

        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        if not data:
            _geocode_cache[address] = (None, None)
            return None, None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])

        _geocode_cache[address] = (lat, lon)
        time.sleep(1)
        return lat, lon

    except Exception:
        _geocode_cache[address] = (None, None)
        return None, None


def build_event(source, title, start_time, end_time, day_of_week=None, age=None):
    lat, lon = geocode_address(source.get("address"))

    return {
        "title": title,
        "start_time": normalize_time(start_time),
        "end_time": normalize_time(end_time),
        "age": age,
        "day_of_week": day_of_week,
        "district": source.get("district"),
        "address": source.get("address"),
        "latitude": lat,
        "longitude": lon,
        "source_name": source["name"],
        "source_url": source["url"],
        "venue_name": source["name"]
    }


def parse_fann(lines, source):
    events = []
    candidate_blocks = []

    current_day = None

    for raw_line in lines:
        line = raw_line

        if looks_like_noise(line):
            continue

        # Se a linha for só o nome do dia
        if line in DAY_NAMES:
            current_day = line
            continue

        # Se a linha começar com o nome do dia e depois vier horário/texto
        for day in DAY_NAMES:
            if line.startswith(day + " "):
                current_day = day
                line = line[len(day):].strip()
                break

        # Também tenta detectar o dia se estiver contido na linha
        if current_day is None:
            for day in DAY_NAMES:
                if day in line:
                    current_day = day
                    break

        match = TIME_RANGE_RE.search(line)
        if not match:
            continue

        start_time, end_time = match.groups()

        # pega tudo depois do horário
        title = line[match.end():].strip()
        title = cleanup_title(title)

        if len(title) < 5:
            continue
        if title.lower().startswith("uhr"):
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": current_day,
            "district": source.get("district"),
            "address": source.get("address")
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start_time,
                end_time=end_time,
                day_of_week=current_day,
                age=age,
            )
        )

    return candidate_blocks, events


def parse_generic(lines, source):
    events = []
    candidate_blocks = []

    current_day = None

    for raw_line in lines:
        line = raw_line

        if looks_like_noise(line):
            continue

        if line in DAY_NAMES:
            current_day = line
            continue

        for day in DAY_NAMES:
            if line.startswith(day + " "):
                current_day = day
                line = line[len(day):].strip()
                break

        match = TIME_RANGE_RE.search(line)
        if not match:
            continue

        start_time, end_time = match.groups()
        title = line[match.end():].strip()
        title = cleanup_title(title)

        if len(title) < 5:
            continue
        if title.lower().startswith("uhr"):
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": current_day,
            "district": source.get("district"),
            "address": source.get("address")
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start_time,
                end_time=end_time,
                day_of_week=current_day,
                age=age,
            )
        )

    return candidate_blocks, events


def dedupe_events(events):
    seen = set()
    unique = []

    for event in events:
        key = (
            event["title"].lower().strip(),
            event["start_time"],
            event["end_time"],
            event.get("age") or "",
            event.get("day_of_week") or "",
            event["source_url"]
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(event)

    return unique


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    all_candidate_blocks = []
    all_events = []

    for source in sources:
        print(f"Fetching: {source['url']}")

        try:
            html = fetch_html(source["url"])
            lines = extract_lines(html)

            parser_name = source.get("parser", "generic")

            if parser_name == "fann":
                candidate_blocks, events = parse_fann(lines, source)
            else:
                candidate_blocks, events = parse_generic(lines, source)

            print(f"Found {len(events)} events for {source['name']}")

            all_candidate_blocks.extend(candidate_blocks)
            all_events.extend(events)

        except Exception as e:
            print(f"Error in {source['name']}: {e}")

    all_events = dedupe_events(all_events)

    output = {
        "candidate_blocks": all_candidate_blocks,
        "events": all_events
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_events)} events to output.json")


if __name__ == "__main__":
    main()
