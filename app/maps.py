import os
import requests


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


def search_store(store_name: str) -> dict:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {}

    payload = {
        "textQuery": store_name,
        "languageCode": "ja",
        "maxResultCount": 1,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.googleMapsUri,"
            "places.primaryTypeDisplayName"
        ),
    }

    try:
        resp = requests.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        places = data.get("places", [])
        if not places:
            return {}
        place = places[0]
        return {
            "store_name": place.get("displayName", {}).get("text", store_name),
            "address": place.get("formattedAddress", ""),
            "phone": place.get("nationalPhoneNumber", ""),
            "maps_url": place.get("googleMapsUri", ""),
            "business_type": place.get("primaryTypeDisplayName", {}).get("text", ""),
        }
    except Exception:
        return {}
