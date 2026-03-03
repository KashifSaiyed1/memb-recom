import asyncio
import json
import re
from playwright.async_api import async_playwright
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY


async def fetch_menu(restaurant_name: str, lat: str = DEFAULT_LAT, lng: str = DEFAULT_LNG, city_label: str = DEFAULT_CITY) -> dict | None:
    """
    Opens Swiggy, searches for the restaurant, clicks it,
    and captures the menu API response via Chrome DevTools Protocol.

    Updated for Render Deployment (Headless).
    """
    async with async_playwright() as p:
        # CHANGED: headless=True for server environment
        # ADDED: --disable-dev-shm-usage and --disable-gpu for container stability
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

        # Stealth: remove automation signals (Your original logic)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        page = await context.new_page()

        # ── CDP setup for low-level response capture (Your original logic) ──
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

        # ── Step 1: Load Swiggy homepage (Your original logic) ──
        print("\n📍 Loading Swiggy (solving WAF challenge)...")
        try:
            await page.goto("https://www.swiggy.com", timeout=60000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"❌ Failed to load Swiggy: {e}")
            await browser.close()
            return None

        # Set location cookie
        await context.add_cookies([
            {
                "name": "userLocation",
                "value": json.dumps({
                    "lat": lat,
                    "lng": lng,
                    "address": city_label,
                    "id": "",
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

        # Fallback: direct fetch
        if not menu_json:
            print("\n🔄 Fallback: Direct fetch...")
            menu_json = await _direct_fetch_menu(page, lat, lng, restaurant_id)

        await cdp.detach()
        await browser.close()
        return menu_json


async def _find_restaurant_id(page, restaurant_name: str) -> str | None:
    """Extract the Swiggy restaurant ID from search result links (Unchanged)."""
    links = await page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({href: e.href, text: e.innerText.substring(0, 80)}))",
    )

    search_terms = [
        restaurant_name.lower(),
        restaurant_name.lower().replace("the ", ""),
    ]

    for link in links:
        href = link.get("href", "")
        text = link.get("text", "").lower()
        if "rest" in href and any(term in text for term in search_terms):
            match = re.search(r"rest(\d+)", href)
            if match:
                print(f"✅ Found: {text[:60]}...")
                return match.group(1)

    for link in links:
        href = link.get("href", "")
        text = link.get("text", "").lower()
        if "rest" in href and ("min" in text or "for two" in text):
            match = re.search(r"rest(\d+)", href)
            if match:
                print(f"✅ Found (fallback): {text[:60]}...")
                return match.group(1)

    return None


async def _direct_fetch_menu(page, lat: str, lng: str, restaurant_id: str) -> dict | None:
    """Fallback: fetch menu API using browser's fetch() (Unchanged)."""
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