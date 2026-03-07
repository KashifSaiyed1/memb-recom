# app/routes.py

from fastapi import APIRouter, HTTPException
from app.models import (
    ScrapeRequest, ScrapeResponse, CityListResponse,
    SuggestRequest, SuggestResponse, PlaceSuggestion,
    GmapsScrapeRequest,
)
from app.service import process_restaurant, process_restaurant_by_id
from app.google_places import search_restaurants, extract_swiggy_link_with_coords
from app.cities import get_city_coordinates, get_all_cities
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY

router = APIRouter()


# ══════════════════════════════════════════════
#  STEP 1: Google Places suggestions
# ══════════════════════════════════════════════

@router.post("/suggest", response_model=SuggestResponse)
async def suggest_restaurants(request: SuggestRequest):
    """
    Search restaurants via Google Places API.
    Returns a list of suggestions with place_id, name, address, lat/lng.

    Usage: User types "Tanatan Juhu" → gets suggestions → picks the right one.
    """
    try:
        results = await search_restaurants(request.query)

        suggestions = [
            PlaceSuggestion(
                place_id=r["place_id"],
                name=r["name"],
                address=r["address"],
                lat=r.get("lat"),
                lng=r.get("lng"),
                rating=r.get("rating"),
                total_ratings=r.get("total_ratings"),
            )
            for r in results
        ]

        return SuggestResponse(success=True, results=suggestions)

    except Exception as e:
        return SuggestResponse(success=False, error=str(e))


# ══════════════════════════════════════════════
#  STEP 2: Scrape via Google Maps (NEW FLOW)
# ══════════════════════════════════════════════

@router.post("/scrape-gmaps", response_model=ScrapeResponse)
async def scrape_via_gmaps(request: GmapsScrapeRequest):
    """
    NEW FLOW:
    1. Try: Google Maps place_id → Extract Swiggy link → Fetch menu by ID
    2. Fallback: Use Google Places name + lat/lng to search Swiggy directly

    Pass the name and lat/lng from the /suggest response.
    """
    lat = request.lat or DEFAULT_LAT
    lng = request.lng or DEFAULT_LNG
    city_label = "Google Maps location"

    try:
        # ── Strategy 1: Find restaurant on Swiggy using its own search API ──
        print(f"\n🗺️ Strategy 1: Searching Swiggy API with Google Places name + coords...")
        link_result = await extract_swiggy_link_with_coords(
            place_id=request.place_id,
            restaurant_name=request.name,
            address=request.address,
            lat=lat,
            lng=lng,
        )

        swiggy_url = link_result.get("swiggy_url")
        restaurant_id = link_result.get("restaurant_id")

        if restaurant_id:
            print(f"✅ Got Swiggy restaurant ID: {restaurant_id}")
            print(f"🔗 Swiggy URL: {swiggy_url}")

            result = await process_restaurant_by_id(
                restaurant_id=restaurant_id,
                lat=lat,
                lng=lng,
                city_label=city_label,
                swiggy_url=swiggy_url,
                save_csv=False,
                save_json=False,
            )

            if "error" not in result:
                menu_df = result["menu_df"]
                menu_items = menu_df.to_dict(orient="records")

                return ScrapeResponse(
                    success=True,
                    scrape_method="google_maps_direct",
                    swiggy_url=swiggy_url,
                    restaurant_info=result["restaurant_info"],
                    inferred=result["inferred"],
                    menu_items=menu_items,
                    total_items=len(menu_items),
                )

        # ── Strategy 2: Fallback — search Swiggy with Google name + lat/lng ──
        if request.name:
            print(f"\n🔄 Strategy 2: Searching Swiggy with Google name '{request.name}'...")

            # Try the full Google name first
            result = await process_restaurant(
                restaurant_name=request.name,
                lat=lat,
                lng=lng,
                city_label=city_label,
                save_csv=False,
                save_json=False,
            )

            if "error" not in result:
                menu_df = result["menu_df"]
                menu_items = menu_df.to_dict(orient="records")

                return ScrapeResponse(
                    success=True,
                    scrape_method="google_name_swiggy_search",
                    swiggy_url=swiggy_url,
                    restaurant_info=result["restaurant_info"],
                    inferred=result["inferred"],
                    menu_items=menu_items,
                    total_items=len(menu_items),
                )

            # Try with just the first part of the name (before " - " or " | ")
            short_name = request.name.split(" - ")[0].split(" | ")[0].split(",")[0].strip()
            if short_name != request.name:
                print(f"\n🔄 Strategy 2b: Trying short name '{short_name}'...")

                result = await process_restaurant(
                    restaurant_name=short_name,
                    lat=lat,
                    lng=lng,
                    city_label=city_label,
                    save_csv=False,
                    save_json=False,
                )

                if "error" not in result:
                    menu_df = result["menu_df"]
                    menu_items = menu_df.to_dict(orient="records")

                    return ScrapeResponse(
                        success=True,
                        scrape_method="google_shortname_swiggy_search",
                        swiggy_url=swiggy_url,
                        restaurant_info=result["restaurant_info"],
                        inferred=result["inferred"],
                        menu_items=menu_items,
                        total_items=len(menu_items),
                    )

        # ── All strategies failed ──
        return ScrapeResponse(
            success=False,
            scrape_method="google_maps",
            swiggy_url=swiggy_url,
            error="Could not find this restaurant on Swiggy. Tried: Google Maps link extraction, Swiggy name search.",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
#  OLD FLOW: Scrape via Swiggy search
# ══════════════════════════════════════════════

def _resolve_location(request: ScrapeRequest) -> tuple[str, str, str]:
    if request.lat and request.lng:
        return request.lat, request.lng, f"Custom ({request.lat}, {request.lng})"
    city_data = get_city_coordinates(request.city)
    if city_data:
        return city_data["lat"], city_data["lng"], city_data["label"]
    return None, None, None


@router.get("/cities", response_model=CityListResponse)
def list_cities():
    """Return all supported city names."""
    cities = get_all_cities()
    return CityListResponse(total=len(cities), cities=cities)


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_restaurant(request: ScrapeRequest):
    """
    OLD FLOW: Search Swiggy by restaurant name + city.
    Still works, but /suggest + /scrape-gmaps is more accurate.
    """
    lat, lng, city_label = _resolve_location(request)

    if not lat or not lng:
        return ScrapeResponse(
            success=False,
            error=f"City '{request.city}' not found. Use GET /api/cities to see supported cities, or pass custom lat/lng.",
        )

    print(f"\n📍 Location: {city_label} ({lat}, {lng})")

    try:
        result = await process_restaurant(
            restaurant_name=request.restaurant_name,
            lat=lat,
            lng=lng,
            city_label=city_label,
            save_csv=False,
            save_json=False,
        )

        if "error" in result:
            return ScrapeResponse(
                success=False,
                city_used=city_label,
                scrape_method="swiggy_search",
                error=result["error"],
            )

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")

        return ScrapeResponse(
            success=True,
            city_used=city_label,
            scrape_method="swiggy_search",
            restaurant_info=result["restaurant_info"],
            inferred=result["inferred"],
            menu_items=menu_items,
            total_items=len(menu_items),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape-and-save", response_model=ScrapeResponse)
async def scrape_and_save(request: ScrapeRequest):
    """Same as /scrape but also saves CSV and JSON files locally."""
    lat, lng, city_label = _resolve_location(request)

    if not lat or not lng:
        return ScrapeResponse(
            success=False,
            error=f"City '{request.city}' not found.",
        )

    try:
        result = await process_restaurant(
            restaurant_name=request.restaurant_name,
            lat=lat,
            lng=lng,
            city_label=city_label,
            save_csv=True,
            save_json=True,
        )

        if "error" in result:
            return ScrapeResponse(
                success=False,
                city_used=city_label,
                scrape_method="swiggy_search",
                error=result["error"],
            )

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")

        return ScrapeResponse(
            success=True,
            city_used=city_label,
            scrape_method="swiggy_search",
            restaurant_info=result["restaurant_info"],
            inferred=result["inferred"],
            menu_items=menu_items,
            total_items=len(menu_items),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
