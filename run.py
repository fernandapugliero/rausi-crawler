import json
import requests
from bs4 import BeautifulSoup


def fetch_html(url):
    headers = {
        "User-Agent": "RausiCrawler/0.1"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def extract_blocks(html, source):
    soup = BeautifulSoup(html, "html.parser")

    results = []
    elements = soup.find_all(["h1", "h2", "h3", "p", "li"])

    for el in elements:
        text = " ".join(el.get_text(" ", strip=True).split())

        if len(text) < 20:
            continue

        results.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "tag": el.name,
            "text": text
        })

    return results[:50]


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    all_results = []

    for source in sources:
        print(f"Fetching: {source['url']}")

        try:
            html = fetch_html(source["url"])
            blocks = extract_blocks(html, source)
            print(f"Found {len(blocks)} blocks")

            all_results.extend(blocks)

        except Exception as e:
            print(f"Error: {e}")

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_results)} items to output.json")


if __name__ == "__main__":
    main()
