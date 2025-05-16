import streamlit as st
import pandas as pd
import requests
import re
import time
import io
import os
import hashlib
import json
from dotenv import load_dotenv
from search import search_places, get_place_details
from enrich import scrape_contact_info_from_site, extract_email_from_text, extract_name_and_title_from_text
load_dotenv()

# --- Persistent API usage tracking ---
USAGE_FILE = "usage_log.txt"

def load_api_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r") as f:
            return int(f.read().strip())
    return 0

def save_api_usage(count):
    with open(USAGE_FILE, "w") as f:
        f.write(str(count))

# Load persistent usage at startup (initialize to 39 if file not present)
if "api_calls" not in st.session_state:
    usage = load_api_usage()
    if usage == 0:
        usage = 39
    st.session_state.api_calls = usage

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "table"

st.set_page_config(page_title="Direct Contact Search")

PAGES = {
    "Lead Finder": "🔍 Lead Finder",
    "Instructions": "❓ Help"
}

# Remove or comment out the old selectbox:
# page = st.sidebar.selectbox("Select a page", list(PAGES.keys()), format_func=lambda x: PAGES[x])

# Restore vertical sidebar button navigation for clarity
st.sidebar.markdown("### Navigation")

if "page" not in st.session_state:
    st.session_state.page = "Lead Finder"

if st.sidebar.button("🔍 Lead Finder"):
    st.session_state.page = "Lead Finder"
if st.sidebar.button("❓ Help"):
    st.session_state.page = "Instructions"

page = st.session_state.page

if page == "Instructions":
    st.title("❓ Help")
    st.markdown("""
    Welcome to the **Lead Finder & Contact Search Tool** — built to help marketing and sales teams identify qualified business leads and find the right people to contact.

    ### ✅ How to Use:

    1. **Go to 🔍 Lead Finder**
       - Enter a business type (e.g., "dentist", "funeral home")
       - Select one or more states
       - Optionally set filters or adjust how many cities to search
       - Click **Search**
       - Download either all leads or just new ones

    2. **Go to 📇 Direct Contact Search**
       - Upload your downloaded CSV
       - Click **Start Email Scraping**
       - The tool will enrich leads with:
         - Contact names
         - Likely emails
         - LinkedIn search links
         - Confidence scores
       - Download the enriched list

    ---

    ### ❓ FAQ

    **Q: Will this tool find every business in a state?**  
    A: No — it finds top results using Google’s Places API. It’s designed for quality and speed, not exhaustive scraping.

    **Q: Why are some emails blank?**  
    A: If the tool can’t find a direct contact or a usable format, it leaves the field blank or falls back to a scraped general email.

    **Q: What’s a LinkedIn search link?**  
    A: It opens a Google search targeting LinkedIn profiles based on the contact’s name and company.

    **Q: How do I know if an email is good?**  
    A: Use the **Confidence Score** field and avoid emails marked as fallback-only or low confidence.

    **Q: How many leads can I get per month?**  
    A: The free tier supports up to ~11,000 API calls/month. Your usage is tracked below.

    ---

    Built by **Olivia Burnett**
    """, unsafe_allow_html=True)

import re as _re

# --- Helper function for filename creation ---
def get_contact_page_url(website):
    if pd.isna(website) or not str(website).startswith("http"):
        return ""
    return website.rstrip("/") + "/contact"

def create_filename(prefix, business_type, states, is_new=False):
    import re
    clean_type = re.sub(r'\W+', '_', business_type.strip().lower())
    clean_states = "_".join([s.replace(" ", "") for s in states])
    suffix = f"{clean_type}_in_{clean_states}.csv"
    return f"{'new_' if is_new else ''}{prefix}_{suffix}"

if page == "Lead Finder":
    # --- Test Mode Checkbox ---
    test_mode = st.sidebar.checkbox("🧪 Enable Test Mode (for fast testing)")
    st.title("🔍 Lead Finder")
    st.markdown("<p style='color:#888;'>Enter a type of business and select the states you'd like to search. This tool will generate a list of relevant businesses using the Google Maps API.</p>", unsafe_allow_html=True)

    if "search_history" not in st.session_state:
        st.session_state.search_history = []

    business_type = st.text_input("Enter a type of business (e.g., cemetery, funeral home, school)")

    states = st.multiselect("Select one or more U.S. states:", [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
        "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
        "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
        "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
        "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
        "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
    ])

    st.markdown("**Only include leads that:**")
    has_phone = st.checkbox("Has Phone Number")
    has_website = st.checkbox("Has Website")
    lead_filters = []
    if has_phone:
        lead_filters.append("Has Phone Number")
    if has_website:
        lead_filters.append("Has Website")

    if business_type and states:
        search_summary = f"{business_type.title()} in {', '.join(states)}"
        if search_summary not in st.session_state.search_history:
            st.session_state.search_history.append(search_summary)

    # Add search_depth logic with test mode
    if test_mode:
        search_depth = 3
    else:
        search_depth = st.slider(
            "Search Depth (cities per state)",
            min_value=1,
            max_value=25,
            value=5,
            help="Select how many top cities in each state to search for this business type."
        )

    # Pagination option (default to False)
    paginate_results = st.checkbox(
        "📄 Use Pagination (up to 3 pages of results)",
        value=False,
        help="This will increase API usage but return more leads per search."
    )

    # Top 25 cities per state (abbreviated for brevity; in practice, should be full 25 for each)
    TOP_CITIES_PER_STATE = {
        "Alabama": ["Birmingham", "Montgomery", "Mobile", "Huntsville", "Tuscaloosa", "Hoover", "Dothan", "Auburn", "Decatur", "Madison", "Florence", "Gadsden", "Vestavia Hills", "Prattville", "Phenix City", "Alabaster", "Bessemer", "Enterprise", "Opelika", "Homewood", "Northport", "Anniston", "Athens", "Daphne", "Pelham"],
        "Alaska": ["Anchorage", "Fairbanks", "Juneau", "Sitka", "Ketchikan", "Wasilla", "Kenai", "Kodiak", "Bethel", "Palmer", "Homer", "Unalaska", "Barrow", "Soldotna", "Valdez", "Nome", "Kotzebue", "Petersburg", "Seward", "Wrangell", "Dillingham", "Cordova", "North Pole", "Houston", "Craig"],
        "Arizona": ["Phoenix", "Tucson", "Mesa", "Chandler", "Glendale", "Scottsdale", "Gilbert", "Tempe", "Peoria", "Surprise", "Yuma", "Avondale", "Goodyear", "Flagstaff", "Buckeye", "Lake Havasu City", "Casa Grande", "Sierra Vista", "Maricopa", "Oro Valley", "Prescott", "Bullhead City", "Prescott Valley", "Apache Junction", "Queen Creek"],
        "Arkansas": ["Little Rock", "Fort Smith", "Fayetteville", "Springdale", "Jonesboro", "North Little Rock", "Conway", "Rogers", "Pine Bluff", "Bentonville", "Hot Springs", "Benton", "Sherwood", "Texarkana", "Russellville", "Bella Vista", "Paragould", "Cabot", "West Memphis", "Searcy", "Van Buren", "Bryant", "Siloam Springs", "El Dorado", "Forrest City"],
        # ... (add all states as needed)
        "California": ["Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno", "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim", "Santa Ana", "Riverside", "Stockton", "Irvine", "Chula Vista", "Fremont", "San Bernardino", "Modesto", "Oxnard", "Fontana", "Moreno Valley", "Glendale", "Huntington Beach", "Santa Clarita", "Garden Grove"],
        "New York": ["New York", "Buffalo", "Rochester", "Yonkers", "Syracuse", "Albany", "New Rochelle", "Mount Vernon", "Schenectady", "Utica", "White Plains", "Hempstead", "Troy", "Niagara Falls", "Binghamton", "Freeport", "Valley Stream", "Long Beach", "Rome", "North Tonawanda", "Poughkeepsie", "Jamestown", "Ithaca", "Elmira", "Newburgh"],
        # ... (continue for all states)
        # Fallback for states not listed
    }

    if st.session_state.search_history:
        st.markdown("### Recent Searches")
        st.markdown("<ul>" + "".join([f"<li>{query}</li>" for query in st.session_state.search_history[-5:]]) + "</ul>", unsafe_allow_html=True)

    if st.button("Search"):
        if not business_type or not states:
            st.warning("Please enter a business type and select at least one state.")
        else:
            # Gate for API usage limit
            API_LIMIT = 11000
            if st.session_state.api_calls >= API_LIMIT:
                st.error(f"🚫 API usage limit ({API_LIMIT:,}) reached for the month. Please try again after your usage resets.")
                st.stop()
            API_KEY = os.getenv("GOOGLE_API_KEY")


            leads = []

            with st.spinner(f"⏳ Searching... this may take some time."):
                search_terms = [business_type]
                # Only expand variants if not in test mode
                if not test_mode:
                    if "dentist" in business_type.lower():
                        search_terms.extend(["dental office", "dental clinic", "family dentist"])
                    elif "school" in business_type.lower():
                        search_terms.extend(["elementary school", "middle school", "high school", "academy"])

                for state in states:
                    # Get top N cities for the state, fallback to state name if not found
                    state_cities = TOP_CITIES_PER_STATE.get(state, [state])
                    cities_to_search = state_cities[:search_depth] if len(state_cities) >= search_depth else state_cities
                    for city in cities_to_search:
                        for term in search_terms:
                            with st.spinner(f"Searching {term} in {city}, {state}..."):
                                # Smart caching: normalize common business types
                                normalization_map = {
                                    "dental office": "dentist",
                                    "dental clinic": "dentist",
                                    "family dentist": "dentist",
                                    "elementary school": "school",
                                    "middle school": "school",
                                    "high school": "school",
                                    "academy": "school"
                                }
                                normalized_term = normalization_map.get(term.lower(), term.lower())

                                cache_key = f"{normalized_term}_{city.lower().replace(' ', '')}_{state.lower().replace(' ', '')}"
                                cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
                                cache_path = os.path.join("cache", f"{cache_hash}.json")

                                if not os.path.exists("cache"):
                                    os.makedirs("cache")

                                if os.path.exists(cache_path):
                                    with open(cache_path, "r") as f:
                                        query_results = json.load(f)
                                else:
                                    query_results = search_places(term, f"{city}, {state}", API_KEY, use_pagination=paginate_results)
                                    with open(cache_path, "w") as f:
                                        json.dump(query_results, f)
                                    st.session_state.api_calls += 1
                                    save_api_usage(st.session_state.api_calls)
                                # for result in query_results:
                                for result in query_results:
                                    place_id = result.get("place_id")
                                    phone = ""
                                    website = ""
                                    if place_id:
                                        details = get_place_details(place_id, API_KEY)
                                        phone = details.get("formatted_phone_number", "")
                                        website = details.get("website", "")
                                    leads.append({
                                        "Business Name": result.get("name", ""),
                                        "Phone": phone,
                                        "Website": website,
                                        "Address": result.get("formatted_address", "")
                                    })
                                    time.sleep(1)

            df = pd.DataFrame(leads)

            # Deduplicate
            df.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
            df.reset_index(drop=True, inplace=True)

            # Apply filters
            if "Has Phone Number" in lead_filters:
                df = df[df["Phone"].notna() & df["Phone"].str.strip().ne("")]
            if "Has Website" in lead_filters:
                df = df[df["Website"].notna() & df["Website"].str.strip().ne("")]

            archive_file = "lead_archive.csv"

            if os.path.exists(archive_file):
                archive_df = pd.read_csv(archive_file)
            else:
                archive_df = pd.DataFrame(columns=["Business Name", "Phone", "Website", "Address"])

            if not df.empty and len(df.columns) > 0:
                df["Status"] = df.apply(
                    lambda row: "Already Harvested" if (
                        ((archive_df["Business Name"] == row["Business Name"]) &
                         (archive_df["Phone"] == row["Phone"]) &
                         (archive_df["Website"] == row["Website"])).any()
                    ) else "New",
                    axis=1
                )

                new_leads_to_add = df[df["Status"] == "New"]

                st.success(f"Found {len(df)} leads ({(df['Status'] == 'New').sum()} new, {(df['Status'] == 'Already Harvested').sum()} previously harvested).")
                # Remove LinkedIn Search column from display if present
                display_df = df.copy()
                if "LinkedIn Search" in display_df.columns:
                    display_df = display_df.drop(columns=["LinkedIn Search"])
                st.dataframe(display_df)

                # --- Construct export filenames ---
                filename_all = create_filename("leads", business_type, states)
                filename_new = create_filename("leads", business_type, states, is_new=True)

                # Download All Leads button and archive update
                if st.download_button("📥 Download All Leads", display_df.to_csv(index=False), file_name=filename_all, mime="text/csv"):
                    new_leads_to_add = display_df[display_df["Status"] == "New"]
                    updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                    updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                    updated_archive.to_csv(archive_file, index=False)

                # Download Only New Leads button and archive update
                if st.download_button("🆕 Download Only New Leads", new_leads_to_add.to_csv(index=False), file_name=filename_new, mime="text/csv"):
                    updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                    updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                    updated_archive.to_csv(archive_file, index=False)

                # Save results to session state for persistent view
                st.session_state.lead_results = df
            else:
                st.warning("⚠️ No leads were found. Please check your search term or selected states.")


#
# ---- Sidebar Lead Summary ----
if "lead_results" in st.session_state:
    df = st.session_state.lead_results
    new_count = (df["Status"] == "New").sum()
    existing_count = (df["Status"] == "Already Harvested").sum()

    st.sidebar.markdown("### 📊 Lead Summary")
    st.sidebar.markdown(f"- Total Leads: **{len(df)}**")
    st.sidebar.markdown(f"- 🆕 New: **{new_count}**")
    st.sidebar.markdown(f"- ♻️ Already Harvested: **{existing_count}**")


# ---- API usage tracker (simple text version) ----
API_LIMIT = 11000
api_usage = st.session_state.api_calls
st.sidebar.markdown(f"**API Usage:** {api_usage:,} / {API_LIMIT:,}")
if api_usage >= API_LIMIT:
    st.sidebar.error("🚫 Monthly API limit reached!")

# Footer attribution (default Streamlit style)
st.sidebar.markdown("---")
st.sidebar.markdown("Built by Olivia Burnett")
def extract_emails_from_text(text):
    obfuscated_patterns = [
        r'[\w\.-]+@[\w\.-]+\.\w+',
        r'[\w\.-]+\s?\[\s?at\s?\]\s?[\w\.-]+\s?\[\s?dot\s?\]\s?\w+',
        r'[\w\.-]+\s?\(?\s?at\s?\)?\s?[\w\.-]+\s?\(?\s?dot\s?\)?\s?\w+'
    ]
    emails = []
    for pattern in obfuscated_patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for match in matches:
            cleaned = (match
                       .replace("[at]", "@")
                       .replace("(at)", "@")
                       .replace(" at ", "@")
                       .replace("[dot]", ".")
                       .replace("(dot)", ".")
                       .replace(" dot ", ".")
                       .replace(" ", "")
                       .strip())
            if cleaned not in emails:
                emails.append(cleaned)
    return emails