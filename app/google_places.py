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
    Find Swiggy URL for a restaurant.

    Strategy 1a: DuckDuckGo HTML search (no browser, no captcha, fast)
    Strategy 1b: DuckDuckGo with shorter name
    Strategy 1c: Direct Swiggy search API via browser

    Returns dict with swiggy_url, restaurant_id, zomato_url.
    """
    print(f"\n🔍 Finding Swiggy link for: {restaurant_name}")

    result = {
        "swiggy_url": None,
        "restaurant_id": None,
        "zomato_url": None,
    }

    city = _extract_city(address)
    print(f"   City from address: {city}")

    # Build name variants to search
    clean_name = restaurant_name.replace(" - ", " ").replace(" & ", " and ")

    # Short name: remove common suffixes
    short_name = restaurant_name
    for suffix in [" - Kitchen & Bar", " - Kitchen and Bar", " - Bar & Kitchen",
                   " - Restaurant & Bar", " - Restaurant", " - Cafe", " - Bar",
                   " Restaurant", " Cafe", " Bar", " Kitchen"]:
        if short_name.lower().endswith(suffix.lower()):
            short_name = short_name[:len(short_name) - len(suffix)].strip()
            break

    print(f"   Full name: {restaurant_name}")
    print(f"   Short name: {short_name}")

    # ── Strategy 1a: DuckDuckGo search (no browser needed!) ──
    search_queries = []
    if city:
        search_queries.append(f"{clean_name} {city} site:swiggy.com")
        search_queries.append(f"{short_name} {city} site:swiggy.com")
        search_queries.append(f"{short_name} {city} swiggy")
    search_queries.append(f"{clean_name} site:swiggy.com")
    search_queries.append(f"{short_name} swiggy")

    async with httpx.AsyncClient(timeout=15.0) as client:
        for query in search_queries:
            print(f"\n🔎 DuckDuckGo: {query}")

            try:
                ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                response = await client.get(
                    ddg_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                    },
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    print(f"   ⚠️ DuckDuckGo returned {response.status_code}")
                    continue

                html = response.text

                # Find Swiggy URLs in DuckDuckGo results
                # DDG wraps links in redirects: //duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.swiggy.com%2F...
                uddg_matches = re.findall(r'uddg=(https?[^&"]+swiggy\.com[^&"]*)', html)
                for match in uddg_matches:
                    decoded = urllib.parse.unquote(match)
                    if "rest" in decoded and "/city/" in decoded:
                        result["swiggy_url"] = decoded
                        print(f"✅ Found Swiggy (DDG redirect): {decoded[:100]}")
                        break

                if result["swiggy_url"]:
                    break

                # Also check for direct swiggy.com URLs in the HTML
                direct_matches = re.findall(
                    r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&]+rest\d+[^\s"\'<>&]*',
                    html,
                )
                if direct_matches:
                    result["swiggy_url"] = urllib.parse.unquote(direct_matches[0])
                    print(f"✅ Found Swiggy (DDG direct): {result['swiggy_url'][:100]}")
                    break

                # Check for any swiggy.com link
                any_swiggy = re.findall(
                    r'https?://(?:www\.)?swiggy\.com/[^\s"\'<>&]+rest\d+',
                    html,
                )
                if any_swiggy:
                    result["swiggy_url"] = urllib.parse.unquote(any_swiggy[0])
                    print(f"✅ Found Swiggy (DDG any): {result['swiggy_url'][:100]}")
                    break

            except Exception as e:
                print(f"   ⚠️ DuckDuckGo error: {e}")
                continue

    # ── Strategy 1b: Try Bing search if DDG failed ──
    if not result["swiggy_url"]:
        print("\n🔎 Trying Bing search...")

        bing_queries = []
        if city:
            bing_queries.append(f"{short_name} {city} site:swiggy.com")
        bing_queries.append(f"{short_name} swiggy site:swiggy.com")

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query in bing_queries:
                try:
                    bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
                    response = await client.get(
                        bing_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                        },
                        follow_redirects=True,
                    )

                    if response.status_code == 200:
                        html = response.text
                        swiggy_matches = re.findall(
                            r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&]+rest\d+[^\s"\'<>&]*',
                            html,
                        )
                        if swiggy_matches:
                            result["swiggy_url"] = urllib.parse.unquote(swiggy_matches[0])
                            print(f"✅ Found Swiggy (Bing): {result['swiggy_url'][:100]}")
                            break
                except Exception as e:
                    print(f"   ⚠️ Bing error: {e}")
                    continue

    # ── Extract restaurant ID ──
    if result["swiggy_url"]:
        match = re.search(r"rest(\d+)", result["swiggy_url"])
        if match:
            result["restaurant_id"] = match.group(1)
            print(f"🆔 Restaurant ID: {result['restaurant_id']}")
    else:
        print("⚠️ No Swiggy link found via search engines")

    return result


def _extract_city(address: str) -> str:
    """Extract city name from a Google address string."""
    if not address:
        return ""

    parts = [p.strip() for p in address.split(",")]

    cleaned = []
    for part in parts:
        if re.match(r"^\d{5,6}$", part.strip()):
            continue
        if part.strip().lower() == "india":
            continue
        if re.match(r"^[A-Za-z\s]+\d{5,6}$", part.strip()):
            cleaned.append(re.sub(r"\d+", "", part).strip())
            continue
        cleaned.append(part)

    if len(cleaned) >= 3:
        return cleaned[-2]
    elif len(cleaned) >= 2:
        return cleaned[-1]
    elif cleaned:
        return cleaned[0]

    return ""
