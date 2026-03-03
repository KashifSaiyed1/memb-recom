# app/models.py

from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    restaurant_name: str = Field(..., min_length=1, example="The Blue Oven")
    city: str = Field(default="ahmedabad", example="ahmedabad")

    # Optional: override with custom lat/lng (takes priority over city)
    lat: str | None = Field(default=None, example="23.0225")
    lng: str | None = Field(default=None, example="72.5714")


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
    restaurant_info: dict | None = None
    inferred: InferredAttributes | None = None
    menu_items: list[dict] = []
    total_items: int = 0
    error: str | None = None


class CityListResponse(BaseModel):
    total: int
    cities: list[str]
