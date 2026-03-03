# app/service.py

import json
import pandas as pd

from app.scraper import fetch_menu
from app.extractor import extract_restaurant_info
from app.parser import parse_menu
from app.inference import infer_restaurant_attributes
from app import DEFAULT_LAT, DEFAULT_LNG, DEFAULT_CITY


async def process_restaurant(
    restaurant_name: str,
    lat: str = DEFAULT_LAT,
    lng: str = DEFAULT_LNG,
    city_label: str = DEFAULT_CITY,
    save_csv: bool = True,
    save_json: bool = True,
) -> dict:
    """
    End-to-end pipeline:
      1. Scrape menu JSON from Swiggy
      2. Extract restaurant metadata
      3. Parse menu items
      4. Infer business attributes
      5. Save CSV + JSON

    Returns a dict with: restaurant_info, inferred, menu_df, summary
    """
    # ── Step 1: Scrape ──
    menu_json = await fetch_menu(restaurant_name, lat=lat, lng=lng, city_label=city_label)

    if not menu_json:
        print("❌ Menu not captured.")
        return {"error": "Menu not captured"}

    # ── Step 2: Parse menu items ──
    menu_items = parse_menu(menu_json)

    if not menu_items:
        # Save raw JSON for debugging
        debug_path = f"{_safe_filename(restaurant_name)}_debug.json"
        with open(debug_path, "w") as f:
            json.dump(menu_json, f, indent=2)
        print(f"❌ No items found. Raw JSON saved as {debug_path}")
        return {"error": "No menu items found", "debug_file": debug_path}

    # ── Step 3: Extract restaurant metadata ──
    restaurant_info = extract_restaurant_info(menu_json)
    _print_restaurant_info(restaurant_info)

    # ── Step 4: Infer business attributes ──
    inferred = infer_restaurant_attributes(restaurant_info, menu_items)

    # ── Step 5: Build DataFrame ──
    df = pd.DataFrame(menu_items)
    for key, value in inferred.items():
        df[key] = value

    # ── Step 6: Build summary ──
    summary = {
        "Restaurant Name": restaurant_info.get("name", restaurant_name),
        "Cuisines (Swiggy)": ", ".join(restaurant_info.get("cuisines", [])),
        "Cost for Two (Swiggy)": restaurant_info.get("costForTwoMessage", ""),
        "Rating": restaurant_info.get("avgRating", ""),
        "Total Ratings": restaurant_info.get("totalRatingsString", ""),
        "Area": restaurant_info.get("areaName", ""),
        "City": restaurant_info.get("city", ""),
        **inferred,
    }

    _print_summary(summary)

    # ── Step 7: Save files ──
    base_name = _safe_filename(restaurant_name)

    if save_csv:
        csv_path = f"{base_name}_menu.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n💾 Menu saved as {csv_path} ({len(df)} items)")

    if save_json:
        json_path = f"{base_name}_summary.json"
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"💾 Summary saved as {json_path}")

    return {
        "restaurant_info": restaurant_info,
        "inferred": inferred,
        "menu_df": df,
        "summary": summary,
    }


# ── Helpers ──

def _safe_filename(name: str) -> str:
    return name.strip().replace(" ", "_").replace("/", "_")


def _print_restaurant_info(info: dict):
    print(f"\n📊 Restaurant: {info.get('name', 'Unknown')}")
    print(f"   Cuisines: {', '.join(info.get('cuisines', []))}")
    print(f"   Cost for Two: {info.get('costForTwoMessage', 'N/A')}")
    print(f"   Rating: {info.get('avgRating', 'N/A')}")


def _print_summary(summary: dict):
    print("\n" + "=" * 60)
    print("📊 RESTAURANT ANALYSIS")
    print("=" * 60)
    for k, v in summary.items():
        print(f"   {k}: {v}")
    print("=" * 60)
