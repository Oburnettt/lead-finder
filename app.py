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

st.set_page_config(page_title="Email Scraper", layout="wide")

st.markdown("""
    <style>
    body {
        background-color: #0e1117;
        color: white;
    }
    .sidebar .sidebar-content {
        background: #1a1a1a;
    }
    .stSelectbox > div {
        background: #222;
        color: white;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

if "api_calls" not in st.session_state:
    st.session_state.api_calls = 0

st.sidebar.markdown("### 🧭 Navigation")
if "page" not in st.session_state:
    st.session_state.page = "Lead Finder"

if st.sidebar.button("🔍 Lead Finder"):
    st.session_state.page = "Lead Finder"
if st.sidebar.button("📧 Email Scraper"):
    st.session_state.page = "Email Scraper"
if st.sidebar.button("ℹ️ Instructions"):
    st.session_state.page = "Instructions"

page = st.session_state.page

if page == "Instructions":
    st.title("ℹ️ How to Use This Tool")
    st.markdown("""
    <p style='color:#bbb;'>
    Created by <strong>Olivia Burnett</strong>, this tool helps marketing and sales teams find business leads and extract contact emails all in one place.

    <br><br>
    <strong>Steps:</strong>
    <ol>
    <li>Go to the Lead Finder tab</li>
    <li>Enter a business type and select states</li>
    <li>Click Search and download your results</li>
    <li>Go to Email Scraper, upload the CSV, and scrape emails</li>
    </ol>
    </p>
    """, unsafe_allow_html=True)

elif page == "Lead Finder":
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

    st.sidebar.markdown("### 🧰 Optional Filters")
    lead_filters = st.sidebar.multiselect("Only include leads that:", ["Has Phone Number", "Has Website"])

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
            API_KEY = os.getenv("GOOGLE_API_KEY")

            def search_places(query, location, api_key):
                url = f"https://maps.googleapis.com/maps/api/place/textsearch/json"
                params = {
                    "query": f"{query} in {location}",
                    "key": api_key
                }
                response = requests.get(url, params=params)
                data = response.json()
                results = data.get("results", [])
                # Return results as is, with place_id included in each result
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
                                query_results = search_places(term, f"{city}, {state}", API_KEY)
                                st.session_state.api_calls += 1
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

                # Download All Leads button and archive update
                if st.download_button("📥 Download All Leads", display_df.to_csv(index=False), file_name="all_leads.csv", mime="text/csv"):
                    new_leads_to_add = display_df[display_df["Status"] == "New"]
                    updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                    updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                    updated_archive.to_csv(archive_file, index=False)

                # Download Only New Leads button and archive update
                if st.download_button("🆕 Download Only New Leads", new_leads_to_add.to_csv(index=False), file_name="new_leads_only.csv", mime="text/csv"):
                    updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                    updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                    updated_archive.to_csv(archive_file, index=False)
            else:
                st.warning("⚠️ No leads were found. Please check your search term or selected states.")

elif page == "Email Scraper":
    st.title("📧 Bulk Email Scraper")
    uploaded_file = st.file_uploader("Upload a CSV exported from the Lead Finder", type=["csv"])

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

                    emails = []
                    contact_names = []
                    job_titles = []
                    likely_emails = []
                    fallback_used = []

                    def extract_email_from_website(url):
                        try:
                            headers = {'User-Agent': 'Mozilla/5.0'}
                            res = requests.get(url, timeout=5, headers=headers)
                            soup = BeautifulSoup(res.text, 'html.parser')
                            emails_found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", soup.text)
                            return emails_found[0] if emails_found else ""
                        except Exception as e:
                            return ""

                    def fetch_best_page(url):
                        page_paths = ["about", "team", "contact"]
                        if not url.startswith("http"):
                            url = "http://" + url
                        for path in page_paths:
                            try_urls = [
                                url.rstrip("/") + "/" + path,
                                url.rstrip("/") + "/" + path.capitalize(),
                                url.rstrip("/") + "/" + path.title()
                            ]
                            for test_url in try_urls:
                                try:
                                    headers = {"User-Agent": "Mozilla/5.0"}
                                    res = requests.get(test_url, timeout=7, headers=headers)
                                    if res.status_code == 200 and len(res.text) > 200:
                                        soup = BeautifulSoup(res.text, "html.parser")
                                        for script in soup(["script", "style"]):
                                            script.decompose()
                                        text = soup.get_text(separator=" ", strip=True)
                                        if len(text) > 200:
                                            return text[:5000]
                                except Exception:
                                    continue
                        # Try root page as fallback
                        try:
                            headers = {"User-Agent": "Mozilla/5.0"}
                            res = requests.get(url, timeout=7, headers=headers)
                            if res.status_code == 200 and len(res.text) > 200:
                                soup = BeautifulSoup(res.text, "html.parser")
                                for script in soup(["script", "style"]):
                                    script.decompose()
                                text = soup.get_text(separator=" ", strip=True)
                                if len(text) > 200:
                                    return text[:5000]
                        except Exception:
                            pass
                        return None

                    def gpt_extract_contact(text, website):
                        prompt = (
                            "Given the following text extracted from the About, Team, or Contact page of a business website, "
                            "suggest the most relevant person to contact for business outreach. "
                            "Return:\n"
                            "- Suggested Contact Name (if found)\n"
                            "- Job Title\n"
                            "- Reason for suggestion (optional)\n"
                            "- Confidence Score (1-10) based on how certain you are this is the best contact\n"
                            "If no contact is found, say so and return Confidence Score 1.\n"
                            f"\nWebsite: {website}\n\nExtracted Text:\n{text}\n\nRespond in CSV format as:\n"
                            "Contact Name,Job Title,Reason,Confidence Score"
                        )
                        try:
                            response = openai.ChatCompletion.create(
                                model="gpt-3.5-turbo",
                                messages=[{"role": "user", "content": prompt}],
                                max_tokens=256,
                                temperature=0.3,
                            )
                            output = response.choices[0].message.content.strip()
                            lines = output.splitlines()
                            for line in lines:
                                if "," in line:
                                    fields = line.split(",", 3)
                                    while len(fields) < 4:
                                        fields.append("")
                                    return fields
                            return ["", "", "No contact found", "1"]
                        except Exception as e:
                            return ["", "", f"OpenAI error: {e}", "1"]

                    def generate_email(name, domain):
                        # Simple heuristic: first.last@domain
                        name = name.strip()
                        if not name or not domain:
                            return ""
                        parts = name.split()
                        if len(parts) == 0:
                            return ""
                        email_local = parts[0].lower()
                        if len(parts) > 1:
                            email_local += "." + parts[-1].lower()
                        # Remove non-alphanumeric
                        email_local = re.sub(r'[^a-z0-9.]', '', email_local)
                        return f"{email_local}@{domain}"

                    progress = st.progress(0)
                    for i, row in df.iterrows():
                        website = row["Website"]
                        scraped_email = ""
                        if pd.isna(website) or not str(website).startswith("http"):
                            emails.append("")
                            contact_names.append("")
                            job_titles.append("")
                            likely_emails.append("")
                            fallback_used.append("Y")
                            progress.progress((i + 1) / len(df))
                            continue
                        scraped_email = extract_email_from_website(website)
                        # AI-enhanced contact detection
                        text = fetch_best_page(website)
                        name, title, reason, confidence = "", "", "", ""
                        likely_contact_email = ""
                        fallback = "N"
                        if text and openai.api_key:
                            name, title, reason, confidence = gpt_extract_contact(text, website)
                            # Only generate likely email if confidence is at least 5 and name + title present
                            try:
                                conf_score = int(str(confidence).strip())
                            except Exception:
                                conf_score = 1
                            if name.strip() and conf_score >= 5:
                                # Extract domain from website
                                domain_match = re.search(r"https?://(?:www\.)?([^/]+)", website)
                                domain = domain_match.group(1) if domain_match else ""
                                likely_contact_email = generate_email(name, domain)
                            else:
                                likely_contact_email = ""
                        # Fallback: use scraped email if no likely contact
                        if not likely_contact_email:
                            likely_contact_email = scraped_email
                            fallback = "Y"
                        emails.append(scraped_email)
                        contact_names.append(name)
                        job_titles.append(title)
                        likely_emails.append(likely_contact_email)
                        fallback_used.append(fallback)
                        progress.progress((i + 1) / len(df))
                        time.sleep(1)

                    df["Scraped Email"] = emails
                    df["Contact Name"] = contact_names
                    df["Job Title"] = job_titles
                    df["Likely Contact Email"] = likely_emails
                    df["Fallback Email Used (Y/N)"] = fallback_used

                    output = io.StringIO()
                    df.to_csv(output, index=False)
                    st.success("✅ Scraping and enrichment complete. Download your file below.")
                    st.download_button(
                        "📥 Download CSV with Enriched Contacts",
                        output.getvalue(),
                        file_name="leads_with_contacts.csv",
                        mime="text/csv"
                    )
        except Exception as e:
            st.error(f"❌ Failed to read file: {e}")



# Footer attribution
st.markdown(
    "<hr style='margin-top: 4rem; margin-bottom: 1rem;'>"
    "<div style='text-align: center; font-size: 0.8rem; color: #888;'>"
    "Built by Olivia Burnett"
    "</div>",
    unsafe_allow_html=True
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**🔢 Estimated API Usage:** {st.session_state.api_calls} requests")
st.sidebar.markdown("Free tier covers ~11,000/month")