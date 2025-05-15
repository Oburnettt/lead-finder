import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import os
from dotenv import load_dotenv
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
    "Email Scraper": "📇 Direct Contact Search",
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
if st.sidebar.button("📇 Direct Contact Search"):
    st.session_state.page = "Email Scraper"
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
def create_filename(prefix, business_type, states, is_new=False):
    import re
    clean_type = re.sub(r'\W+', '_', business_type.strip().lower())
    clean_states = "_".join([s.replace(" ", "") for s in states])
    suffix = f"{clean_type}_in_{clean_states}.csv"
    return f"{'new_' if is_new else ''}{prefix}_{suffix}"

if page == "Lead Finder":
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

    # Add search_depth slider for top N cities per state
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
                        time.sleep(2)  # Required delay for next_page_token to activate
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

            leads = []

            with st.spinner(f"⏳ Searching... this may take some time."):
                search_terms = [business_type]
                if "dentist" in business_type.lower():
                    search_terms.extend(["dental office", "dental clinic", "family dentist"])  # Example variant expansion
                elif "school" in business_type.lower():
                    search_terms.extend(["elementary school", "middle school", "high school", "academy"])

                for state in states:
                    # Get top N cities for the state, fallback to state name if not found
                    state_cities = TOP_CITIES_PER_STATE.get(state, [state])
                    cities_to_search = state_cities[:search_depth] if len(state_cities) >= search_depth else state_cities
                    for city in cities_to_search:
                        for term in search_terms:
                            with st.spinner(f"Searching {term} in {city}, {state}..."):
                                query_results = search_places(term, f"{city}, {state}", API_KEY, use_pagination=paginate_results)
                                st.session_state.api_calls += 1
                                save_api_usage(st.session_state.api_calls)
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

                # ---- Always display as DataFrame preview (CSV-like format) ----
                if "lead_results" in st.session_state:
                    df = st.session_state.lead_results
                    st.dataframe(df)
            else:
                st.warning("⚠️ No leads were found. Please check your search term or selected states.")

elif page == "Email Scraper":
    st.title("📇 Direct Contact Search")
    uploaded_file = st.file_uploader(
        "Upload a CSV file of leads to find direct contacts, emails, and contact pages.",
        type=["csv"]
    )
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.success(f"✅ Loaded {len(df)} rows.")
            st.write("📊 Preview:", df.head())

            if "Website" not in df.columns:
                st.error("❌ The uploaded CSV does not contain a 'Website' column.")
            else:
                if st.button("🔍 Start Email Scraping"):
                    import openai
                    openai_api_key = os.getenv("OPENAI_API_KEY")
                    if not openai_api_key:
                        openai_api_key = st.text_input("Enter your OpenAI API Key", type="password")
                        if openai_api_key:
                            os.environ["OPENAI_API_KEY"] = openai_api_key
                    openai.api_key = os.getenv("OPENAI_API_KEY")

                    # Remove unused enrichment options UI

                    contact_names = []
                    job_titles = []
                    direct_emails = []
                    fallback_used = []
                    contact_page_urls = []

                    # Helper to extract email addresses from a web page
                    def extract_emails_from_text(text):
                        return re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)

                    # Helper to perform Google search and parse result text for contact info
                    def google_search_and_extract_contact(query):
                        from googlesearch import search
                        headers = {"User-Agent": "Mozilla/5.0"}
                        # Try up to 5 results
                        for url in search(query, num_results=5, advanced=True):
                            url_lower = url.lower()
                            # Only look at likely contact/people/leadership/about/team pages
                            if any(x in url_lower for x in ["contact", "team", "leadership", "about", "staff"]):
                                try:
                                    res = requests.get(url, timeout=8, headers=headers)
                                    if res.status_code == 200:
                                        soup = BeautifulSoup(res.text, "html.parser")
                                        for s in soup(["script", "style"]):
                                            s.decompose()
                                        text = soup.get_text(separator=" ", strip=True)
                                        # Try to find Owner, Marketing Director, or General Manager in the text
                                        contact_priority = [("Owner",), ("Marketing Director",), ("General Manager",)]
                                        found_contacts = []
                                        for pri_titles in contact_priority:
                                            pattern = r"([A-Z][a-z]+ [A-Z][a-z]+)[^\n]{0,40}(" + "|".join([re.escape(t) for t in pri_titles]) + r")[^\n]{0,40}([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})?"
                                            matches = re.findall(pattern, text)
                                            for match in matches:
                                                name = match[0]
                                                title = match[1]
                                                email = match[2] if match[2] else ""
                                                found_contacts.append((name, title, email))
                                            if found_contacts:
                                                # Return the first found for this priority
                                                return found_contacts[0][0], found_contacts[0][1], found_contacts[0][2]
                                        # If not found with above, try line-by-line fallback
                                        lines = text.splitlines()
                                        for pri_titles in contact_priority:
                                            for line in lines:
                                                for pri in pri_titles:
                                                    if pri.lower() in line.lower():
                                                        name_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", line)
                                                        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line)
                                                        name = name_match.group(1) if name_match else ""
                                                        email = email_match.group(0) if email_match else ""
                                                        return name, pri, email
                                        # Fallback: just extract any email
                                        emails = extract_emails_from_text(text)
                                        if emails:
                                            return "", "", emails[0]
                                except Exception:
                                    continue
                        return "", "", ""

                    # Helper to get the business contact page URL
                    def get_contact_page_url(website):
                        if not isinstance(website, str) or not website:
                            return ""
                        # Try contact page
                        for suffix in ["/contact", "/contact-us", "/about", "/team"]:
                            url = website.rstrip("/") + suffix
                            try:
                                r = requests.get(url, timeout=5)
                                if r.status_code == 200:
                                    return url
                            except Exception:
                                continue
                        # Fallback to website itself
                        return website

                    progress = st.progress(0)
                    for i, row in df.iterrows():
                        website = row.get("Website", "")
                        business_name = row.get("Business Name", "")
                        address = row.get("Address", "")
                        found_name = ""
                        found_title = ""
                        found_email = ""
                        used_fallback = "N"
                        contact_page_url = ""
                        # If website missing or invalid, mark all as not found
                        if pd.isna(website) or not str(website).startswith("http"):
                            contact_names.append("")
                            job_titles.append("")
                            direct_emails.append("")
                            fallback_used.append("Y")
                            contact_page_urls.append("")
                            progress.progress((i + 1) / len(df))
                            continue
                        # Build prioritized search queries
                        location = ""
                        if pd.notna(address):
                            location = address
                        queries = [
                            f'Owner of {business_name} {location}',
                            f'Marketing Director of {business_name} {location}',
                            f'General Manager of {business_name} {location}',
                            f'Contact {business_name} {location}',
                        ]
                        for query in queries:
                            name, title, email = google_search_and_extract_contact(query)
                            if email:
                                found_email = email
                                found_name = name
                                found_title = title
                                break
                        if found_email:
                            used_fallback = "N"
                            contact_page_url = ""
                        else:
                            # Fallback: try to extract any email from the website contact/about page
                            try:
                                headers = {"User-Agent": "Mozilla/5.0"}
                                for suffix in ["/contact", "/about", "/team"]:
                                    url = website.rstrip("/") + suffix
                                    r = requests.get(url, timeout=6, headers=headers)
                                    if r.status_code == 200:
                                        soup = BeautifulSoup(r.text, "html.parser")
                                        for s in soup(["script", "style"]):
                                            s.decompose()
                                        text = soup.get_text(separator=" ", strip=True)
                                        emails = extract_emails_from_text(text)
                                        if emails:
                                            found_email = emails[0]
                                            used_fallback = "Y"
                                            break
                                if not found_email:
                                    # Try homepage
                                    r = requests.get(website, timeout=6, headers=headers)
                                    if r.status_code == 200:
                                        soup = BeautifulSoup(r.text, "html.parser")
                                        for s in soup(["script", "style"]):
                                            s.decompose()
                                        text = soup.get_text(separator=" ", strip=True)
                                        emails = extract_emails_from_text(text)
                                        if emails:
                                            found_email = emails[0]
                                            used_fallback = "Y"
                            except Exception:
                                pass
                            # Try to find a contact page URL even if no email found
                            contact_page_url = get_contact_page_url(website)
                        contact_names.append(found_name)
                        job_titles.append(found_title)
                        direct_emails.append(found_email)
                        fallback_used.append(used_fallback)
                        contact_page_urls.append(contact_page_url)
                        progress.progress((i + 1) / len(df))
                        time.sleep(1)

                    # Build output DataFrame in the specified column order
                    output_df = pd.DataFrame({
                        "Business Name": df.get("Business Name", ""),
                        "Website": df.get("Website", ""),
                        "Contact Name": contact_names,
                        "Job Title": job_titles,
                        "Direct Contact Email": direct_emails,
                        "Fallback Used (Y/N)": fallback_used,
                        "Business Contact Page URL": contact_page_urls,
                    })
                    output_df = output_df[
                        [
                            "Business Name",
                            "Website",
                            "Contact Name",
                            "Job Title",
                            "Direct Contact Email",
                            "Fallback Used (Y/N)",
                            "Business Contact Page URL",
                        ]
                    ]
                    output = io.StringIO()
                    output_df.to_csv(output, index=False)
                    output.seek(0)
                    st.success("✅ Scraping and enrichment complete. Download your file below.")
                    # --- Export filename logic for direct contact search ---
                    filename = uploaded_file.name
                    parts = filename.replace(".csv", "").split("_in_")
                    if len(parts) == 2:
                        biz, states = parts
                        enriched_name = f"direct_contacts_{states}_{biz}.csv"
                    else:
                        enriched_name = "direct_contacts_enriched.csv"
                    st.download_button(
                        "📥 Download CSV with Enriched Contacts",
                        output.getvalue(),
                        file_name=enriched_name,
                        mime="text/csv"
                    )
        except Exception as e:
            st.error(f"❌ Failed to read file: {e}")



# ---- API usage tracker (simple text version) ----
API_LIMIT = 11000
api_usage = st.session_state.api_calls
st.sidebar.markdown(f"**API Usage:** {api_usage:,} / {API_LIMIT:,}")
if api_usage >= API_LIMIT:
    st.sidebar.error("🚫 Monthly API limit reached!")

# Footer attribution (default Streamlit style)
st.sidebar.markdown("---")
st.sidebar.markdown("Built by Olivia Burnett")