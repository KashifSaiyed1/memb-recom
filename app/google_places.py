# app/google_places.py

import re
import json
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
    Find Swiggy restaurant ID using Swiggy's OWN search API.

    Instead of fighting search engines (all blocked on cloud IPs), we:
    1. Open Swiggy.com in browser (get WAF token + cookies)
    2. Call Swiggy's internal search API with restaurant name + lat/lng from Google
    3. Match the result to find the correct restaurant ID

    This is the most reliable approach because:
    - We use Swiggy's own data (not a third-party search engine)
    - Google Places lat/lng ensures we search in the right city
    - No search engine captchas or blocks
    """
    print(f"\n🔍 Finding Swiggy link for: {restaurant_name}")

    result = {
        "swiggy_url": None,
        "restaurant_id": None,
        "zomato_url": None,
    }

    city = _extract_city(address)
    print(f"   City from address: {city}")

    # Get lat/lng from address parsing (will be overridden by caller if available)
    short_name = _get_short_name(restaurant_name)
    print(f"   Full name: {restaurant_name}")
    print(f"   Short name: {short_name}")

    # Build search terms to try on Swiggy
    search_terms = [short_name]
    if short_name != restaurant_name:
        search_terms.append(restaurant_name)
    # Also try first word only (e.g., "Brewgarten" from "Brewgarten Ahmedabad")
    first_word = short_name.split()[0] if short_name else ""
    if first_word and len(first_word) >= 4 and first_word.lower() != short_name.lower():
        search_terms.append(first_word)

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
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """)

        page = await context.new_page()

        try:
            # ── Step 1: Open Swiggy to get WAF token ──
            print("📍 Loading Swiggy for search API access...")
            await page.goto("https://www.swiggy.com", timeout=30000)
            await page.wait_for_timeout(4000)

            cookies = await context.cookies()
            has_waf = "aws-waf-token" in [c["name"] for c in cookies]
            print(f"🍪 WAF token: {has_waf}")

            # ── Step 2: Call Swiggy search API from the browser ──
            for term in search_terms:
                print(f"\n🔎 Swiggy API search: '{term}'")

                search_result = await page.evaluate(
                    """async (params) => {
                        try {
                            const url = `https://www.swiggy.com/dapi/restaurants/search/v3?lat=${params.lat}&lng=${params.lng}&str=${encodeURIComponent(params.query)}&trackingId=undefined&submitAction=ENTER&queryUniqueId=`;
                            const response = await fetch(url, {
                                method: 'GET',
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json, text/plain, */*',
                                    'Content-Type': 'application/json',
                                }
                            });
                            const data = await response.json();
                            return { status: response.status, data: JSON.stringify(data) };
                        } catch(e) {
                            return { status: 0, data: e.message };
                        }
                    }""",
                    {
                        "query": term,
                        "lat": str(result.get("_lat", "19.0760")),
                        "lng": str(result.get("_lng", "72.8777")),
                    },
                )

                if search_result["status"] != 200:
                    print(f"   ⚠️ Swiggy API returned status: {search_result['status']}")
                    continue

                try:
                    api_data = json.loads(search_result["data"])
                except:
                    print(f"   ⚠️ Invalid JSON from Swiggy API")
                    continue

                # Parse search results to find restaurant cards
                restaurants = _extract_restaurants_from_search(api_data)
                print(f"   📋 Found {len(restaurants)} restaurants in Swiggy search")

                if not restaurants:
                    continue

                # Print all results for debugging
                for r in restaurants[:5]:
                    print(f"      → {r['name']} (ID: {r['id']}, Area: {r.get('area', 'N/A')})")

                # Try to match by name
                matched = _match_restaurant(restaurants, restaurant_name, short_name, city)

                if matched:
                    result["restaurant_id"] = str(matched["id"])
                    # Build Swiggy URL from the slug if available
                    slug = matched.get("slug", "")
                    city_slug = matched.get("city_slug", "")
                    if slug and city_slug:
                        result["swiggy_url"] = f"https://www.swiggy.com/city/{city_slug}/{slug}"
                    else:
                        result["swiggy_url"] = f"https://www.swiggy.com/restaurant/rest{matched['id']}"
                    print(f"✅ Matched: {matched['name']} (ID: {matched['id']})")
                    print(f"🔗 Swiggy URL: {result['swiggy_url']}")
                    break

        except Exception as e:
            print(f"❌ Error: {e}")

        await browser.close()

    # Extract restaurant ID from URL if not set
    if result["swiggy_url"] and not result["restaurant_id"]:
        match = re.search(r"rest(\d+)", result["swiggy_url"])
        if match:
            result["restaurant_id"] = match.group(1)

    if result["restaurant_id"]:
        print(f"🆔 Restaurant ID: {result['restaurant_id']}")
    else:
        print("⚠️ No matching restaurant found on Swiggy")

    return result


async def extract_swiggy_link_with_coords(
    place_id: str,
    restaurant_name: str,
    address: str,
    lat: str,
    lng: str,
) -> dict:
    """
    Same as extract_swiggy_link but accepts lat/lng directly.
    This is what routes.py should call.
    """
    print(f"\n🔍 Finding Swiggy link for: {restaurant_name}")

    result_data = {
        "swiggy_url": None,
        "restaurant_id": None,
        "zomato_url": None,
    }

    city = _extract_city(address)
    short_name = _get_short_name(restaurant_name)

    print(f"   City: {city}")
    print(f"   Full name: {restaurant_name}")
    print(f"   Short name: {short_name}")
    print(f"   Coords: {lat}, {lng}")

    # Build search terms
    search_terms = [short_name]
    if short_name != restaurant_name:
        search_terms.append(restaurant_name)
    first_word = short_name.split()[0] if short_name else ""
    if first_word and len(first_word) >= 4 and first_word.lower() != short_name.lower():
        search_terms.append(first_word)

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
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """)

        page = await context.new_page()

        try:
            # ── Step 1: Open Swiggy to get WAF token ──
            print("📍 Loading Swiggy for search API access...")
            await page.goto("https://www.swiggy.com", timeout=30000)
            await page.wait_for_timeout(4000)

            # Set location cookie with Google Places lat/lng
            await context.add_cookies([
                {
                    "name": "userLocation",
                    "value": json.dumps({
                        "lat": lat, "lng": lng,
                        "address": address or city,
                        "id": "", "annotation": city or "India",
                    }),
                    "domain": ".swiggy.com",
                    "path": "/",
                }
            ])

            cookies = await context.cookies()
            has_waf = "aws-waf-token" in [c["name"] for c in cookies]
            print(f"🍪 WAF token: {has_waf}")

            # ── Step 2: Call Swiggy search API ──
            for term in search_terms:
                print(f"\n🔎 Swiggy API search: '{term}' (lat={lat}, lng={lng})")

                search_result = await page.evaluate(
                    """async (params) => {
                        try {
                            const url = `https://www.swiggy.com/dapi/restaurants/search/v3?lat=${params.lat}&lng=${params.lng}&str=${encodeURIComponent(params.query)}&trackingId=undefined&submitAction=ENTER&queryUniqueId=`;
                            const response = await fetch(url, {
                                method: 'GET',
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json, text/plain, */*',
                                    'Content-Type': 'application/json',
                                }
                            });
                            const text = await response.text();
                            return { status: response.status, data: text };
                        } catch(e) {
                            return { status: 0, data: e.message };
                        }
                    }""",
                    {"query": term, "lat": lat, "lng": lng},
                )

                if search_result["status"] != 200:
                    print(f"   ⚠️ Swiggy API status: {search_result['status']}")
                    continue

                try:
                    api_data = json.loads(search_result["data"])
                except:
                    print(f"   ⚠️ Invalid JSON from Swiggy")
                    continue

                # Parse results
                restaurants = _extract_restaurants_from_search(api_data)
                print(f"   📋 Found {len(restaurants)} restaurants")

                if not restaurants:
                    continue

                for r in restaurants[:5]:
                    print(f"      → {r['name']} (ID: {r['id']}, Area: {r.get('area', 'N/A')})")

                # Match
                matched = _match_restaurant(restaurants, restaurant_name, short_name, city)

                if matched:
                    result_data["restaurant_id"] = str(matched["id"])
                    slug = matched.get("slug", "")
                    city_slug = matched.get("city_slug", "")
                    if slug and city_slug:
                        result_data["swiggy_url"] = f"https://www.swiggy.com/city/{city_slug}/{slug}"
                    else:
                        result_data["swiggy_url"] = f"https://www.swiggy.com/restaurant/rest{matched['id']}"
                    print(f"✅ Matched: {matched['name']} (ID: {matched['id']})")
                    print(f"🔗 URL: {result_data['swiggy_url']}")
                    break

        except Exception as e:
            print(f"❌ Error: {e}")

        await browser.close()

    if result_data["restaurant_id"]:
        print(f"🆔 Restaurant ID: {result_data['restaurant_id']}")
    else:
        print("⚠️ No matching restaurant found on Swiggy")

    return result_data


def _extract_restaurants_from_search(api_data: dict) -> list[dict]:
    """Parse Swiggy search API response to extract restaurant info."""
    restaurants = []

    # Swiggy search returns data in cards
    cards = api_data.get("data", {}).get("cards", [])

    for card in cards:
        # Try different card structures
        group_cards = card.get("groupedCard", {}).get("cardGroupMap", {})

        # Check RESTAURANT group
        rest_group = group_cards.get("RESTAURANT", {})
        if rest_group:
            for rc in rest_group.get("cards", []):
                info = rc.get("card", {}).get("card", {}).get("info", {})
                if info.get("id"):
                    restaurants.append(_parse_restaurant_info(info))

        # Also check top-level cards
        inner = card.get("card", {}).get("card", {})
        if inner.get("@type", "").endswith("RestaurantSearchResult"):
            info = inner.get("info", {})
            if info.get("id"):
                restaurants.append(_parse_restaurant_info(info))

        # Check for restaurant list in card
        if "restaurants" in inner:
            for rest in inner["restaurants"]:
                info = rest.get("info", {})
                if info.get("id"):
                    restaurants.append(_parse_restaurant_info(info))

    # Deduplicate by ID
    seen = set()
    unique = []
    for r in restaurants:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)

    return unique


def _parse_restaurant_info(info: dict) -> dict:
    """Parse a single restaurant info dict from Swiggy API."""
    return {
        "id": info.get("id", ""),
        "name": info.get("name", ""),
        "area": info.get("areaName", ""),
        "city_slug": info.get("city", {}).get("slug", "") if isinstance(info.get("city"), dict) else "",
        "slug": info.get("slugs", {}).get("restaurant", "") if isinstance(info.get("slugs"), dict) else "",
        "cuisines": info.get("cuisines", []),
        "rating": info.get("avgRating", ""),
        "cost_for_two": info.get("costForTwoMessage", ""),
    }


def _match_restaurant(restaurants: list[dict], full_name: str, short_name: str, city: str) -> dict | None:
    """
    Match a restaurant from Swiggy search results to the Google Places name.
    Uses fuzzy matching since names differ across platforms.
    """
    full_lower = full_name.lower().strip()
    short_lower = short_name.lower().strip()

    # Extract significant words from short name
    skip_words = {"the", "and", "of", "by", "at", "in", "a", "an"}
    short_words = [w for w in short_lower.split() if w not in skip_words and len(w) >= 3]

    # Pass 1: Exact name match
    for r in restaurants:
        r_name = r["name"].lower().strip()
        if r_name == full_lower or r_name == short_lower:
            return r

    # Pass 2: One name contains the other
    for r in restaurants:
        r_name = r["name"].lower().strip()
        if short_lower in r_name or r_name in short_lower:
            return r
        if full_lower in r_name or r_name in full_lower:
            return r

    # Pass 3: Majority of significant words match
    if short_words:
        best_match = None
        best_score = 0

        for r in restaurants:
            r_name = r["name"].lower()
            matched = sum(1 for w in short_words if w in r_name)
            score = matched / len(short_words)
            if score > best_score and score >= 0.5:
                best_score = score
                best_match = r

        if best_match:
            return best_match

    # Pass 4: If only 1 result, take it (Swiggy search was specific enough)
    if len(restaurants) == 1:
        print(f"   ℹ️ Only 1 result, auto-matching: {restaurants[0]['name']}")
        return restaurants[0]

    return None


def _get_short_name(name: str) -> str:
    """Remove common restaurant suffixes."""
    short = name
    suffixes = [
        " - Kitchen & Bar", " - Kitchen and Bar", " - Bar & Kitchen",
        " - Restaurant & Bar", " - Restaurant and Bar",
        " - Restaurant", " - Cafe", " - Bar", " - Lounge",
        " - Bistro", " - Brewery", " - Taproom",
        " Restaurant", " Cafe", " Bar", " Lounge",
        " Kitchen", " Bistro", " Brewery",
    ]
    for suffix in suffixes:
        if short.lower().endswith(suffix.lower()):
            short = short[:len(short) - len(suffix)].strip()
            break
    return short


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
