from .base import (
    DAY_NAMES,
    TIME_EVENT_RE,
    fetch_html,
    extract_lines,
    cleanup_title,
    looks_like_bad_title,
    extract_age_structured,
    is_in_scope_0_6,
    build_event,
    normalize_time,
)


def parse(source: dict) -> list[dict]:
    html = fetch_html(source["url"])
    lines = extract_lines(html)

    events = []
    current_day = None

    for line in lines:
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

        event = build_event(
            source=source,
            title=title,
            start_time=normalize_time(start_time),
            end_time=normalize_time(end_time),
            day_of_week=current_day,
            age_label=age_label,
            age_min=age_min,
            age_max=age_max,
            raw_text=line,
        )

        if event:
            events.append(event)

    return events
