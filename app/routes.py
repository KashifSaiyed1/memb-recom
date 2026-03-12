# app/routes.py

from fastapi import APIRouter, HTTPException
from app.models import (
    ScrapeRequest, ScrapeResponse, CityListResponse,
    SuggestRequest, SuggestResponse, PlaceSuggestion,
    GmapsScrapeRequest,
)
from app.service import process_restaurant, process_menu_json
from app.google_places import search_restaurants, find_and_fetch_menu
from app.cities import get_city_coordinates, get_all_cities
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY

router = APIRouter()


# ══════════════════════════════════════════════
#  STEP 1: Google Places suggestions
# ══════════════════════════════════════════════

@router.post("/suggest", response_model=SuggestResponse)
async def suggest_restaurants(request: SuggestRequest):
    """Search restaurants via Google Places API."""
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
#  STEP 2: Scrape via Google Places (OPTIMIZED)
# ══════════════════════════════════════════════

@router.post("/scrape-gmaps", response_model=ScrapeResponse)
async def scrape_via_gmaps(request: GmapsScrapeRequest):
    """
    OPTIMIZED: Single browser session does search + menu fetch.
    ~18-22 seconds instead of ~40 seconds.
    """
    lat = str(request.lat) if request.lat else DEFAULT_LAT
    lng = str(request.lng) if request.lng else DEFAULT_LNG

    try:
        # ── Single-session: find restaurant + fetch menu ──
        scrape_result = await find_and_fetch_menu(
            restaurant_name=request.name,
            address=request.address,
            lat=lat,
            lng=lng,
        )

        swiggy_url = scrape_result.get("swiggy_url")
        restaurant_id = scrape_result.get("restaurant_id")
        menu_json = scrape_result.get("menu_json")

        if not restaurant_id:
            # Fallback: try old Swiggy search flow
            if request.name:
                print(f"\n🔄 Fallback: Old Swiggy search with '{request.name}'...")
                result = await process_restaurant(
                    restaurant_name=request.name,
                    lat=lat,
                    lng=lng,
                    city_label="Google Maps location",
                    save_csv=False,
                    save_json=False,
                )

                if "error" not in result:
                    menu_df = result["menu_df"]
                    menu_items = menu_df.to_dict(orient="records")
                    return ScrapeResponse(
                        success=True,
                        scrape_method="swiggy_search_fallback",
                        restaurant_info=result["restaurant_info"],
                        inferred=result["inferred"],
                        menu_items=menu_items,
                        total_items=len(menu_items),
                    )

                # Try short name
                short_name = request.name.split(" - ")[0].split(" | ")[0].split(",")[0].strip()
                if short_name != request.name:
                    result = await process_restaurant(
                        restaurant_name=short_name,
                        lat=lat,
                        lng=lng,
                        city_label="Google Maps location",
                        save_csv=False,
                        save_json=False,
                    )
                    if "error" not in result:
                        menu_df = result["menu_df"]
                        menu_items = menu_df.to_dict(orient="records")
                        return ScrapeResponse(
                            success=True,
                            scrape_method="swiggy_shortname_fallback",
                            restaurant_info=result["restaurant_info"],
                            inferred=result["inferred"],
                            menu_items=menu_items,
                            total_items=len(menu_items),
                        )

            return ScrapeResponse(
                success=False,
                scrape_method="google_maps",
                swiggy_url=swiggy_url,
                error="Could not find this restaurant on Swiggy.",
            )

        if not menu_json:
            return ScrapeResponse(
                success=False,
                scrape_method="google_maps_direct",
                swiggy_url=swiggy_url,
                error="Restaurant found on Swiggy but menu could not be captured.",
            )

        # Process the menu JSON (parse + infer)
        result = await process_menu_json(menu_json)

        if "error" in result:
            return ScrapeResponse(
                success=False,
                scrape_method="google_maps_direct",
                swiggy_url=swiggy_url,
                error=result["error"],
            )

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
    cities = get_all_cities()
    return CityListResponse(total=len(cities), cities=cities)


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_restaurant(request: ScrapeRequest):
    lat, lng, city_label = _resolve_location(request)
    if not lat or not lng:
        return ScrapeResponse(success=False, error=f"City '{request.city}' not found.")

    try:
        result = await process_restaurant(
            restaurant_name=request.restaurant_name,
            lat=lat, lng=lng, city_label=city_label,
            save_csv=False, save_json=False,
        )
        if "error" in result:
            return ScrapeResponse(success=False, city_used=city_label, scrape_method="swiggy_search", error=result["error"])

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")
        return ScrapeResponse(
            success=True, city_used=city_label, scrape_method="swiggy_search",
            restaurant_info=result["restaurant_info"], inferred=result["inferred"],
            menu_items=menu_items, total_items=len(menu_items),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape-and-save", response_model=ScrapeResponse)
async def scrape_and_save(request: ScrapeRequest):
    lat, lng, city_label = _resolve_location(request)
    if not lat or not lng:
        return ScrapeResponse(success=False, error=f"City '{request.city}' not found.")

    try:
        result = await process_restaurant(
            restaurant_name=request.restaurant_name,
            lat=lat, lng=lng, city_label=city_label,
            save_csv=True, save_json=True,
        )
        if "error" in result:
            return ScrapeResponse(success=False, city_used=city_label, scrape_method="swiggy_search", error=result["error"])

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")
        return ScrapeResponse(
            success=True, city_used=city_label, scrape_method="swiggy_search",
            restaurant_info=result["restaurant_info"], inferred=result["inferred"],
            menu_items=menu_items, total_items=len(menu_items),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
