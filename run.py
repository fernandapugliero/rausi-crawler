import json
from parsers.fann import parse as parse_fann
from parsers.adalbert import parse as parse_adalbert
from parsers.fallback import parse as parse_fallback

PARSERS = {
    "fann": parse_fann,
    "adalbert": parse_adalbert,
    "fallback": parse_fallback,
}


def dedupe(events: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for event in events:
        key = (
            str(event.get("source_id", "")).strip().lower(),
            str(event.get("title", "")).strip().lower(),
            event.get("start_time"),
            event.get("end_time"),
            event.get("day_of_week"),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    all_events = []
    errors = []
    source_stats = []

    for source in sources:
        parser_name = source.get("parser", "fallback")
        parser = PARSERS.get(parser_name, parse_fallback)

        try:
            events = parser(source)
            all_events.extend(events)
            source_stats.append({
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "parser": parser_name,
                "event_count": len(events),
                "status": "ok",
            })
            print(f"{source.get('name')}: {len(events)} events")
        except Exception as e:
            errors.append({
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "parser": parser_name,
                "error": str(e),
            })
            source_stats.append({
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "parser": parser_name,
                "event_count": 0,
                "status": "error",
            })
            print(f"ERROR in {source.get('name')}: {e}")

    all_events = dedupe(all_events)

    output = {
        "events": all_events,
        "errors": errors,
        "source_stats": source_stats,
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"saved {len(all_events)} events total")


if __name__ == "__main__":
    main()
