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
    Find Swiggy URL using DuckDuckGo HTML search inside Playwright.
    Uses html.duckduckgo.com (no JavaScript needed, instant results).
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
    short_name = _get_short_name(restaurant_name)
    print(f"   Full name: {restaurant_name}")
    print(f"   Short name: {short_name}")

    # Build search queries
    search_queries = []
    if city:
        search_queries.append(f"{short_name} {city} swiggy.com")
        search_queries.append(f"{short_name} {city} swiggy")
        if short_name != restaurant_name:
            search_queries.append(f"{restaurant_name} {city} swiggy.com")
    search_queries.append(f"{short_name} swiggy.com")
    search_queries.append(f"{short_name} swiggy menu order")

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
                print(f"\n🔎 DuckDuckGo HTML: {query}")

                # Use the HTML-only version of DuckDuckGo (no JS rendering needed)
                ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

                try:
                    await page.goto(ddg_url, timeout=15000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"   ⚠️ Navigation error: {e}")

                    # Fallback: try regular DuckDuckGo
                    try:
                        ddg_url2 = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&t=h_&ia=web"
                        await page.goto(ddg_url2, timeout=15000)
                        await page.wait_for_timeout(3000)
                    except:
                        continue

                # Get the full page HTML
                html = await page.content()

                # Debug: show page title and length
                title = await page.title()
                print(f"   Page: '{title[:50]}' ({len(html)} chars)")

                # ── Method 1: Find Swiggy URLs directly in HTML ──
                swiggy_patterns = [
                    r'https?://(?:www\.)?swiggy\.com/city/[^\s"\'<>&;]+rest\d+',
                    r'https?://(?:www\.)?swiggy\.com/[^\s"\'<>&;]*rest\d+',
                    r'swiggy\.com/city/[^\s"\'<>&;]+rest\d+',
                ]

                for pattern in swiggy_patterns:
                    matches = re.findall(pattern, html)
                    if matches:
                        url = matches[0]
                        if not url.startswith("http"):
                            url = "https://www." + url
                        result["swiggy_url"] = urllib.parse.unquote(url)
                        print(f"✅ Found Swiggy in HTML: {result['swiggy_url'][:100]}")
                        break

                if result["swiggy_url"]:
                    break

                # ── Method 2: Find encoded Swiggy URLs (DDG uddg redirect) ──
                uddg_matches = re.findall(r'uddg=([^&"\'<>\s]+)', html)
                for encoded_url in uddg_matches:
                    decoded = urllib.parse.unquote(encoded_url)
                    if "swiggy.com" in decoded and "rest" in decoded:
                        result["swiggy_url"] = decoded
                        print(f"✅ Found Swiggy (DDG uddg): {decoded[:100]}")
                        break

                if result["swiggy_url"]:
                    break

                # ── Method 3: Check all <a> href attributes ──
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => ({href: e.href, text: (e.textContent || '').substring(0, 80)}))",
                )

                # Debug: show results found
                result_links = [l for l in links if "swiggy" in l.get("href", "").lower() or "swiggy" in l.get("text", "").lower()]
                if result_links:
                    print(f"   🔗 Swiggy-related links found: {len(result_links)}")
                    for rl in result_links[:5]:
                        print(f"      → {rl['href'][:80]} [{rl['text'][:30]}]")

                for link in links:
                    href = link.get("href", "")

                    # Direct Swiggy link
                    if "swiggy.com" in href and "rest" in href:
                        result["swiggy_url"] = _clean_redirect(href)
                        print(f"✅ Found Swiggy (link): {result['swiggy_url'][:100]}")
                        break

                    # DDG redirect containing Swiggy
                    if "duckduckgo.com" in href and "swiggy" in href:
                        cleaned = _clean_redirect(href)
                        if "swiggy.com" in cleaned and "rest" in cleaned:
                            result["swiggy_url"] = cleaned
                            print(f"✅ Found Swiggy (DDG redirect link): {cleaned[:100]}")
                            break

                if result["swiggy_url"]:
                    break

                # Debug: show what links we DID find
                external = [l for l in links if l.get("href", "").startswith("http")
                           and "duckduckgo" not in l.get("href", "")]
                if external and not result_links:
                    print(f"   ℹ️ Non-DDG links found: {len(external)}")
                    for el in external[:3]:
                        print(f"      → {el['href'][:80]}")

            # ── Fallback: try Bing ──
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

                        for pattern in swiggy_patterns:
                            matches = re.findall(pattern, html)
                            if matches:
                                url = matches[0]
                                if not url.startswith("http"):
                                    url = "https://www." + url
                                result["swiggy_url"] = urllib.parse.unquote(url)
                                print(f"✅ Found Swiggy (Bing): {result['swiggy_url'][:100]}")
                                break

                        if result["swiggy_url"]:
                            break

                    except Exception as e:
                        print(f"   ⚠️ Bing error: {e}")

        except Exception as e:
            print(f"❌ Search error: {e}")

        await browser.close()

    # Extract restaurant ID
    if result["swiggy_url"]:
        # Clean up URL (remove tracking params)
        clean_url = result["swiggy_url"].split("?")[0] if "utm_" in result["swiggy_url"] else result["swiggy_url"]
        result["swiggy_url"] = clean_url

        match = re.search(r"rest(\d+)", result["swiggy_url"])
        if match:
            result["restaurant_id"] = match.group(1)
            print(f"🆔 Restaurant ID: {result['restaurant_id']}")
    else:
        print("⚠️ No Swiggy link found via any search engine")

    return result


def _get_short_name(name: str) -> str:
    """Remove common restaurant suffixes to get the core name."""
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
