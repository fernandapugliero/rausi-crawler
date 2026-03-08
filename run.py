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

AGE_RANGE_RE = re.compile(
    r"(\d+)\s*[-–]\s*(\d+)\s*(Jahr|Jahre|Monat|Monate)",
    re.IGNORECASE
)

AGE_AB_RE = re.compile(
    r"ab\s+(\d+)\s*(Jahr|Jahre|Monat|Monate)",
    re.IGNORECASE
)

KEEP_KEYWORDS = [
    "baby",
    "krabbel",
    "kleinkind",
    "eltern-kind",
    "familientreff",
    "babymassage",
    "pekip",
    "spielgruppe",
    "vater-kind",
    "mama-baby",
    "musik",
    "turnen",
]

EXCLUDE_KEYWORDS = [
    "grundschule",
    "schulkind",
    "jugendliche",
    "teen",
    "teens",
    "ab 7 jahr",
    "ab 7 jahren",
    "ab 8 jahr",
    "ab 8 jahren",
    "ab 9 jahr",
    "ab 9 jahren",
    "ab 10 jahr",
    "ab 10 jahren",
]

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

        if stripped.startswith(day + ":"):
            return day

    return None


def remove_day_prefix(line):
    stripped = line.strip()

    for day in DAY_NAMES:
        if stripped == day:
            return ""
        if stripped.startswith(day + " "):
            return stripped[len(day):].strip()
        if stripped.startswith(day + ":"):
            return stripped[len(day) + 1:].strip()

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

    if "start am" in title:
        return True

    return False


def extract_age_structured(title):
    """
    Returns:
    age_label, age_min, age_max
    Units are normalized to years.
    Months are converted to fractions of years.
    """
    title_lower = title.lower()

    match = AGE_RANGE_RE.search(title)
    if match:
        min_raw = int(match.group(1))
        max_raw = int(match.group(2))
        unit = match.group(3).lower()

        if "monat" in unit:
            age_min = round(min_raw / 12, 2)
            age_max = round(max_raw / 12, 2)
            age_label = f"{min_raw}-{max_raw} Monate"
        else:
            age_min = min_raw
            age_max = max_raw
            age_label = f"{min_raw}-{max_raw} Jahre"

        return age_label, age_min, age_max

    match = AGE_AB_RE.search(title)
    if match:
        min_raw = int(match.group(1))
        unit = match.group(2).lower()

        if "monat" in unit:
            age_min = round(min_raw / 12, 2)
            age_max = 6
            age_label = f"ab {min_raw} Monate"
        else:
            age_min = min_raw
            age_max = 6
            age_label = f"ab {min_raw} Jahre"

        return age_label, age_min, age_max

    if "baby" in title_lower or "krabbel" in title_lower or "pekip" in title_lower or "babymassage" in title_lower:
        return "0-1 Jahr", 0, 1

    if "kleinkind" in title_lower:
        return "1-3 Jahre", 1, 3

    if "eltern-kind" in title_lower or "familientreff" in title_lower or "vater-kind" in title_lower or "mama-baby" in title_lower:
        return None, 0, 6

    return None, None, None


def is_in_scope_0_6(title, age_min, age_max):
    lower = title.lower()

    for keyword in EXCLUDE_KEYWORDS:
        if keyword in lower:
            return False

    if age_min is not None:
        if age_min > 6:
            return False

    if age_max is not None:
        if age_min is not None and age_min <= 6:
            return True
        if age_max <= 6:
            return True
        return False

    for keyword in KEEP_KEYWORDS:
        if keyword in lower:
            return True

    return False


def build_event(source, title, start_time, end_time, day_of_week=None, age_label=None, age_min=None, age_max=None):
    lat, lon = geocode(source["address"])

    return {
        "title": title,
        "start_time": normalize_time(start_time),
        "end_time": normalize_time(end_time),
        "age": age_label,
        "age_min": age_min,
        "age_max": age_max,
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
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    # tenta focar na seção principal da agenda para as páginas da Jugendwohnen
    start_index = None
    end_index = None

    for i, line in enumerate(lines):
        if "Angebote im" in line or "Angebote im FaNN" in line:
            start_index = i
            break

    if start_index is None:
        agenda_lines = lines
    else:
        for i in range(start_index + 1, len(lines)):
            if (
                lines[i].startswith("Das FaNN ist ein Ort")
                or lines[i].startswith("Beratungsangebote")
                or lines[i].startswith("Kontakt")
            ):
                end_index = i
                break

        if end_index is None:
            end_index = min(len(lines), start_index + 150)

        agenda_lines = lines[start_index:end_index]

    candidate_blocks = []
    events = []
    current_day = None

    for line in agenda_lines:
        explicit_day = find_explicit_day_in_line(line)
        if explicit_day:
            current_day = explicit_day
            line = remove_day_prefix(line)

            if not line:
                continue

        match = TIME_EVENT_RE.match(line)
        if not match:
            continue

        start_time, end_time, title = match.groups()
        title = cleanup_title(title)

        if looks_like_bad_title(title):
            continue

        if "start am" in title.lower():
            continue

        age_label, age_min, age_max = extract_age_structured(title)

        if not is_in_scope_0_6(title, age_min, age_max):
            continue

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
                age_label=age_label,
                age_min=age_min,
                age_max=age_max
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
