import streamlit as st
import requests
import pandas as pd
import time
import re
from bs4 import BeautifulSoup

# ---------------- CONFIG ----------------
API_KEY = "AIzaSyDUI3NB0HF8f64Y4D1_fg0ix6HgQvee69U"  # Replace with your actual Google API key

PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Top 10 cities by population in each state (trimmed to 10 for performance)
TOP_CITIES_BY_STATE = {
    "Ohio": ["Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron", "Dayton", "Parma", "Canton", "Youngstown", "Lorain"],
    "California": ["Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno", "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim"],
    "Texas": ["Houston", "San Antonio", "Dallas", "Austin", "Fort Worth", "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo"],
    # Add all other states here...
}

# Full list of U.S. states
ALL_STATES = sorted(TOP_CITIES_BY_STATE.keys())
# ----------------------------------------

st.title("Lead Finder – CGS Imaging")

business_type = st.text_input("Enter business type (e.g., cemetery, funeral home, school):")
selected_state = st.selectbox("Choose a U.S. state:", ALL_STATES)

def get_email_from_website(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=5, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", soup.text)
        return emails[0] if emails else ""
    except:
        return ""

if st.button("Search"):
    if not business_type or not selected_state:
        st.warning("Please enter a business type and select a state.")
    else:
        all_data = []
        cities = TOP_CITIES_BY_STATE.get(selected_state, [])

        st.info(f"Searching {business_type} businesses in {selected_state} across {len(cities)} cities...")

        for city in cities:
            st.write(f"🔍 Searching {city}...")
            query = f"{business_type} in {city}, {selected_state}"

            params = {"query": query, "key": API_KEY}
            res = requests.get(PLACES_URL, params=params)
            data = res.json()
            places = data.get("results", [])

            # Pagination support (up to 3 pages)
            page = 1
            while "next_page_token" in data and page < 3:
                time.sleep(2)  # token delay
                res = requests.get(PLACES_URL, params={"pagetoken": data["next_page_token"], "key": API_KEY})
                data = res.json()
                places.extend(data.get("results", []))
                page += 1

            for place in places:
                place_id = place.get("place_id")
                name = place.get("name")
                address = place.get("formatted_address")

                # Fetch phone and website
                details_res = requests.get(DETAILS_URL, params={"place_id": place_id, "key": API_KEY})
                details = details_res.json().get("result", {})
                phone = details.get("formatted_phone_number", "")
                website = details.get("website", "")
                email = get_email_from_website(website) if website else ""

                all_data.append({
                    "Business Name": name,
                    "Address": address,
                    "Phone": phone,
                    "Website": website,
                    "Email": email
                })

        # Show & export data
        df = pd.DataFrame(all_data).drop_duplicates(subset="Business Name")

        if df.empty:
            st.info("No results found.")
        else:
            st.success(f"Found {len(df)} businesses!")
            st.dataframe(df)
            st.download_button("Download CSV", data=df.to_csv(index=False), file_name="leads.csv", mime="text/csv")