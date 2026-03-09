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

AGE_RANGE_RE = re.compile(
    r"(\d+)\s*[-–]\s*(\d+)\s*(Jahr|Jahre|Monat|Monate)",
    re.IGNORECASE
)

AGE_AB_RE = re.compile(
    r"ab\s+(\d+)\s*(Jahr|Jahre|Monat|Monate)",
    re.IGNORECASE
)

AGE_TEXT_RE = re.compile(
    r"(\d+\s*bis\s*\d+\s*(?:jährige|jährigen|Monate|Jahre))",
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
    "familien-turnen",
    "klang",
    "lauf, spiel und spaß",
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
    "7 bis 9",
    "7-9",
    "8 bis 10",
    "8-10",
]

BAD_TITLE_STARTS = [
    "uhr",
    "und ",
    ",",
    ".",
    "start am",
    "erster termin",
    "darüber hinaus",
    "mit anmeldung",
    "ohne anmeldung",
]

BAD_TITLE_EXACT = {
    "",
    "uhr",
    "uhr)",
    "uhr:",
}

_geocode_cache = {}


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "RausiCrawler/0.1"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def extract_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    return [line for line in lines if line]


def normalize_time(value: str) -> str:
    return value.replace(".", ":")


def format_uhr_time(hour: str, minute: str | None) -> str:
    h = int(hour)
    m = int(minute) if minute else 0
    return f"{h:02d}:{m:02d}"


def geocode(address: str | None) -> tuple[float | None, float | None]:
    if not address:
        return None, None

    if address in _geocode_cache:
        return _geocode_cache[address]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "RausiCrawler/0.1"}

    try:
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


def cleanup_title(title: str) -> str:
    title = title.strip(" ,:-–")
    title = re.sub(r"^Uhr\b[: ]*", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^\)+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def looks_like_bad_title(title: str) -> bool:
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


def extract_age_structured(text: str) -> tuple[str | None, float | None, float | None]:
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


def is_in_scope_0_6(text: str, age_min: float | None, age_max: float | None) -> bool:
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


def build_event(
    source: dict,
    title: str,
    start_time: str,
    end_time: str,
    day_of_week: str | None = None,
    age_label: str | None = None,
    age_min: float | None = None,
    age_max: float | None = None,
    raw_text: str | None = None,
) -> dict | None:
    if not title or not start_time or not end_time:
        return None

    lat, lon = geocode(source.get("address"))

    return {
        "source_id": source.get("id"),
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "age": age_label,
        "age_min": age_min,
        "age_max": age_max,
        "day_of_week": day_of_week,
        "district": source.get("district"),
        "address": source.get("address"),
        "latitude": lat,
        "longitude": lon,
        "source_name": source.get("name"),
        "source_url": source.get("url"),
        "venue_name": source.get("name"),
        "raw_text": raw_text,
    }
