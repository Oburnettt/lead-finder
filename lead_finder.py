import streamlit as st
import requests
import pandas as pd
import time
import re
from bs4 import BeautifulSoup

# ---------------- CONFIG ----------------
API_KEY = "AIzaSyAtZ7wTYzP6Iju47dJGuuxD49KOzPDAQdY"  # Replace with your actual Google API key

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
    text_search_count = 0
    place_details_count = 0
    if not business_type or not selected_state:
        st.warning("Please enter a business type and select a state.")
    else:
        all_data = []
        cities = TOP_CITIES_BY_STATE.get(selected_state, [])

        st.info(f"Searching {business_type} businesses in {selected_state} across {len(cities)} cities...")

        def is_website_likely_correct(business_name, website_url):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(website_url, timeout=5, headers=headers)
                return business_name.lower() in res.text.lower()
            except:
                return False

        for city in cities:
            st.write(f"🔍 Searching {city}...")
            query = f"{business_type} in {city}, {selected_state}"

            params = {"query": query, "key": API_KEY}
            res = requests.get(PLACES_URL, params=params)
            text_search_count += 1
            data = res.json()
            places = data.get("results", [])

            # Pagination support (up to 3 pages)
            page = 1
            while "next_page_token" in data and page < 3:
                time.sleep(2)  # token delay
                res = requests.get(PLACES_URL, params={"pagetoken": data["next_page_token"], "key": API_KEY})
                text_search_count += 1
                data = res.json()
                places.extend(data.get("results", []))
                page += 1

            for place in places:
                place_id = place.get("place_id")
                name = place.get("name")
                address = place.get("formatted_address")

                # Fetch phone and website
                details_res = requests.get(DETAILS_URL, params={"place_id": place_id, "key": API_KEY})
                place_details_count += 1
                details = details_res.json().get("result", {})
                phone = details.get("formatted_phone_number", "")
                website = details.get("website", "")

                def clean_url(url):
                    if pd.isna(url) or not isinstance(url, str) or url.strip() == "":
                        return ""
                    url = url.strip()
                    if not url.startswith("http"):
                        url = "http://" + url
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        return f"{parsed.scheme}://{parsed.netloc}"
                    except:
                        return url

                website = clean_url(website)
                is_verified = is_website_likely_correct(name, website) if website else False
                email = get_email_from_website(website) if website else ""

                all_data.append({
                    "Business Name": name,
                    "Address": address,
                    "Phone": phone,
                    "Website": website,
                    "Email": email,
                    "Verified Website Match": is_verified
                })

        # Show & export data
        df = pd.DataFrame(all_data).drop_duplicates(subset="Business Name")

        # Clean and filter URLs
        df = df[df["Website"] != ""]

        if df.empty:
            st.info("No results found.")
        else:
            # --- API usage counters ---

            with st.expander("📊 Lead Summary", expanded=True):
                st.markdown("---")
                BASE_CREDIT = 300.00  # reset starting credit
                cost_per_text_search = 0.002  # $0.002 per text search
                cost_per_details_request = 0.002  # $0.002 per details lookup

                text_search_cost = text_search_count * cost_per_text_search
                details_cost = place_details_count * cost_per_details_request
                total_cost = text_search_cost + details_cost
                remaining_credit = BASE_CREDIT - total_cost

                st.markdown(f"**Text Search Requests:** {text_search_count} (${text_search_cost:.2f})")
                st.markdown(f"**Place Details Requests:** {place_details_count} (${details_cost:.2f})")
                st.markdown(f"**Total API Usage Cost:** ${total_cost:.2f}")
                st.markdown(f"**Remaining Credit Estimate:** ~${remaining_credit:.2f} USD")

                st.markdown("---")
                st.caption("Built by Olivia Burnett")

            st.success(f"Found {len(df)} businesses!")
            st.dataframe(df)
            st.download_button("Download CSV", data=df.to_csv(index=False), file_name="leads.csv", mime="text/csv")