import time
import requests

def search_places(query, location, api_key, use_pagination=False):
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"{query} in {location}",
        "key": api_key
    }
    results = []
    for _ in range(3 if use_pagination else 1):
        response = requests.get(url, params=params)
        data = response.json()
        results.extend(data.get("results", []))
        if "next_page_token" in data:
            params["pagetoken"] = data["next_page_token"]
            time.sleep(2)
        else:
            break
    return results

def get_place_details(place_id, api_key):
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number,website",
        "key": api_key
    }
    response = requests.get(details_url, params=params)
    if response.status_code == 200:
        return response.json().get("result", {})
    return {}