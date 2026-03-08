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

TIME_EVENT_RE = re.compile(r"(\d{1,2}[.:]\d{2})\s*[–-]\s*(\d{1,2}[.:]\d{2})\s+(.+)")
TIME_UHR_RE = re.compile(
    r"(\d{1,2})(?:\s*Uhr)?(?:\s*(\d{1,2}))?\s+bis\s+(\d{1,2})(?:\s*Uhr)?(?:\s*(\d{1,2}))?",
    re.IGNORECASE
)

AGE_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*(Jahr|Jahre|Monat|Monate)", re.IGNORECASE)
AGE_AB_RE = re.compile(r"ab\s+(\d+)\s*(Jahr|Jahre|Monat|Monate)", re.IGNORECASE)
AGE_TEXT_RE = re.compile(r"(\d+\s*bis\s*\d+\s*(?:jährige|jährigen|Monate|Jahre))", re.IGNORECASE)

KEEP_KEYWORDS = [
    "baby", "krabbel", "kleinkind", "eltern-kind", "familientreff",
    "babymassage", "pekip", "spielgruppe", "vater-kind", "mama-baby",
    "musik", "turnen", "familien-turnen", "klang"
]

EXCLUDE_KEYWORDS = [
    "grundschule", "schulkind", "jugendliche", "teen", "teens",
    "ab 7 jahr", "ab 7 jahren", "ab 8 jahr", "ab 8 jahren",
    "ab 9 jahr", "ab 9 jahren", "ab 10 jahr", "ab 10 jahren",
    "7 bis 9", "7-9", "8 bis 10", "8-10"
]

BAD_TITLE_STARTS = [
    "uhr", "und ", ",", ".", "start am", "erster termin",
    "darüber hinaus", "mit anmeldung", "ohne anmeldung"
]

BAD_TITLE_EXACT = {"", "uhr", "uhr)", "uhr:"}

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
    params = {"q": address, "format": "json", "limit": 1}
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

    if "start am" in lower:
        return True

    return False


def extract_age_structured(text):
    text_lower = text.lower()

    match = AGE_RANGE_RE.search(text)
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

    match = AGE_AB_RE.search(text)
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

    match = AGE_TEXT_RE.search(text)
    if match:
        raw = match.group(1).lower()
        nums = re.findall(r"\d+", raw)

        if len(nums) >= 2:
            min_raw = int(nums[0])
            max_raw = int(nums[1])

            if "monat" in raw:
                age_min = round(min_raw / 12, 2)
                age_max = round(max_raw / 12, 2)
                age_label = f"{min_raw}-{max_raw} Monate"
            else:
                age_min = min_raw
                age_max = max_raw
                age_label = f"{min_raw}-{max_raw} Jahre"

            return age_label, age_min, age_max

    if "baby" in text_lower or "krabbel" in text_lower or "pekip" in text_lower or "babymassage" in text_lower:
        return "0-1 Jahre", 0, 1

    if "kleinkind" in text_lower:
        return "1-3 Jahre", 1, 3

    if (
        "eltern-kind" in text_lower
        or "familientreff" in text_lower
        or "vater-kind" in text_lower
        or "mama-baby" in text_lower
        or "familien-turnen" in text_lower
    ):
        return None, 0, 6

    return None, None, None


def is_in_scope_0_6(text, age_min, age_max):
    lower = text.lower()

    for keyword in EXCLUDE_KEYWORDS:
        if keyword in lower:
            return False

    if age_min is not None and age_min > 6:
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
    if not start_time or not end_time or not title:
        return None

    lat, lon = geocode(source["address"])

    return {
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
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


def parse_fann(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    start_index = None
    end_index = None

    for i, line in enumerate(lines):
        if "Angebote im" in line:
            start_index = i
            break

    agenda_lines = lines
    if start_index is not None:
        for i in range(start_index + 1, len(lines)):
            if (
                lines[i].startswith("Das FaNN ist ein Ort")
                or lines[i].startswith("Beratungsangebote")
                or lines[i].startswith("Kontakt")
            ):
                end_index = i
                break

        if end_index is None:
            end_index = min(len(lines), start_index + 180)

        agenda_lines = lines[start_index:end_index]

    candidate_blocks = []
    events = []
    current_day = None

    for line in agenda_lines:
        stripped = line.strip()

        if stripped in DAY_NAMES:
            current_day = stripped
            continue

        for day in DAY_NAMES:
            if stripped.startswith(day + " "):
                current_day = day
                stripped = stripped[len(day):].strip()
                break

        match = TIME_EVENT_RE.match(stripped)
        if not match:
            continue

        start_time, end_time, title = match.groups()
        title = cleanup_title(title)

        if looks_like_bad_title(title):
            continue

        age_label, age_min, age_max = extract_age_structured(title)

        if not is_in_scope_0_6(title, age_min, age_max):
            continue

        candidate_blocks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "text": stripped,
            "day_of_week": current_day,
            "district": source["district"],
            "address": source["address"]
        })

        event = build_event(
            source=source,
            title=title,
            start_time=normalize_time(start_time),
            end_time=normalize_time(end_time),
            day_of_week=current_day,
            age_label=age_label,
            age_min=age_min,
            age_max=age_max
        )
        if event:
            events.append(event)

    return candidate_blocks, events


def format_uhr_time(hour, minute):
    h = int(hour)
    m = int(minute) if minute else 0
    return f"{h:02d}:{m:02d}"


def parse_adalbert(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    start_index = None
    end_index = None

    for i, line in enumerate(lines):
        if "Kurse und Angebote im Familien-Zentrum" in line:
            start_index = i
            break

    section_lines = lines
    if start_index is not None:
        for i in range(start_index + 1, len(lines)):
            if lines[i].startswith("Wo ist das Familien-Zentrum?"):
                end_index = i
                break

        if end_index is None:
            end_index = len(lines)

        section_lines = lines[start_index:end_index]

    candidate_blocks = []
    events = []
    current_day = None
    current_title = None
    current_desc = None

    for line in section_lines:
        stripped = line.strip()

        if stripped in DAY_NAMES:
            current_day = stripped
            current_title = None
            current_desc = None
            continue

        stripped = re.sub(r"^\d+\.\s*", "", stripped).strip()

        time_match = TIME_UHR_RE.search(stripped)
        if time_match and current_title:
            start_hour, start_min, end_hour, end_min = time_match.groups()
            start_time = format_uhr_time(start_hour, start_min)
            end_time = format_uhr_time(end_hour, end_min)

            combined_text = current_title
            if current_desc:
                combined_text += " " + current_desc

            age_label, age_min, age_max = extract_age_structured(combined_text)

            if is_in_scope_0_6(combined_text, age_min, age_max):
                candidate_blocks.append({
                    "source_name": source["name"],
                    "source_url": source["url"],
                    "text": f"{current_title} | {current_desc or ''} | {stripped}",
                    "day_of_week": current_day,
                    "district": source["district"],
                    "address": source["address"]
                })

                event = build_event(
                    source=source,
                    title=cleanup_title(current_title),
                    start_time=start_time,
                    end_time=end_time,
                    day_of_week=current_day,
                    age_label=age_label,
                    age_min=age_min,
                    age_max=age_max
                )
                if event:
                    events.append(event)

            current_title = None
            current_desc = None
            continue

        lower = stripped.lower()
        if (
            "link zur buchung" in lower
            or "ohne anmeldung" in lower
            or "mit anmeldung" in lower
            or "offenes angebot" in lower
            or "kostenpflichtig" in lower
            or "online" in lower
        ):
            continue

        if current_title is None:
            current_title = stripped.rstrip(",")
        elif current_desc is None:
            current_desc = stripped.rstrip(",")

    return candidate_blocks, events


def parse_source(source):
    parser = source.get("parser", "fann")

    if parser == "adalbert":
        return parse_adalbert(source)

    return parse_fann(source)


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
            print(f"error in source {source['name']}: {e}")
            continue

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
