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
    Find Swiggy URL for a restaurant using DuckDuckGo search inside Playwright.

    httpx requests to search engines are blocked on Render's network,
    so we use a real browser to search DuckDuckGo instead.
    """
    print(f"\n🔍 Finding Swiggy link for: {restaurant_name}")

    result = {
        "swiggy_url": None,
        "restaurant_id": None,
        "zomato_url": None,
    }

    city = _extract_city(address)
    print(f"   City from address: {city}")

    # Build name variants
    clean_name = restaurant_name.replace(" - ", " ").replace(" & ", " and ")

    # Short name: remove common suffixes
    short_name = restaurant_name
    for suffix in [" - Kitchen & Bar", " - Kitchen and Bar", " - Bar & Kitchen",
                   " - Restaurant & Bar", " - Restaurant", " - Cafe", " - Bar",
                   " Restaurant", " Cafe", " Bar", " Kitchen", " Lounge",
                   " - Lounge", " - Bistro", " Bistro"]:
        if short_name.lower().endswith(suffix.lower()):
            short_name = short_name[:len(short_name) - len(suffix)].strip()
            break

    print(f"   Full name: {restaurant_name}")
    print(f"   Short name: {short_name}")

    # Build search queries (most specific first)
    search_queries = []
    if city:
        search_queries.append(f"{short_name} {city} site:swiggy.com")
        search_queries.append(f"{clean_name} {city} site:swiggy.com")
        search_queries.append(f"{short_name} {city} swiggy")
    search_queries.append(f"{short_name} site:swiggy.com")
    search_queries.append(f"{short_name} swiggy menu")

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
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            for query in search_queries:
                print(f"\n🔎 DuckDuckGo: {query}")

                ddg_url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
                try:
                    await page.goto(ddg_url, timeout=15000)
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"   ⚠️ Navigation error: {e}")
                    continue

                # Get all links from the page
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.href)",
                )

                # Check for Swiggy URLs
                for href in links:
                    if "swiggy.com" in href and "rest" in href:
                        clean = _clean_redirect(href)
                        if "rest" in clean:
                            result["swiggy_url"] = clean
                            print(f"✅ Found Swiggy link: {clean[:100]}")
                            break

                if result["swiggy_url"]:
                    break

                # Also check page HTML for encoded URLs
                html = await page.content()
                swiggy_matches = re.findall(
                    r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&]+rest\d+[^\s"\'<>&]*',
                    html,
                )
                if swiggy_matches:
                    result["swiggy_url"] = urllib.parse.unquote(swiggy_matches[0])
                    print(f"✅ Found Swiggy in HTML: {result['swiggy_url'][:100]}")
                    break

                # Check DuckDuckGo redirect URLs (uddg parameter)
                uddg_matches = re.findall(r'uddg=(https?[^&"]+swiggy\.com[^&"]*)', html)
                for match in uddg_matches:
                    decoded = urllib.parse.unquote(match)
                    if "rest" in decoded:
                        result["swiggy_url"] = decoded
                        print(f"✅ Found Swiggy (DDG redirect): {decoded[:100]}")
                        break

                if result["swiggy_url"]:
                    break

            # ── If DDG failed, try Bing in the same browser ──
            if not result["swiggy_url"]:
                bing_queries = []
                if city:
                    bing_queries.append(f"{short_name} {city} site:swiggy.com")
                bing_queries.append(f"{short_name} swiggy site:swiggy.com")

                for query in bing_queries:
                    print(f"\n🔎 Bing: {query}")

                    try:
                        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
                        await page.goto(bing_url, timeout=15000)
                        await page.wait_for_timeout(2000)

                        html = await page.content()
                        swiggy_matches = re.findall(
                            r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&]+rest\d+[^\s"\'<>&]*',
                            html,
                        )
                        if swiggy_matches:
                            result["swiggy_url"] = urllib.parse.unquote(swiggy_matches[0])
                            print(f"✅ Found Swiggy (Bing): {result['swiggy_url'][:100]}")
                            break

                        # Check links too
                        links = await page.eval_on_selector_all(
                            "a[href]",
                            "els => els.map(e => e.href)",
                        )
                        for href in links:
                            if "swiggy.com" in href and "rest" in href:
                                clean = _clean_redirect(href)
                                if "rest" in clean:
                                    result["swiggy_url"] = clean
                                    print(f"✅ Found Swiggy (Bing link): {clean[:100]}")
                                    break

                        if result["swiggy_url"]:
                            break

                    except Exception as e:
                        print(f"   ⚠️ Bing error: {e}")
                        continue

        except Exception as e:
            print(f"❌ Search error: {e}")

        await browser.close()

    # Extract restaurant ID
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


def _clean_redirect(url: str) -> str:
    """Extract actual URL from search engine redirect wrappers."""
    # DuckDuckGo redirect
    if "duckduckgo.com/l/" in url:
        match = re.search(r'uddg=(https?[^&]+)', url)
        if match:
            return urllib.parse.unquote(match.group(1))
    # Google redirect
    if "google.com/url" in url:
        match = re.search(r'[?&]q=(https?[^&]+)', url)
        if match:
            return urllib.parse.unquote(match.group(1))
    return url
