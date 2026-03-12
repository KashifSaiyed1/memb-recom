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


async def find_and_fetch_menu(
    restaurant_name: str,
    address: str,
    lat: str,
    lng: str,
) -> dict:
    """
    OPTIMIZED: Single browser session does EVERYTHING:
    1. Open Swiggy → solve WAF
    2. Search Swiggy API for restaurant → get ID
    3. Fetch menu API with that ID → get menu JSON

    Returns dict with: restaurant_id, swiggy_url, menu_json
    """
    import asyncio

    print(f"\n🚀 Single-session scrape for: {restaurant_name}")

    result = {
        "restaurant_id": None,
        "swiggy_url": None,
        "menu_json": None,
    }

    city = _extract_city(address)
    short_name = _get_short_name(restaurant_name)

    print(f"   City: {city}")
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
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            geolocation={"latitude": float(lat), "longitude": float(lng)},
            permissions=["geolocation"],
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
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        page = await context.new_page()

        # ── CDP setup for menu capture ──
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.enable")

        response_bodies = {}
        menu_json_captured = {"data": None}

        def on_response_received(params):
            url = params.get("response", {}).get("url", "")
            request_id = params.get("requestId", "")
            status = params.get("response", {}).get("status", 0)
            if "/dapi/menu/pl" in url:
                print(f"   📡 CDP: Menu API detected! Status: {status}")
                response_bodies[request_id] = {"url": url, "status": status}

        async def on_loading_finished(params):
            request_id = params.get("requestId", "")
            if request_id in response_bodies and response_bodies[request_id]["status"] == 200:
                try:
                    body_result = await cdp.send("Network.getResponseBody", {"requestId": request_id})
                    body = body_result.get("body", "")
                    data = json.loads(body)
                    if "data" in data:
                        menu_json_captured["data"] = data
                        print("   ✅ Menu captured via CDP!")
                except Exception as e:
                    print(f"   ⚠️ CDP body fetch error: {e}")

        cdp.on("Network.responseReceived", on_response_received)
        cdp.on("Network.loadingFinished", lambda p: asyncio.ensure_future(on_loading_finished(p)))

        try:
            # ══════════════════════════════════════
            #  PHASE 1: Open Swiggy + WAF (4 seconds)
            # ══════════════════════════════════════
            print("\n📍 Phase 1: Loading Swiggy...")
            await page.goto("https://www.swiggy.com", timeout=30000)
            await page.wait_for_timeout(4000)

            # Set location cookie
            await context.add_cookies([{
                "name": "userLocation",
                "value": json.dumps({
                    "lat": lat, "lng": lng,
                    "address": address or city or "India",
                    "id": "", "annotation": city or "India",
                }),
                "domain": ".swiggy.com",
                "path": "/",
            }])

            cookies = await context.cookies()
            has_waf = "aws-waf-token" in [c["name"] for c in cookies]
            print(f"🍪 WAF token: {has_waf}")

            # ══════════════════════════════════════
            #  PHASE 2: Search Swiggy API (2-3 seconds)
            # ══════════════════════════════════════
            restaurant_id = None

            for term in search_terms:
                print(f"\n🔎 Phase 2: Swiggy search: '{term}'")

                search_result = await page.evaluate(
                    """async (params) => {
                        try {
                            const url = `https://www.swiggy.com/dapi/restaurants/search/v3?lat=${params.lat}&lng=${params.lng}&str=${encodeURIComponent(params.query)}&trackingId=undefined&submitAction=ENTER&queryUniqueId=`;
                            const response = await fetch(url, {
                                method: 'GET',
                                credentials: 'include',
                                headers: { 'Accept': 'application/json' }
                            });
                            return { status: response.status, data: await response.text() };
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
                    continue

                restaurants = _extract_restaurants_from_search(api_data)
                print(f"   📋 Found {len(restaurants)} restaurants")

                for r in restaurants[:5]:
                    print(f"      → {r['name']} (ID: {r['id']})")

                matched = _match_restaurant(restaurants, restaurant_name, short_name, city)

                if matched:
                    restaurant_id = str(matched["id"])
                    slug = matched.get("slug", "")
                    city_slug = matched.get("city_slug", "")
                    if slug and city_slug:
                        result["swiggy_url"] = f"https://www.swiggy.com/city/{city_slug}/{slug}"
                    else:
                        result["swiggy_url"] = f"https://www.swiggy.com/restaurant/rest{restaurant_id}"
                    result["restaurant_id"] = restaurant_id
                    print(f"✅ Matched: {matched['name']} (ID: {restaurant_id})")
                    break

            if not restaurant_id:
                print("❌ No restaurant found on Swiggy")
                await cdp.detach()
                await browser.close()
                return result

            # ══════════════════════════════════════
            #  PHASE 3: Fetch menu (same browser!) (8-12 seconds)
            # ══════════════════════════════════════
            print(f"\n📡 Phase 3: Fetching menu for rest{restaurant_id}...")

            # Navigate to restaurant page to trigger menu API
            if result["swiggy_url"]:
                print(f"🔗 Navigating to: {result['swiggy_url'][:80]}...")
                try:
                    await page.goto(result["swiggy_url"], timeout=20000, wait_until="domcontentloaded")
                except:
                    pass  # SPA might error, that's OK

            # Wait for CDP to capture menu
            for _ in range(25):
                if menu_json_captured["data"]:
                    break
                await page.wait_for_timeout(500)

            # Fallback: direct API fetch
            if not menu_json_captured["data"]:
                print("🔄 Fallback: Direct API fetch...")
                fetch_result = await page.evaluate(
                    """async (params) => {
                        try {
                            const url = `https://www.swiggy.com/dapi/menu/pl?page-type=REGULAR_MENU&complete-menu=true&lat=${params.lat}&lng=${params.lng}&restaurantId=${params.id}&submitAction=ENTER`;
                            const response = await fetch(url, {
                                method: 'GET',
                                credentials: 'include',
                                headers: { 'Accept': 'application/json' }
                            });
                            return { status: response.status, body: await response.text() };
                        } catch(e) {
                            return { status: 0, body: e.message };
                        }
                    }""",
                    {"lat": lat, "lng": lng, "id": restaurant_id},
                )

                if fetch_result["status"] == 200 and fetch_result["body"]:
                    try:
                        data = json.loads(fetch_result["body"])
                        if "data" in data:
                            menu_json_captured["data"] = data
                            print("✅ Menu captured via direct fetch!")
                    except:
                        pass

            result["menu_json"] = menu_json_captured["data"]

        except Exception as e:
            print(f"❌ Error: {e}")

        await cdp.detach()
        await browser.close()

    if result["menu_json"]:
        print(f"🏁 Done! Restaurant ID: {result['restaurant_id']}")
    else:
        print("❌ Menu not captured")

    return result


# ══════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════

def _extract_restaurants_from_search(api_data: dict) -> list[dict]:
    """Parse Swiggy search API response to extract restaurant info."""
    restaurants = []
    cards = api_data.get("data", {}).get("cards", [])

    for card in cards:
        group_cards = card.get("groupedCard", {}).get("cardGroupMap", {})
        rest_group = group_cards.get("RESTAURANT", {})
        if rest_group:
            for rc in rest_group.get("cards", []):
                info = rc.get("card", {}).get("card", {}).get("info", {})
                if info.get("id"):
                    restaurants.append(_parse_restaurant_info(info))

        inner = card.get("card", {}).get("card", {})
        if inner.get("@type", "").endswith("RestaurantSearchResult"):
            info = inner.get("info", {})
            if info.get("id"):
                restaurants.append(_parse_restaurant_info(info))

        if "restaurants" in inner:
            for rest in inner["restaurants"]:
                info = rest.get("info", {})
                if info.get("id"):
                    restaurants.append(_parse_restaurant_info(info))

    seen = set()
    unique = []
    for r in restaurants:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    return unique


def _parse_restaurant_info(info: dict) -> dict:
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
    full_lower = full_name.lower().strip()
    short_lower = short_name.lower().strip()
    skip_words = {"the", "and", "of", "by", "at", "in", "a", "an"}
    short_words = [w for w in short_lower.split() if w not in skip_words and len(w) >= 3]

    for r in restaurants:
        r_name = r["name"].lower().strip()
        if r_name == full_lower or r_name == short_lower:
            return r

    for r in restaurants:
        r_name = r["name"].lower().strip()
        if short_lower in r_name or r_name in short_lower:
            return r
        if full_lower in r_name or r_name in full_lower:
            return r

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

    if len(restaurants) == 1:
        return restaurants[0]

    return None


def _get_short_name(name: str) -> str:
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
    return cleaned[0] if cleaned else ""
