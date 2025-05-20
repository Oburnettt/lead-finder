import streamlit as st
import pandas as pd
import requests
import re
import time
import io
import os
import hashlib
import json
# Load scraper role config
with open("scraper_config.json", "r") as f:
    ROLE_CONFIG = json.load(f)
from dotenv import load_dotenv
from search import search_places, get_place_details
from enrich import scrape_contact_info_from_site, extract_email_from_text, extract_name_and_title_from_text
load_dotenv()

USAGE_FILE = "api_usage_real.json"

def load_api_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    return {"actual": 0, "estimated": 0}

def save_api_usage(usage_dict):
    with open(USAGE_FILE, "w") as f:
        json.dump(usage_dict, f)

# Session state: load persistent usage at startup
if "api_usage" not in st.session_state:
    st.session_state.api_usage = load_api_usage()
if "api_calls" not in st.session_state:
    st.session_state.api_calls = 0

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "table"

st.set_page_config(page_title="Direct Contact Search")

PAGES = {
    "Lead Finder": "🔍 Lead Finder",
    "Lead Database": "📁 Lead Database",
    "Enrich Contacts": "👤 Enrich Contacts",
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
if st.sidebar.button("📁 Lead Database"):
    st.session_state.page = "Lead Database"
if st.sidebar.button("👤 Enrich Contacts"):
    st.session_state.page = "Enrich Contacts"
if st.sidebar.button("❓ Help"):
    st.session_state.page = "Instructions"

# Sidebar options and controls (test mode, etc.)
test_mode = st.sidebar.checkbox("🧪 Enable Test Mode (for fast testing)")
use_threading = st.sidebar.checkbox(
    "⚡ Enable Fast Search (Threaded)", 
    value=False,
    help="Use multi-threading to search multiple cities in parallel. May increase speed but also API risk."
)

# Insert a large flexible spacer to push content down
st.sidebar.markdown("<div style='height:40vh;'></div>", unsafe_allow_html=True)

API_LIMIT = 11000

page = st.session_state.page

if page == "Enrich Contacts":
    st.title("👤 Enrich Contacts")

    uploaded_file = st.file_uploader("Upload a CSV of business leads to enrich", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)

        st.success(f"Uploaded {len(df)} businesses for enrichment.")
        st.info("This is a placeholder. Enrichment code will run here in the next step.")

        # Begin enrichment process
        enriched_rows = []
        fallback_rows = []

        for idx, row in df.iterrows():
            name, title = "", ""
            email, phone = "", ""
            linkedin = ""
            website = row.get("Website", "")
            business_name = row.get("Business Name", "")
            fallback_notes = ""

            # Determine relevant titles from the config
            industry = business_name.lower()
            matched_roles = []

            for key in ROLE_CONFIG.get("titles_by_industry", {}):
                if key in industry:
                    matched_roles = ROLE_CONFIG["titles_by_industry"][key]
                    break
            if not matched_roles:
                matched_roles = ["owner", "manager", "director"]

            if website and isinstance(website, str) and website.startswith("http"):
                try:
                    contact_info = scrape_contact_info_from_site(website, matched_roles)

                    name = contact_info.get("name", "")
                    title = contact_info.get("title", "")
                    email = contact_info.get("email", "")
                    phone = contact_info.get("phone", "")

                    if not email and not phone and name:
                        linkedin = f"https://www.google.com/search?q=site:linkedin.com/in+%22{name}%22+%22{business_name}%22"

                    if name or title or email or phone:
                        enriched_rows.append({
                            "Business Name": business_name,
                            "Name": name,
                            "Title": title,
                            "Email": email,
                            "Phone": phone,
                            "LinkedIn": linkedin,
                            "Website": website,
                            "Source": "Website"
                        })
                    else:
                        fallback_rows.append({
                            "Business Name": business_name,
                            "Phone": row.get("Phone", ""),
                            "Website": website,
                            "Email": contact_info.get("business_email", ""),
                            "Contact Page": contact_info.get("contact_page", ""),
                            "Notes": "No direct contact found"
                        })

                except Exception as e:
                    fallback_rows.append({
                        "Business Name": business_name,
                        "Phone": row.get("Phone", ""),
                        "Website": website,
                        "Email": "",
                        "Contact Page": "",
                        "Notes": f"Error scraping site: {str(e)}"
                    })
            else:
                fallback_rows.append({
                    "Business Name": business_name,
                    "Phone": row.get("Phone", ""),
                    "Website": website,
                    "Email": "",
                    "Contact Page": "",
                    "Notes": "No website listed"
                })

        enriched_contacts = pd.DataFrame(enriched_rows)
        fallback_info = pd.DataFrame(fallback_rows)

        st.success(f"✅ Enriched {len(enriched_contacts)} contacts.")
        st.info(f"ℹ️ {len(fallback_info)} leads used fallback general business info.")

        # Display download options for enrichment outputs
        st.download_button("📥 Download Verified Contacts (.csv)", enriched_contacts.to_csv(index=False), file_name="verified_contacts.csv", mime="text/csv")
        st.download_button("📥 Download General Info (.csv)", fallback_info.to_csv(index=False), file_name="general_business_info.csv", mime="text/csv")

        try:
            import openpyxl
            from io import BytesIO

            def to_excel_download(df1, df2):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df1.to_excel(writer, sheet_name='Verified Contacts', index=False)
                    df2.to_excel(writer, sheet_name='General Info', index=False)
                output.seek(0)
                return output

            excel_data = to_excel_download(enriched_contacts, fallback_info)
            st.download_button("📥 Download Combined (.xlsx)", data=excel_data, file_name="enriched_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.warning("Excel export not available. Missing openpyxl module.")

elif page == "Instructions":
    st.title("❓ Help")
    st.markdown("""
<style>
.help-section h4 {
    margin-top: 1.5em;
    color: #f0f0f0;
}
.help-section ul {
    padding-left: 1.2em;
}
.help-section li {
    margin-bottom: 0.5em;
}
</style>

<div class="help-section">

## 🧭 How to Use This Tool

### 🔍 Lead Finder Tab

Use this tab to search for businesses in specific industries and states.

**Steps to run a search:**
- Enter a business type (e.g., dentist, school)
- Select one or more U.S. states
- Adjust filters and advanced options as needed
- Click **Search**

---

## ⚙️ Filters and Advanced Options

### 🔽 Filter Leads
These help clean your results:

- **📞 Only show leads with a phone number**  
  Use this if you plan to call businesses.  
  _Skip if you only need email or website data._

- **🌐 Only show leads with a website**  
  Useful if you want to research the business further.  
  _Uncheck to include more small/local businesses._

---

### 🔧 Advanced Options

- **📄 Get More Leads Per City**  
  Searches more Google result pages per city.  
  _Use this if your results seem limited or you're in a large market._  
  _Not needed for quick tests or small states._

- **☑️ Explore More Cities**  
  Skips previously searched cities and expands your reach.  
  _Helpful for repeat searches or lead expansion over time._

- **⚡ Enable Fast Search (Threaded)**  
  Speeds up the process using multi-threading.  
  _Use if you have a solid internet connection._  
  _Avoid if you’re close to your monthly API limit._

- **🧪 Test Mode**  
  Runs a short version of the search (3 cities per state).  
  _Use this to preview results without using many API calls._

---

## 📁 Lead Database Tab

View, filter, and export the leads you've collected.

### 🔍 Filter Leads
- Filter by **state** or **business type**
- Select specific leads to download

### 🕓 Previous Searches
- Revisit past searches
- Download or delete them
- Preview before exporting

---

## 🧾 Extra Notes

- Your monthly API usage is tracked in the sidebar (limit: **11,000** calls)
- Duplicate leads are flagged as **Already Harvested**
- Each lead includes:
  - Name, Phone, Website, Address
  - Search term + state

---

</div>

Built with love by **Olivia Burnett**
""", unsafe_allow_html=True)

elif page == "Lead Database":
    st.title("📁 Lead Database")
    tab1, tab2 = st.tabs(["🔍 Filter Leads", "🕓 Previous Searches"])

    with tab1:
        # Always load all leads from the archive CSV if it exists, otherwise initialize empty DataFrame
        lead_archive_file = "lead_results_latest.csv"
        if os.path.exists(lead_archive_file):
            lead_archive_df = pd.read_csv(lead_archive_file)
        else:
            lead_archive_df = pd.DataFrame(columns=["Business Name", "Phone", "Website", "Address", "Status"])

        st.session_state.lead_results = lead_archive_df

        # --- UI: Horizontal rule and filter header ---
        st.markdown("---")
        st.markdown("### 🔍 Filter Options")

        # --- Filter controls ---
        available_states = sorted(lead_archive_df["Search State(s)"].dropna().unique()) if "Search State(s)" in lead_archive_df.columns else []
        available_terms = sorted(lead_archive_df["Search Term"].dropna().unique()) if "Search Term" in lead_archive_df.columns else []

        selected_states = st.multiselect("Filter by State(s)", available_states)
        selected_terms = st.multiselect("Filter by Business Type", available_terms)

        filtered_df = lead_archive_df.copy()
        if selected_states:
            filtered_df = filtered_df[filtered_df["Search State(s)"].isin(selected_states)]
        if selected_terms:
            filtered_df = filtered_df[filtered_df["Search Term"].isin(selected_terms)]

        # --- Pagination logic for filtered leads ---
        leads_per_page = 10
        if "filter_leads_page" not in st.session_state:
            st.session_state.filter_leads_page = 0

        total_filtered = len(filtered_df)
        total_pages = (total_filtered + leads_per_page - 1) // leads_per_page
        current_page = st.session_state.filter_leads_page

        paged_df = filtered_df.iloc[current_page * leads_per_page: (current_page + 1) * leads_per_page]

        # Create a list to track selected indices
        selected_indices = []

        if not filtered_df.empty:
            st.markdown(f"### Displaying {len(filtered_df)} leads")

            select_all = st.checkbox("☑️ Select All Filtered Results", value=False)

            # --- Simplified modern styled lead display (timestamp/status as tooltip) ---
            for idx, row in paged_df.iterrows():
                with st.container():
                    col1, col2 = st.columns([0.05, 0.95])
                    selected = col1.checkbox("", key=f"select_{idx}", value=select_all)
                    if selected:
                        selected_indices.append(idx)
                    with col2:
                        st.markdown(f"""
<div style="
    background: linear-gradient(145deg, #1f1f1f, #1a1a1a);
    border-radius: 8px;
    border: 1px solid #333;
    padding: 15px;
    margin-bottom: 12px;
    box-shadow: 0 0 8px rgba(0,0,0,0.3);
    position: relative;"
    title="🕒 {row.get('Timestamp', 'N/A')} | Status: {row.get('Status', 'N/A')}"
>
    <div style="font-size: 18px; font-weight: bold; color: #f0f0f0;">{row.get('Business Name', '')}</div>
    <div style="margin-top: 2px; color: #bbb; font-style: italic;">
        {row.get('Search Term', 'N/A')} in {row.get('Search State(s)', 'N/A')}
    </div>
    <div style="margin-top: 6px; color: #bbb;">
        📞 <strong>{row.get('Phone', 'N/A')}</strong><br>
        🌐 <a href="{row.get('Website')}" target="_blank" style="color: #4fa8f4;">Visit Website</a><br>
        📍 {row.get('Address', 'N/A')}
    </div>
</div>
""", unsafe_allow_html=True)

            # --- Pagination controls ---
            col_prev, col_page, col_next = st.columns([0.15, 0.2, 0.15])
            with col_prev:
                if st.button("⬅️ Previous", disabled=(current_page == 0), key="filter_prev_pg"):
                    st.session_state.filter_leads_page = max(0, current_page - 1)
                    st.experimental_rerun()
            with col_page:
                st.markdown(f"<div style='text-align:center;padding-top:4px;'>Page {current_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
            with col_next:
                if st.button("Next ➡️", disabled=(current_page >= total_pages - 1), key="filter_next_pg"):
                    st.session_state.filter_leads_page = min(total_pages - 1, current_page + 1)
                    st.experimental_rerun()

            # --- UI: Spacing before export buttons ---
            st.markdown("### 📤 Export Options")
            # Export button for selected leads
            if selected_indices:
                selected_leads = filtered_df.loc[selected_indices]
                csv_export = selected_leads.to_csv(index=False)
                st.download_button("📥 Export Selected Leads", data=csv_export, file_name="selected_leads.csv", mime="text/csv")
            # Allow download of all leads as well
            st.download_button("📥 Download All Leads", lead_archive_df.to_csv(index=False), file_name="lead_database.csv", mime="text/csv")
        else:
            st.warning("⚠️ No leads match your filter.")

    with tab2:
        st.markdown("### 🕓 Previous Searches")
        lead_results_file = "lead_results_latest.csv"
        if os.path.exists(lead_results_file):
            # Load and group previous searches
            full_df = pd.read_csv(lead_results_file)
            if not full_df.empty:
                # Group by Search Term, State(s), Timestamp Group
                full_df["Timestamp Group"] = pd.to_datetime(full_df["Timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
                grouped = list(full_df.groupby(["Search Term", "Search State(s)", "Timestamp Group"]))

                # --- Pagination state ---
                if "prev_searches_page" not in st.session_state:
                    st.session_state.prev_searches_page = 0
                groups_per_page = 5
                total_groups = len(grouped)
                total_pages = (total_groups + groups_per_page - 1) // groups_per_page
                page = st.session_state.prev_searches_page
                start_idx = page * groups_per_page
                end_idx = min(start_idx + groups_per_page, total_groups)
                paged_groups = grouped[start_idx:end_idx]

                # --- For delete: maintain state for deletion triggers ---
                if "delete_group_keys" not in st.session_state:
                    st.session_state.delete_group_keys = {}

                # --- Display paginated groups ---
                for i, (key, group_df) in enumerate(paged_groups):
                    term, state, timestamp = key
                    label = f"{term.title()} in {state} — {timestamp}"
                    lead_count = len(group_df)
                    group_id = f"{term}|{state}|{timestamp}"
                    delete_btn_key = f"del_{group_id}_{start_idx+i}".replace(" ", "_")
                    preview_key = f"preview_{group_id}_{start_idx+i}".replace(" ", "_")
                    download_key = f"download_{group_id}_{start_idx+i}".replace(" ", "_").lower()
                    # --- Container for group ---
                    with st.container():
                        st.markdown(f"""
<div style="border: 1px solid #333; padding: 15px; border-radius: 8px; margin-bottom: 15px; background-color: #1c1c1c;">
    <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">
        🔎 {label} <span style="color:#bbb; font-size:14px;">({lead_count} lead{'s' if lead_count != 1 else ''})</span>
    </div>
</div>
""", unsafe_allow_html=True)
                        cols = st.columns([0.15, 0.2, 0.25])
                        with cols[0]:
                            st.checkbox("👁 Preview", key=preview_key)
                        with cols[1]:
                            st.download_button(
                                label="📥 Download Leads",
                                data=group_df.to_csv(index=False),
                                file_name=f"{term}_{state}_{timestamp}.csv".replace(" ", "_").lower(),
                                mime="text/csv",
                                key=download_key
                            )
                        with cols[2]:
                            if st.button("🗑 Delete Search", key=delete_btn_key):
                                st.session_state.delete_group_keys[group_id] = True
                        # --- Deletion logic ---
                        if st.session_state.delete_group_keys.get(group_id, False):
                            # Remove this group's rows from full_df and save
                            mask = ~(
                                (full_df["Search Term"] == term)
                                & (full_df["Search State(s)"] == state)
                                & (full_df["Timestamp Group"] == timestamp)
                            )
                            full_df = full_df[mask]
                            # Remove the trigger so it doesn't re-trigger
                            st.session_state.delete_group_keys[group_id] = False
                            # Remove the group from grouped list and update file
                            full_df.drop(columns=["Timestamp Group"], inplace=True, errors="ignore")
                            full_df.to_csv(lead_results_file, index=False)
                            st.experimental_rerun()
                        if st.session_state.get(preview_key):
                            st.dataframe(group_df)

                # --- Pagination controls ---
                col_prev, col_page, col_next = st.columns([0.15, 0.2, 0.15])
                with col_prev:
                    if st.button("⬅️ Previous", disabled=(page == 0), key="prev_pg"):
                        st.session_state.prev_searches_page = max(0, page - 1)
                        st.experimental_rerun()
                with col_page:
                    st.markdown(f"<div style='text-align:center;padding-top:4px;'>Page {page+1} of {total_pages}</div>", unsafe_allow_html=True)
                with col_next:
                    if st.button("Next ➡️", disabled=(page >= total_pages-1), key="next_pg"):
                        st.session_state.prev_searches_page = min(total_pages-1, page + 1)
                        st.experimental_rerun()

                # --- Export All Historical Searches ---
                st.markdown("---")
                st.markdown("#### 📦 Export All Historical Searches")
                total_leads = len(full_df)
                if "export_confirm" not in st.session_state:
                    st.session_state.export_confirm = False
                if st.button("📦 Export All Historical Searches", key="export_all_hist"):
                    st.session_state.export_confirm = True
                if st.session_state.export_confirm:
                    st.warning(f"You are about to export {total_leads:,} leads. Are you sure?")
                    if st.button("✅ Confirm Export", key="confirm_export_all"):
                        export_csv = full_df.drop(columns=["Timestamp Group"], errors="ignore").to_csv(index=False)
                        st.download_button(
                            label="📥 Download All Historical Leads",
                            data=export_csv,
                            file_name="lead_results_latest.csv",
                            mime="text/csv",
                            key="dl_all_hist"
                        )
                        # Reset confirmation after download button shown
                        st.session_state.export_confirm = False
            else:
                st.info("No previous search results found.")
        else:
            st.info("No previous search results found.")

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
    # --- API input disabling logic ---
    disabled = st.session_state.api_calls >= API_LIMIT
    st.title("🔍 Lead Finder")
    st.markdown("<p style='color:#888;'>Enter a type of business and select the states you'd like to search. This tool will generate a list of relevant businesses using the Google Maps API.</p>", unsafe_allow_html=True)

    if "search_history" not in st.session_state:
        st.session_state.search_history = []

    business_type = st.text_input(
        "Enter a type of business (e.g., cemetery, funeral home, school)",
        disabled=disabled
    )

    states = st.multiselect(
        "Select one or more U.S. states:",
        [
            "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
            "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
            "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
            "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
            "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
            "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
            "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
        ],
        disabled=disabled
    )

    with st.expander("📎 Filter Leads", expanded=False):
        has_phone = st.checkbox("📞 Only show leads with a phone number", disabled=disabled)
        has_website = st.checkbox("🌐 Only show leads with a website", disabled=disabled)
    lead_filters = []
    if has_phone:
        lead_filters.append("📞 Only show leads with a phone number")
    if has_website:
        lead_filters.append("🌐 Only show leads with a website")

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
            help="Select how many top cities in each state to search for this business type.",
            disabled=disabled
        )

    # Pagination option (default to False) in advanced options expander
    with st.expander("⚙️ Advanced Options", expanded=False):
        paginate_results = st.checkbox(
            "📄 Get More Leads Per City (searches multiple pages)",
            value=False,
            help="Enable this to search up to 3 pages of results per city. Increases API usage but returns more leads.",
            disabled=disabled
        )
        explore_more = st.checkbox(
            "☑️ Explore More Cities (skip previously searched ones)",
            value=False,
            help="Skips cities already searched for this business type to expand coverage across sessions.",
            disabled=disabled
        )

    # Load top cities per state from external JSON for full coverage
    with open("top_cities_by_state_converted.json", "r") as f:
        TOP_CITIES_PER_STATE = json.load(f)

    # Recent Searches now in the sidebar

    # --- Estimate API Usage ---
    if business_type and states:
        estimated_terms = [business_type]
        if not test_mode:
            if "dentist" in business_type.lower():
                estimated_terms.extend(["dental office", "dental clinic", "family dentist"])
            elif "school" in business_type.lower():
                estimated_terms.extend(["elementary school", "middle school", "high school", "academy"])

        estimated_term_count = len(estimated_terms)
        estimated_city_count = len(states) * (search_depth if not test_mode else 3)
        estimated_per_term = 3 if paginate_results else 1
        estimated_total_calls = estimated_term_count * estimated_city_count * estimated_per_term

        st.session_state.api_usage["estimated"] += estimated_total_calls
        save_api_usage(st.session_state.api_usage)
        st.info(f"🔍 Estimated API calls for this search: **{estimated_total_calls:,}**")

    if st.button("Search", disabled=disabled):
        if not business_type or not states:
            st.warning("Please enter a business type and select at least one state.")
        else:
            # Gate for API usage limit
            if st.session_state.api_calls >= API_LIMIT:
                st.error(f"🚫 API usage limit ({API_LIMIT:,}) reached for the month. Please try again after your usage resets.")
                st.stop()
            API_KEY = os.getenv("GOOGLE_API_KEY")

            leads = []

            with st.spinner(f"⏳ Searching... this may take some time."):
                from concurrent.futures import ThreadPoolExecutor

                search_terms = [business_type]
                # Only expand variants if not in test mode
                if not test_mode:
                    if "dentist" in business_type.lower():
                        search_terms.extend(["dental office", "dental clinic", "family dentist"])
                    elif "school" in business_type.lower():
                        search_terms.extend(["elementary school", "middle school", "high school", "academy"])

        def search_city(city):
            city_leads = []
            for term in search_terms:
                with st.spinner(f"Searching {term} in {city}, {state}..."):
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
                        st.session_state.api_usage["actual"] += 1
                        save_api_usage(st.session_state.api_usage)

            for result in query_results:
                place_id = result.get("place_id")
                phone = ""
                website = ""
                if place_id:
                    details = get_place_details(place_id, API_KEY)
                    phone = details.get("formatted_phone_number", "")
                    website = details.get("website", "")
                city_leads.append({
                    "Business Name": result.get("name", ""),
                    "Phone": phone,
                    "Website": website,
                    "Address": result.get("formatted_address", ""),
                    "Search Term": business_type,
                    "Search State(s)": state,
                    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
            if not use_threading:
                time.sleep(0.3)  # Prevent rate-limiting
            return city_leads

        for state in states:
            state_cities = TOP_CITIES_PER_STATE.get(state, [state])
            offset_key = f"{business_type.lower()}_{state.lower()}_offset"
            if explore_more:
                if offset_key not in st.session_state:
                    st.session_state[offset_key] = 0
                start = st.session_state[offset_key]
                end = start + search_depth
                cities_to_search = state_cities[start:end]
                st.session_state[offset_key] += search_depth
            else:
                cities_to_search = state_cities[:search_depth] if len(state_cities) >= search_depth else state_cities

            if use_threading:
                with ThreadPoolExecutor(max_workers=8) as executor:
                    for city_leads in executor.map(search_city, cities_to_search):
                        leads.extend(city_leads)
            else:
                for city in cities_to_search:
                    leads.extend(search_city(city))

            df = pd.DataFrame(leads)

            # Deduplicate
            df.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
            df.reset_index(drop=True, inplace=True)

            # Apply filters
            if "📞 Only show leads with a phone number" in lead_filters:
                df = df[df["Phone"].notna() & df["Phone"].str.strip().ne("")]
            if "🌐 Only show leads with a website" in lead_filters:
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

                # Update the archive immediately with new leads so they persist and display in Lead Database
                new_leads_to_add = df[df["Status"] == "New"]
                updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                updated_archive.to_csv(archive_file, index=False)

                # Save latest session to both files
                st.session_state.lead_results = df
                df.to_csv("lead_results_latest.csv", index=False)

                # Download All Leads button
                st.download_button("📥 Download All Leads", display_df.to_csv(index=False), file_name=filename_all, mime="text/csv")

                # Download Only New Leads button and archive update
                if st.download_button("🆕 Download Only New Leads", new_leads_to_add.to_csv(index=False), file_name=filename_new, mime="text/csv"):
                    updated_archive = pd.concat([archive_df, new_leads_to_add], ignore_index=True)
                    updated_archive.drop_duplicates(subset=["Business Name", "Phone", "Website"], inplace=True)
                    updated_archive.to_csv(archive_file, index=False)

                # Save results to session state for persistent view
                st.session_state.lead_results = df
                # Save to CSV for persistence on refresh
                df.to_csv("lead_results_latest.csv", index=False)
            else:
                st.warning("⚠️ No leads were found. Please check your search term or selected states.")


# Sidebar Lead Summary (expander version)
    st.sidebar.markdown("<div style='margin-top:auto;'></div>", unsafe_allow_html=True)
    # Lead Summary block moved above API usage and wrapped in expander
    with st.sidebar.expander("📊 Lead Summary", expanded=False):
        if "lead_results" in st.session_state:
            df = st.session_state.lead_results
            new_count = (df["Status"] == "New").sum()
            existing_count = (df["Status"] == "Already Harvested").sum()
            st.markdown(f"- 📌 **Total Leads:** {len(df)}")
            st.markdown(f"- 🆕 **New:** {new_count}")
            st.markdown(f"- ♻️ **Already Harvested:** {existing_count}")
        else:
            st.markdown("No results to summarize yet.")

    # Recent Searches in the sidebar
    if "search_history" in st.session_state and st.session_state.search_history:
        st.sidebar.markdown("### 🔁 Recent Searches")
        st.sidebar.markdown("<ul>" + "".join([f"<li>{query}</li>" for query in st.session_state.search_history[-5:]]) + "</ul>", unsafe_allow_html=True)

    # Ensure api_calls is initialized before usage/credit block
    if "api_calls" not in st.session_state:
        st.session_state.api_calls = 0
    # Move API usage and credit explicitly to the very bottom, with horizontal rule and bottom container
    with st.sidebar.container():
        st.sidebar.markdown("<hr>", unsafe_allow_html=True)
        usage = st.session_state.api_usage
        st.sidebar.markdown(f"**Actual API Usage:** {usage['actual']:,}")
        st.sidebar.markdown(f"**Estimated Usage (Projected):** {usage['estimated']:,}")
        st.sidebar.markdown(f"**Remaining Credit Estimate:** ~{300 - usage['actual'] * 0.017:.2f} USD")
        if usage["actual"] >= API_LIMIT:
            st.sidebar.error("🚫 Monthly API limit reached!")
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

