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
                    for term in search_terms:
                        query_results = search_places(term, f"{state}", API_KEY)
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
                updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                updated_archive.to_csv(archive_file, index=False)

                st.success(f"Found {len(df)} leads ({(df['Status'] == 'New').sum()} new, {(df['Status'] == 'Already Harvested').sum()} previously harvested).")
                st.dataframe(df)
                st.download_button("📥 Download All Leads", df.to_csv(index=False), file_name="all_leads.csv", mime="text/csv")
                st.download_button("🆕 Download Only New Leads", new_leads_to_add.to_csv(index=False), file_name="new_leads_only.csv", mime="text/csv")
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
                    emails = []

                    def extract_email_from_website(url):
                        try:
                            headers = {'User-Agent': 'Mozilla/5.0'}
                            res = requests.get(url, timeout=5, headers=headers)
                            soup = BeautifulSoup(res.text, 'html.parser')
                            emails_found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", soup.text)
                            return emails_found[0] if emails_found else ""
                        except Exception as e:
                            return ""

                    progress = st.progress(0)
                    for i, row in df.iterrows():
                        website = row["Website"]
                        if pd.isna(website) or not str(website).startswith("http"):
                            emails.append("")
                            continue
                        email = extract_email_from_website(website)
                        emails.append(email)
                        progress.progress((i + 1) / len(df))
                        time.sleep(1)

                    df["Scraped Email"] = emails

                    output = io.StringIO()
                    df.to_csv(output, index=False)
                    st.success("✅ Scraping complete. Download your file below.")
                    st.download_button("📥 Download CSV with Emails", output.getvalue(), file_name="leads_with_emails.csv", mime="text/csv")
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