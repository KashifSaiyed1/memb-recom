# app/routes.py

from fastapi import APIRouter, HTTPException
from app.models import ScrapeRequest, ScrapeResponse, CityListResponse
from app.service import process_restaurant
from app.cities import get_city_coordinates, get_all_cities
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY

router = APIRouter()


def _resolve_location(request: ScrapeRequest) -> tuple[str, str, str]:
    """
    Resolve lat/lng/label from the request.
    Priority: custom lat/lng > city name > default (Ahmedabad).
    """
    # If custom lat/lng provided, use those
    if request.lat and request.lng:
        return request.lat, request.lng, f"Custom ({request.lat}, {request.lng})"

    # Look up city
    city_data = get_city_coordinates(request.city)
    if city_data:
        return city_data["lat"], city_data["lng"], city_data["label"]

    # City not found
    return None, None, None


@router.get("/cities", response_model=CityListResponse)
def list_cities():
    """Return all supported city names."""
    cities = get_all_cities()
    return CityListResponse(total=len(cities), cities=cities)


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_restaurant(request: ScrapeRequest):
    """
    Scrape a restaurant's menu from Swiggy.

    Pass city name (e.g. "mumbai", "bangalore", "pune")
    or custom lat/lng for any location.
    """
    # Resolve location
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
                error=result["error"],
            )

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")

        return ScrapeResponse(
            success=True,
            city_used=city_label,
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
            error=f"City '{request.city}' not found. Use GET /api/cities to see supported cities.",
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
                error=result["error"],
            )

        menu_df = result["menu_df"]
        menu_items = menu_df.to_dict(orient="records")

        return ScrapeResponse(
            success=True,
            city_used=city_label,
            restaurant_info=result["restaurant_info"],
            inferred=result["inferred"],
            menu_items=menu_items,
            total_items=len(menu_items),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
