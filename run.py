import json
import re
import requests
from bs4 import BeautifulSoup


TIME_RANGE_RE = re.compile(r"(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})")
AGE_RE = re.compile(r"(\d+\s*[-–]\s*\d+\s*Jahr(?:e)?)", re.IGNORECASE)

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

DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def fetch_html(url):
    headers = {"User-Agent": "RausiCrawler/0.1"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def clean_text(text):
    return " ".join(text.split()).strip()


def normalize_time(value):
    return value.replace(".", ":")


def looks_like_noise(text):
    if len(text) < 12:
        return True

    for bad in BAD_TEXT_PARTS:
        if bad.lower() in text.lower():
            return True

    return False


def infer_day_from_text(text):
    lower = text.lower()

    if "montag" in lower:
        return "Montag"
    if "dienstag" in lower:
        return "Dienstag"
    if "mittwoch" in lower:
        return "Mittwoch"
    if "donnerstag" in lower:
        return "Donnerstag"
    if "freitag" in lower:
        return "Freitag"
    if "samstag" in lower:
        return "Samstag"
    if "sonntag" in lower:
        return "Sonntag"

    return None


def extract_candidate_blocks(html, source):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    elements = soup.find_all(["h1", "h2", "h3", "h4", "p", "li"])

    current_day = None

    for el in elements:
        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue

        inferred_day = infer_day_from_text(text)
        if inferred_day and len(text) <= 20:
            current_day = inferred_day
            continue

        if looks_like_noise(text):
            continue

        has_time = bool(TIME_RANGE_RE.search(text))
        has_age = bool(AGE_RE.search(text))

        if has_time or has_age or "anmeldung" in text.lower() or "baby" in text.lower() or "krabbel" in text.lower():
            results.append({
                "source_name": source["name"],
                "source_url": source["url"],
                "tag": el.name,
                "text": text,
                "has_time": has_time,
                "has_age": has_age,
                "day_of_week": current_day,
                "district": source.get("district"),
                "address": source.get("address")
            })

    return results


def cleanup_title(title):
    title = title.strip(" -–,:;")
    title = re.sub(r"^(Uhr\b[: ]*)", "", title).strip()
    title = re.sub(r"^(und\s+\w+\b)", "", title).strip()
    title = re.sub(r"^\)+", "", title).strip()
    return title


def split_block_into_events(block, source):
    text = block["text"]
    matches = list(TIME_RANGE_RE.finditer(text))
    events = []

    if not matches:
        return events

    for i, match in enumerate(matches):
        start_index = match.start()
        end_index = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        chunk = text[start_index:end_index].strip(" •-–,;")
        start_time = normalize_time(match.group(1))
        end_time = normalize_time(match.group(2))

        title = TIME_RANGE_RE.sub("", chunk, count=1).strip(" -–,:;")
        title = cleanup_title(title)

        age_match = AGE_RE.search(chunk)
        age = age_match.group(1) if age_match else None

        if len(title) < 5:
            continue
        if title.lower().startswith("uhr"):
            continue

        events.append({
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "age": age,
            "day_of_week": block.get("day_of_week"),
            "district": source.get("district"),
            "address": source.get("address"),
            "source_name": source["name"],
            "source_url": source["url"],
            "venue_name": source["name"]
        })

    return events


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

    all_blocks = []
    all_events = []

    for source in sources:
        print(f"Fetching: {source['url']}")

        try:
            html = fetch_html(source["url"])
            blocks = extract_candidate_blocks(html, source)
            print(f"Found {len(blocks)} candidate blocks")

            all_blocks.extend(blocks)

            for block in blocks:
                events = split_block_into_events(block, source)
                all_events.extend(events)

        except Exception as e:
            print(f"Error: {e}")

    all_events = dedupe_events(all_events)

    output = {
        "candidate_blocks": all_blocks,
        "events": all_events
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_events)} events to output.json")


if __name__ == "__main__":
    main()
