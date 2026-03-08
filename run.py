import json
import re
import requests
from bs4 import BeautifulSoup


TIME_RANGE_RE = re.compile(r"^(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})\s+(.*)$")
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

BAD_TITLES = {
    "Uhr",
    "Uhr)",
    "Uhr:",
}


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
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return lines


def cleanup_title(title):
    title = title.strip(" -–,:;")
    title = re.sub(r"^(Uhr\b[: ]*)", "", title).strip()
    title = re.sub(r"^(und\s+\w+\b)", "", title).strip()
    title = re.sub(r"^\)+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def build_event(source, title, start_time, end_time, day_of_week=None, age=None):
    return {
        "title": title,
        "start_time": normalize_time(start_time),
        "end_time": normalize_time(end_time),
        "age": age,
        "day_of_week": day_of_week,
        "district": source.get("district"),
        "address": source.get("address"),
        "source_name": source["name"],
        "source_url": source["url"],
        "venue_name": source["name"]
    }


def parse_fann(lines, source):
    events = []
    candidate_blocks = []

    current_day = None

    for line in lines:

        # detectar dia da semana
        for day in DAY_NAMES:
            if line.startswith(day):
                current_day = DAY_NAMES[day]
                line = line.replace(day, "").strip()

        match = TIME_RANGE_RE.match(line)

        if not match:
            continue

        start_time, end_time, raw_title = match.groups()

        title = cleanup_title(raw_title)

        if len(title) < 5:
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

    for line in lines:
        match = TIME_RANGE_RE.match(line)
        if not match:
            continue

        start_time, end_time, raw_title = match.groups()
        title = cleanup_title(raw_title)

        if len(title) < 5 or title in BAD_TITLES or title.lower().startswith("uhr"):
            continue

        age_match = AGE_RE.search(title)
        age = age_match.group(1) if age_match else None

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": line,
            "day_of_week": None,
            "district": source.get("district"),
            "address": source.get("address")
        })

        events.append(
            build_event(
                source=source,
                title=title,
                start_time=start_time,
                end_time=end_time,
                day_of_week=None,
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
