import re
from .base import (
    DAY_NAMES,
    TIME_UHR_RE,
    fetch_html,
    extract_lines,
    cleanup_title,
    extract_age_structured,
    is_in_scope_0_6,
    build_event,
    format_uhr_time,
)


def parse(source: dict) -> list[dict]:
    html = fetch_html(source["url"])
    lines = extract_lines(html)

    events = []
    current_day = None
    current_title = None
    current_desc = None

    for line in lines:
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
                event = build_event(
                    source=source,
                    title=cleanup_title(current_title),
                    start_time=start_time,
                    end_time=end_time,
                    day_of_week=current_day,
                    age_label=age_label,
                    age_min=age_min,
                    age_max=age_max,
                    raw_text=f"{current_title} | {current_desc or ''} | {stripped}",
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

    return events
