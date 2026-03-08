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

KEEP_KEYWORDS = [
    "baby","krabbel","kleinkind","eltern-kind","familientreff",
    "babymassage","pekip","spielgruppe","vater-kind","mama-baby",
    "musik","turnen","familien"
]

EXCLUDE_KEYWORDS = [
    "grundschule","schulkind","jugendliche",
    "ab 7","ab 8","ab 9","ab 10",
    "7 bis","8 bis","9 bis"
]

geocode_cache = {}


def fetch_html(url):
    headers = {"User-Agent": "RausiCrawler/0.1"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def clean_text(text):
    return " ".join(text.split()).strip()


def normalize_time(v):
    return v.replace(".", ":")


def geocode(address):

    if address in geocode_cache:
        return geocode_cache[address]

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }

    try:

        r = requests.get(url, params=params, headers={"User-Agent":"RausiCrawler"})
        data = r.json()

        if not data:
            geocode_cache[address] = (None,None)
            return None,None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])

        geocode_cache[address] = (lat,lon)

        time.sleep(1)

        return lat,lon

    except:
        return None,None


def cleanup_title(title):

    title = title.strip(" ,:-–")

    title = re.sub(r"\s+"," ",title)

    return title


def extract_age(text):

    m = AGE_RANGE_RE.search(text)

    if m:
        return m.group(0)

    return None


def is_in_scope(text):

    lower = text.lower()

    for k in EXCLUDE_KEYWORDS:
        if k in lower:
            return False

    for k in KEEP_KEYWORDS:
        if k in lower:
            return True

    return False


def build_event(source,title,start,end,day,age):

    if not title or not start or not end:
        return None

    lat,lon = geocode(source["address"])

    return {

        "title": title,

        "start_time": start,

        "end_time": end,

        "age": age,

        "day_of_week": day,

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

    soup = BeautifulSoup(html,"html.parser")

    text = soup.get_text("\n")

    lines = [clean_text(l) for l in text.split("\n") if clean_text(l)]

    events = []

    candidate_blocks = []

    current_day = None

    for line in lines:

        if line in DAY_NAMES:
            current_day = line
            continue

        for d in DAY_NAMES:
            if line.startswith(d+" "):
                current_day = d
                line = line[len(d):].strip()

        m = TIME_EVENT_RE.match(line)

        if not m:
            continue

        start,end,title = m.groups()

        title = cleanup_title(title)

        if not is_in_scope(title):
            continue

        age = extract_age(title)

        candidate_blocks.append({

            "source_name":source["name"],
            "text":line,
            "day_of_week":current_day

        })

        event = build_event(

            source,

            title,

            normalize_time(start),

            normalize_time(end),

            current_day,

            age

        )

        if event:
            events.append(event)

    return candidate_blocks,events


def parse_adalbert(source):

    html = fetch_html(source["url"])

    soup = BeautifulSoup(html,"html.parser")

    text = soup.get_text("\n")

    lines = [clean_text(l) for l in text.split("\n") if clean_text(l)]

    events = []

    candidate_blocks = []

    current_day = None
    current_title = None

    for line in lines:

        if line in DAY_NAMES:
            current_day = line
            continue

        m = TIME_UHR_RE.search(line)

        if m and current_title:

            sh,sm,eh,em = m.groups()

            start = f"{int(sh):02d}:{int(sm) if sm else 0:02d}"
            end = f"{int(eh):02d}:{int(em) if em else 0:02d}"

            if not is_in_scope(current_title):
                current_title = None
                continue

            age = extract_age(current_title)

            event = build_event(

                source,

                current_title,

                start,

                end,

                current_day,

                age

            )

            if event:
                events.append(event)

            current_title = None
            continue

        if not current_title:
            current_title = line

    return candidate_blocks,events


def parse_source(source):

    if "adalbert" in source["url"]:
        return parse_adalbert(source)

    return parse_fann(source)


def dedupe(events):

    seen=set()
    result=[]

    for e in events:

        key=(

            e["title"].lower(),

            e["start_time"],

            e["day_of_week"],

            e["venue_name"]

        )

        if key in seen:
            continue

        seen.add(key)

        result.append(e)

    return result


def main():

    with open("sources.json","r",encoding="utf-8") as f:

        sources=json.load(f)

    all_events=[]
    all_candidates=[]

    for s in sources:

        print("Crawling:",s["name"])

        try:

            c,e=parse_source(s)

            print("found",len(e),"events")

            all_candidates.extend(c)

            all_events.extend(e)

        except Exception as err:

            print("error:",err)

    all_events=dedupe(all_events)

    output={

        "events":all_events,

        "candidate_blocks":all_candidates

    }

    with open("output.json","w",encoding="utf-8") as f:

        json.dump(output,f,ensure_ascii=False,indent=2)

    print("saved",len(all_events),"events")


if __name__=="__main__":

    main()
