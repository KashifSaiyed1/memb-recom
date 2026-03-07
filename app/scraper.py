# app/scraper.py

import asyncio
import json
import re
from playwright.async_api import async_playwright
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY


async def fetch_menu(restaurant_name: str, lat: str = DEFAULT_LAT, lng: str = DEFAULT_LNG, city_label: str = DEFAULT_CITY) -> dict | None:
    """
    OLD FLOW: Opens Swiggy, searches for the restaurant, clicks it,
    and captures the menu API response via CDP.
    """
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
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        page = await context.new_page()

        # ── CDP setup ──
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.enable")

        response_bodies: dict = {}
        menu_json: dict | None = None

        def on_response_received(params):
            url = params.get("response", {}).get("url", "")
            request_id = params.get("requestId", "")
            status = params.get("response", {}).get("status", 0)
            if "/dapi/menu/pl" in url:
                print(f"   📡 CDP: Menu API detected! Status: {status}, RequestID: {request_id}")
                response_bodies[request_id] = {"url": url, "status": status}

        async def on_loading_finished(params):
            nonlocal menu_json
            request_id = params.get("requestId", "")
            if request_id in response_bodies and response_bodies[request_id]["status"] == 200:
                try:
                    result = await cdp.send("Network.getResponseBody", {"requestId": request_id})
                    body = result.get("body", "")
                    data = json.loads(body)
                    if "data" in data:
                        menu_json = data
                        print("   ✅ Menu captured via CDP!")
                except Exception as e:
                    print(f"   ⚠️ CDP body fetch error: {e}")

        cdp.on("Network.responseReceived", on_response_received)
        cdp.on(
            "Network.loadingFinished",
            lambda params: asyncio.ensure_future(on_loading_finished(params)),
        )

        # ── Step 1: Load Swiggy homepage ──
        print("\n📍 Loading Swiggy (solving WAF challenge)...")
        try:
            await page.goto("https://www.swiggy.com", timeout=60000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"❌ Failed to load Swiggy: {e}")
            await browser.close()
            return None

        await context.add_cookies([
            {
                "name": "userLocation",
                "value": json.dumps({
                    "lat": lat, "lng": lng,
                    "address": city_label, "id": "",
                    "annotation": city_label.split(",")[0],
                }),
                "domain": ".swiggy.com",
                "path": "/",
            }
        ])

        cookies = await context.cookies()
        has_waf = "aws-waf-token" in [c["name"] for c in cookies]
        print(f"🍪 WAF token present: {has_waf}")

        # ── Step 2: Search ──
        print(f"🔎 Searching for {restaurant_name} on Swiggy...")
        search_url = f"https://www.swiggy.com/search?query={restaurant_name.replace(' ', '%20')}"
        await page.goto(search_url, timeout=60000)
        await page.wait_for_timeout(3000)

        # ── Step 3: Find restaurant ID ──
        restaurant_id = await _find_restaurant_id(page, restaurant_name)

        if not restaurant_id:
            print("❌ Could not find restaurant ID")
            await browser.close()
            return None

        # ── Step 4: Click restaurant card ──
        print("📡 Clicking restaurant (SPA navigation)...")
        target = page.locator(f"a[href*='rest{restaurant_id}']").first

        if await target.count() == 0:
            print("❌ Restaurant link not found")
            await browser.close()
            return None

        await target.click()

        # ── Step 5: Wait for menu API capture ──
        print("⏳ Waiting for menu data...")
        for _ in range(40):
            if menu_json:
                break
            await page.wait_for_timeout(500)

        if not menu_json:
            print("\n🔄 Fallback: Direct fetch...")
            menu_json = await _direct_fetch_menu(page, lat, lng, restaurant_id)

        await cdp.detach()
        await browser.close()
        return menu_json


async def fetch_menu_by_id(
    restaurant_id: str,
    lat: str = DEFAULT_LAT,
    lng: str = DEFAULT_LNG,
    city_label: str = DEFAULT_CITY,
    swiggy_url: str = None,
) -> dict | None:
    """
    NEW FLOW: Fetch menu directly using restaurant ID — SKIPS Swiggy search.
    Used when we already have the restaurant ID from Google Maps → Swiggy link.
    """
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
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        page = await context.new_page()

        # ── CDP setup ──
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.enable")

        response_bodies: dict = {}
        menu_json: dict | None = None

        def on_response_received(params):
            url = params.get("response", {}).get("url", "")
            request_id = params.get("requestId", "")
            status = params.get("response", {}).get("status", 0)
            if "/dapi/menu/pl" in url:
                print(f"   📡 CDP: Menu API detected! Status: {status}, RequestID: {request_id}")
                response_bodies[request_id] = {"url": url, "status": status}

        async def on_loading_finished(params):
            nonlocal menu_json
            request_id = params.get("requestId", "")
            if request_id in response_bodies and response_bodies[request_id]["status"] == 200:
                try:
                    result = await cdp.send("Network.getResponseBody", {"requestId": request_id})
                    body = result.get("body", "")
                    data = json.loads(body)
                    if "data" in data:
                        menu_json = data
                        print("   ✅ Menu captured via CDP!")
                except Exception as e:
                    print(f"   ⚠️ CDP body fetch error: {e}")

        cdp.on("Network.responseReceived", on_response_received)
        cdp.on(
            "Network.loadingFinished",
            lambda params: asyncio.ensure_future(on_loading_finished(params)),
        )

        # ── Step 1: Load Swiggy homepage (WAF challenge) ──
        print(f"\n📍 Loading Swiggy (direct ID fetch for rest{restaurant_id})...")
        try:
            await page.goto("https://www.swiggy.com", timeout=60000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"❌ Failed to load Swiggy: {e}")
            await browser.close()
            return None

        await context.add_cookies([
            {
                "name": "userLocation",
                "value": json.dumps({
                    "lat": lat, "lng": lng,
                    "address": city_label, "id": "",
                    "annotation": city_label.split(",")[0],
                }),
                "domain": ".swiggy.com",
                "path": "/",
            }
        ])

        cookies = await context.cookies()
        has_waf = "aws-waf-token" in [c["name"] for c in cookies]
        print(f"🍪 WAF token present: {has_waf}")

        # ── Step 2: Navigate to restaurant page directly (SKIP SEARCH!) ──
        if swiggy_url:
            print(f"🔗 Navigating to Swiggy URL: {swiggy_url[:80]}...")
            try:
                await page.goto(swiggy_url, timeout=30000, wait_until="domcontentloaded")
            except:
                pass  # SPA might not fully load, that's OK
        else:
            print(f"🔗 No Swiggy URL, using direct API fetch for ID: {restaurant_id}")

        # ── Step 3: Wait for menu API capture ──
        print("⏳ Waiting for menu data...")
        for _ in range(30):
            if menu_json:
                break
            await page.wait_for_timeout(500)

        # Fallback: direct API fetch
        if not menu_json:
            print("🔄 Fallback: Direct API fetch by ID...")
            menu_json = await _direct_fetch_menu(page, lat, lng, restaurant_id)

        await cdp.detach()
        await browser.close()
        return menu_json


# ── Internal helpers ──


async def _find_restaurant_id(page, restaurant_name: str) -> str | None:
    """Extract the Swiggy restaurant ID from search result links."""
    links = await page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({href: e.href, text: e.innerText.substring(0, 100)}))",
    )

    name_lower = restaurant_name.lower().strip()
    search_terms = [name_lower]

    for prefix in ["the ", "hotel ", "cafe ", "restaurant "]:
        if name_lower.startswith(prefix):
            search_terms.append(name_lower[len(prefix):])

    skip_words = {"the", "and", "for", "hotel", "cafe", "restaurant", "bar", "lounge"}
    words = [w for w in name_lower.split() if len(w) >= 3 and w not in skip_words]

    # First pass: full name match
    for link in links:
        href = link.get("href", "")
        text = link.get("text", "").lower()
        if "rest" in href and any(term in text for term in search_terms):
            match = re.search(r"rest(\d+)", href)
            if match:
                print(f"✅ Found: {text[:60]}...")
                print(f"🆔 Restaurant ID: {match.group(1)}")
                return match.group(1)

    # Second pass: partial word match (60%)
    if len(words) >= 2:
        for link in links:
            href = link.get("href", "")
            text = link.get("text", "").lower()
            if "rest" in href:
                matched_words = sum(1 for w in words if w in text)
                if matched_words >= len(words) * 0.6:
                    match = re.search(r"rest(\d+)", href)
                    if match:
                        print(f"✅ Found (partial match): {text[:60]}...")
                        print(f"🆔 Restaurant ID: {match.group(1)}")
                        return match.group(1)

    # Third pass: URL slug match
    name_slug = name_lower.replace(" ", "-").replace("'", "")
    for link in links:
        href = link.get("href", "").lower()
        if "rest" in href and name_slug in href:
            match = re.search(r"rest(\d+)", href)
            if match:
                text = link.get("text", "").lower()
                print(f"✅ Found (URL match): {text[:60]}...")
                print(f"🆔 Restaurant ID: {match.group(1)}")
                return match.group(1)

    # No blind fallback
    print(f"❌ No matching restaurant found for '{restaurant_name}'")
    print(f"   Available results on Swiggy:")
    count = 0
    for link in links:
        href = link.get("href", "")
        text = link.get("text", "").strip()
        if "rest" in href and text and len(text) > 10:
            print(f"   → {text[:70]}")
            count += 1
            if count >= 8:
                break

    return None


async def _direct_fetch_menu(page, lat: str, lng: str, restaurant_id: str) -> dict | None:
    """Fallback: fetch menu API using browser's fetch() with session cookies."""
    import json as _json

    menu_api_url = (
        f"https://www.swiggy.com/dapi/menu/pl"
        f"?page-type=REGULAR_MENU"
        f"&complete-menu=true"
        f"&lat={lat}"
        f"&lng={lng}"
        f"&restaurantId={restaurant_id}"
        f"&submitAction=ENTER"
    )

    result = await page.evaluate(
        """async (params) => {
            try {
                const response = await fetch(params.url, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                        'Content-Type': 'application/json',
                    }
                });
                return { status: response.status, body: await response.text() };
            } catch(e) {
                return { status: 0, body: e.message };
            }
        }""",
        {"url": menu_api_url},
    )

    if result["status"] == 200 and result["body"]:
        try:
            menu_json = _json.loads(result["body"])
            if "data" in menu_json:
                print("✅ Menu captured via direct fetch!")
                return menu_json
        except _json.JSONDecodeError:
            pass

    print(f"⚠️ Direct fetch failed with status: {result['status']}")
    return None