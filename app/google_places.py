# app/google_places.py

import re
import urllib.parse
import httpx
from playwright.async_api import async_playwright

GOOGLE_API_KEY = "AIzaSyCjWqqKJ5CF3PuTDq6uaG8TDZvdl-Z9EuM"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


async def search_restaurants(query: str) -> list[dict]:
    """Search for restaurants using Google Places Text Search API."""
    print(f"\n🔍 Google Places: Searching '{query}'...")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location",
        "Origin": "https://dev.reelo.io",
        "Referer": "https://dev.reelo.io/",
    }

    payload = {"textQuery": query}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(PLACES_URL, json=payload, headers=headers)

        if response.status_code != 200:
            print(f"⚠️ Google Places API error: {response.status_code} - {response.text[:200]}")
            return []

        data = response.json()
        places = data.get("places", [])
        print(f"📍 Google Places returned {len(places)} results")

        results = []
        for place in places:
            results.append({
                "place_id": place.get("id", ""),
                "name": place.get("displayName", {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "lat": place.get("location", {}).get("latitude"),
                "lng": place.get("location", {}).get("longitude"),
                "rating": None,
                "total_ratings": None,
            })

        print(f"✅ Found {len(results)} results")
        return results


async def extract_swiggy_link(place_id: str, restaurant_name: str = "", address: str = "") -> dict:
    """
    Find Swiggy URL for a restaurant using Google Search.

    Instead of scraping Google Maps (which has dynamic lazy-loaded content),
    we search Google for: "restaurant name" "city" site:swiggy.com

    This is faster and more reliable.
    """
    print(f"\n🔍 Finding Swiggy link for: {restaurant_name}")

    result = {
        "swiggy_url": None,
        "restaurant_id": None,
        "zomato_url": None,
    }

    # Extract city from address (last part before country/pin)
    city = _extract_city(address)
    print(f"   City from address: {city}")

    # Build search queries to try (most specific to least)
    search_queries = []

    # Clean restaurant name for search
    clean_name = restaurant_name.replace(" - ", " ").replace(" & ", " ")

    if city:
        search_queries.append(f'"{clean_name}" "{city}" site:swiggy.com')
        search_queries.append(f'{clean_name} {city} swiggy')
    search_queries.append(f'"{clean_name}" site:swiggy.com')
    search_queries.append(f'{clean_name} swiggy restaurant')

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            for query in search_queries:
                print(f"\n🔎 Google Search: {query}")

                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                await page.goto(search_url, timeout=20000)
                await page.wait_for_timeout(2000)

                # Handle consent
                try:
                    for text in ["Accept all", "Accept All", "Reject all"]:
                        btn = page.locator(f"button:has-text('{text}')").first
                        if await btn.count() > 0:
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                except:
                    pass

                # Extract all links from search results
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.href)",
                )

                for href in links:
                    # Direct Swiggy URL in search results
                    if "swiggy.com" in href and "rest" in href:
                        clean = _clean_google_redirect(href)
                        if "rest" in clean:
                            result["swiggy_url"] = clean
                            print(f"✅ Found Swiggy URL: {clean[:100]}")
                            break

                    # Google redirect URL containing Swiggy
                    if "google.com/url" in href and "swiggy" in href:
                        clean = _clean_google_redirect(href)
                        if "swiggy.com" in clean:
                            result["swiggy_url"] = clean
                            print(f"✅ Found Swiggy URL (redirect): {clean[:100]}")
                            break

                if result["swiggy_url"]:
                    break

                # Also check HTML for encoded Swiggy URLs
                html = await page.content()
                swiggy_matches = re.findall(
                    r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&]+rest\d+[^\s"\'<>&]*',
                    html,
                )
                if swiggy_matches:
                    result["swiggy_url"] = urllib.parse.unquote(swiggy_matches[0])
                    print(f"✅ Found Swiggy in search HTML: {result['swiggy_url'][:100]}")
                    break

                # Check Zomato too
                for href in links:
                    if "zomato.com" in href and not result["zomato_url"]:
                        result["zomato_url"] = _clean_google_redirect(href)

            # Extract restaurant ID from Swiggy URL
            if result["swiggy_url"]:
                match = re.search(r"rest(\d+)", result["swiggy_url"])
                if match:
                    result["restaurant_id"] = match.group(1)
                    print(f"🆔 Restaurant ID: {result['restaurant_id']}")
            else:
                print("⚠️ No Swiggy link found in Google Search results")

        except Exception as e:
            print(f"❌ Error: {e}")

        await browser.close()

    return result


def _extract_city(address: str) -> str:
    """Extract city name from a Google address string."""
    if not address:
        return ""

    # Google addresses are usually: "Street, Area, City, State PIN, Country"
    parts = [p.strip() for p in address.split(",")]

    # Remove pin code and country
    cleaned = []
    for part in parts:
        # Skip if it's a pin code (6 digits for India)
        if re.match(r"^\d{5,6}$", part.strip()):
            continue
        # Skip if it's "India"
        if part.strip().lower() == "india":
            continue
        # Skip state + pin like "Maharashtra 400049"
        if re.match(r"^[A-Za-z\s]+\d{5,6}$", part.strip()):
            cleaned.append(re.sub(r"\d+", "", part).strip())
            continue
        cleaned.append(part)

    # City is usually the 3rd-to-last or 2nd-to-last part
    if len(cleaned) >= 3:
        return cleaned[-2]  # "City" in "Area, City, State"
    elif len(cleaned) >= 2:
        return cleaned[-1]
    elif cleaned:
        return cleaned[0]

    return ""


def _clean_google_redirect(url: str) -> str:
    """Extract actual URL from Google's redirect wrapper."""
    if "google.com/url" in url:
        match = re.search(r'[?&]q=(https?[^&]+)', url)
        if match:
            return urllib.parse.unquote(match.group(1))
    return url