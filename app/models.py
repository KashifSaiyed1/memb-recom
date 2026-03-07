# app/models.py

from pydantic import BaseModel, Field


# ── Suggest (Google Places) ──

class SuggestRequest(BaseModel):
    query: str = Field(..., min_length=1, example="Tanatan Juhu Mumbai")


class PlaceSuggestion(BaseModel):
    place_id: str
    name: str
    address: str
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    total_ratings: int | None = None


class SuggestResponse(BaseModel):
    success: bool
    results: list[PlaceSuggestion] = []
    error: str | None = None


# ── Scrape (existing flow: Swiggy search) ──

class ScrapeRequest(BaseModel):
    restaurant_name: str = Field(..., min_length=1, example="The Blue Oven")
    city: str = Field(default="ahmedabad", example="ahmedabad")
    lat: str | None = Field(default=None, example="23.0225")
    lng: str | None = Field(default=None, example="72.5714")


# ── Scrape via Google Maps (new flow: place_id → Swiggy link → menu) ──

class GmapsScrapeRequest(BaseModel):
    place_id: str = Field(..., min_length=1, example="ChIJN1t_tDeuEmsRUsoyG83frY4")
    name: str = Field(default="", example="Tanatan Juhu - Kitchen & Bar")
    address: str = Field(default="", example="462, AB Nair Rd, Juhu, Mumbai, Maharashtra 400049, India")
    lat: float | str | None = Field(default=None, example="19.0760")
    lng: float | str | None = Field(default=None, example="72.8777")


# ── Shared response models ──

class InferredAttributes(BaseModel):
    business_category: str
    cuisine_type: str
    price_range: str
    estimated_visit_frequency_per_month: float
    gross_margin_percent: int
    ambiance: str


class ScrapeResponse(BaseModel):
    success: bool
    city_used: str | None = None
    menu_source: str | None = None  # "structured" or "image_ocr"
    scrape_method: str | None = None  # "swiggy_search" or "google_maps"
    restaurant_info: dict | None = None
    inferred: InferredAttributes | None = None
    menu_items: list[dict] = []
    total_items: int = 0
    swiggy_url: str | None = None
    error: str | None = None


class CityListResponse(BaseModel):
    total: int
    cities: list[str]