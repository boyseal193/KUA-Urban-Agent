import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def load_env_value(key: str):
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    if not os.path.exists(env_path):
        return None

    with open(env_path, "r") as file:
        for line in file:
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().replace('"', "").replace("'", "")

    return None


BRIGHTDATA_API_KEY = load_env_value("BRIGHTDATA_API_KEY") or "62cbbb39-9e0f-4cd8-9012-98313185296e"
BRIGHTDATA_ZONE = load_env_value("BRIGHTDATA_ZONE") or "web_property_finder"


def fetch_html(url: str):
    last_error = None

    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.brightdata.com/request",
                headers={
                    "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "zone": BRIGHTDATA_ZONE,
                    "url": url,
                    "format": "raw",
                    "country": "es"
                },
                timeout=120,
            )

            if response.status_code == 200:
                return response.text

            last_error = f"Bright Data error {response.status_code}: {response.text[:300]}"
            time.sleep(5)

        except Exception as e:
            last_error = str(e)
            time.sleep(5)

    raise Exception(last_error)


def clean_listing_text(text: str):
    remove_phrases = [
        "Skip to main content",
        "Save to favourites",
        "Discard",
        "Share",
        "Add your note",
        "Your note",
        "Available in:",
        "Other languages",
        "View map",
    ]

    for phrase in remove_phrases:
        text = text.replace(phrase, " ")

    text = re.sub(
        r"Español|Català|English|Français|Deutsch|Italiano|Português|Dansk|Suomi|Norsk|Nederlands|Polski|Română|русский|Svenska|Ελληνικά|中文|Українська",
        " ",
        text
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def scrape_listing_text(url: str):
    if not BRIGHTDATA_API_KEY:
        return {
            "success": False,
            "error": "BRIGHTDATA_API_KEY not found",
            "raw_text": None
        }

    try:
        html = fetch_html(url)

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        clean_text = clean_listing_text(text)

        return {
            "success": True,
            "url": url,
            "raw_text": clean_text[:15000],
            "html_preview": html[:1000]
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "raw_text": None
        }


def scrape_idealista_search_urls(search_url: str, limit: int = 10):
    if not BRIGHTDATA_API_KEY:
        return {
            "success": False,
            "error": "BRIGHTDATA_API_KEY not found",
            "urls": []
        }

    try:
        html = fetch_html(search_url)
        soup = BeautifulSoup(html, "html.parser")

        urls = []

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if "/inmueble/" in href:
                full_url = urljoin("https://www.idealista.com", href)
                clean_url = full_url.split("?")[0]

                if clean_url not in urls:
                    urls.append(clean_url)

            if len(urls) >= limit:
                break

        return {
            "success": True,
            "search_url": search_url,
            "count": len(urls),
            "urls": urls
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "urls": []
        }