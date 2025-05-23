import requests
import cloudscraper
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import json

def extract_generic_email(soup, html=""):
    emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@(?!example\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", soup.get_text()))
    mailtos = soup.select("a[href^=mailto]")
    for tag in mailtos:
        href = tag.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip()
        if email:
            emails.add(email)

    if html:
        html_emails = re.findall(r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", html)
        emails.update(html_emails)

    for email in emails:
        if any(keyword in email.lower() for keyword in ["info", "contact", "support", "hello", "admin"]):
            return email
    return ""

def clean_url(url):
    if not isinstance(url, str) or url.strip().lower() == "nan":
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "http://" + url
    return url

def extract_email_from_text(text):
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def extract_phone_from_text(text):
    pattern = r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def extract_people_info(html, matched_roles):
    soup = BeautifulSoup(html, "html.parser")
    people = []

    GENERIC_LABELS = {"meet our team", "our team", "team", "leadership", "management", "staff", "about us"}

    # Step 1: Scan structured elements
    for tag in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "span", "strong", "section", "a"]):
        text = tag.get_text(" ", strip=True)
        if any(role.lower() in text.lower() for role in matched_roles):
            name_tag = tag.find_previous(["h1", "h2", "h3", "strong"])
            if name_tag:
                name = name_tag.get_text(strip=True)
                if name.lower() in GENERIC_LABELS:
                    continue  # Skip generic headers as contact names
            else:
                name = ""
            # Improved title matching logic
            skip_keywords = ["specialty", "areas", "services", "invisalign", "implants", "procedures", "bio", "about", "focus"]
            cleaned_text = text.lower().strip()

            # Ensure it's a short, clean role description, not a specialization bio
            if 1 <= len(cleaned_text.split()) <= 5 and not any(kw in cleaned_text for kw in skip_keywords):
                for role in matched_roles:
                    if role.lower() in cleaned_text:
                        clean_name = name.strip().replace("\n", " ").replace("\r", " ")
                        clean_role = role.title().strip()
                        # Skip titles that contain marketing/section phrases (case-insensitive, expanded list)
                        generic_phrases = [
                            "welcome to", "about your", "our services", "learn more",
                            "improve your smile", "what to expect", "iv sedation",
                            "sleep apnea", "quality dental care", "new patients", 
                            "treatments", "dental care", "oral health"
                        ]
                        if any(phrase in cleaned_text.lower() for phrase in generic_phrases):
                            continue

                        import re
                        # Only allow names that look like "First Last" (capitalized, 2+ parts)
                        if not re.match(r"^[A-Z][a-z]+( [A-Z][a-z]+)+$", clean_name):
                            continue

                        formatted = {"name": clean_name, "role": clean_role}
                        if formatted not in people:
                            people.append({
                                "name": clean_name,
                                "role": clean_role,
                                "email": extract_email_from_text(str(tag)),
                                "phone": extract_phone_from_text(str(tag))
                            })
                        break

    # Step 2: Scan image alt/title attributes
    for img in soup.find_all("img"):
        alt_text = img.get("alt", "")
        title_text = img.get("title", "")
        combined = f"{alt_text} {title_text}".strip()
        if any(role.lower() in combined.lower() for role in matched_roles):
            people.append({
                "name": combined,
                "role": combined,
                "email": "",
                "phone": ""
            })

    # Step 3: Fallback line-by-line scan
    full_text_lines = soup.get_text(separator="\n").splitlines()
    seen = set()
    for i, line in enumerate(full_text_lines):
        if any(role.lower() in line.lower() for role in matched_roles):
            name_line = full_text_lines[i - 1].strip() if i > 0 else ""
            role_line = line.strip()
            identifier = f"{name_line} – {role_line}"
            if identifier and identifier not in seen:
                import re
                # Additional noise filtering for fallback lines
                skip_phrases = [
                    "meet your", "what our patients", "our services", "about your", 
                    "frequently asked", "faq", "iv sedation", "sleep apnea", 
                    "quality dental care", "new patients", "treatments", "oral health"
                ]
                combined_line = f"{name_line.lower()} {role_line.lower()}"
                if any(phrase in combined_line for phrase in skip_phrases):
                    continue

                # Improved name check: must be two proper capitalized words (e.g., John Smith)
                if not re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)+$", name_line):
                    continue

                seen.add(identifier)
                contact_block = f"{name_line}\n{role_line}"
                people.append({
                    "name": name_line,
                    "role": role_line,
                    "email": extract_email_from_text(contact_block),
                    "phone": extract_phone_from_text(contact_block)
                })

    return people

def find_contact_page_link(soup, base_url):
    keywords = [
        "contact", "connect", "schedule", "message", "talk", "reach", "form",
        "get in touch", "start", "appointment", "hello", "inquiry", "support", "visit"
    ]
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()
        # Match on href or link text, even if text is blank
        if any(keyword in href or keyword in text for keyword in keywords):
            return urljoin(base_url, a["href"])
    return ""

def scrape_contact_info_from_site(website, matched_roles):
    website = clean_url(website)
    if not website or website.lower().strip() == "nan":
        return {
            "business_email": "",
            "direct_contacts": "No direct contact found",
            "website": "",
            "scrape_status": "Invalid URL"
        }

    result = {}
    soup = None
    direct_contacts = []
    scrape_status = "Unknown Error"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:112.0) Gecko/20100101 Firefox/112.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive"
    }

    try:
        priority_links = crawl_priority_links(website)

        scraper = cloudscraper.create_scraper()
        for link in priority_links:
            try:
                response = scraper.get(link, timeout=10, headers=headers)
            except requests.exceptions.SSLError:
                scrape_status = "SSL Verification Failed"
                return {
                    "business_email": "",
                    "direct_contacts": "No direct contact found",
                    "website": website,
                    "scrape_status": scrape_status
                }
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(separator=" ").strip().replace("\n", " ").replace("\r", " ")

            people = extract_people_info(response.text, matched_roles)

            for person in people:
                name = person.get("name", "").strip()
                role = person.get("role", "").strip()
                if name and role:
                    direct_contacts.append(f"{name} – {role}")

        if not direct_contacts:
            try:
                response = scraper.get(website, timeout=10, headers=headers)
            except requests.exceptions.SSLError:
                scrape_status = "SSL Verification Failed"
                return {
                    "business_email": "",
                    "direct_contacts": "No direct contact found",
                    "website": website,
                    "scrape_status": scrape_status
                }
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(separator=" ").strip().replace("\n", " ").replace("\r", " ")
            people = extract_people_info(response.text, matched_roles)

            for person in people:
                name = person.get("name", "").strip()
                role = person.get("role", "").strip()
                if name and role:
                    direct_contacts.append(f"{name} – {role}")

        scrape_status = "Success"

    except requests.exceptions.HTTPError as e:
        scrape_status = f"{e.response.status_code} {e.response.reason}"
        page_text = ""
    except Exception as e:
        print(f"Failed to scrape {website}: {e}")
        scrape_status = "Error"
        page_text = ""

    if not soup:
        try:
            try:
                response = scraper.get(website, timeout=10, headers=headers)
            except requests.exceptions.SSLError:
                scrape_status = "SSL Verification Failed"
                return {
                    "business_email": "",
                    "direct_contacts": "No direct contact found",
                    "website": website,
                    "scrape_status": scrape_status
                }
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(separator=" ").strip().replace("\n", " ").replace("\r", " ")
        except Exception:
            soup = None
            page_text = ""

    general_email = extract_email_from_text(page_text) if page_text else None
    if (not general_email or general_email.strip() == "") and soup:
        generic_email = extract_generic_email(soup, response.text)
        if generic_email:
            general_email = generic_email

    result = {
        "business_email": general_email or "",
        "direct_contacts": ", ".join(direct_contacts) if direct_contacts else "No direct contact found",
        "website": website,
        "scrape_status": scrape_status
    }

    return result

TARGET_SUBPAGE_KEYWORDS = ["about", "team", "staff", "doctors", "leadership", "providers", "who-we-are", "our-people"]

def crawl_priority_links(home_url):
    home_url = clean_url(home_url)
    if not home_url or home_url.lower().strip() == "nan":
        return []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:112.0) Gecko/20100101 Firefox/112.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        }
        scraper = cloudscraper.create_scraper()
        try:
            response = scraper.get(home_url, timeout=10, headers=headers)
        except requests.exceptions.SSLError:
            print(f"SSL Verification Failed for {home_url}")
            return []
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        links = [a['href'] for a in soup.find_all("a", href=True)]
        internal_links = [
            urljoin(home_url, l) for l in links
            if any(k in l.lower() for k in TARGET_SUBPAGE_KEYWORDS) and l.startswith("/")
        ]

        return list(set(internal_links))
    except Exception as e:
        print(f"Error crawling {home_url}: {e}")
        return []

def extract_from_jsonld(html):
    soup = BeautifulSoup(html, "html.parser")
    people = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Person":
                people.append({
                    "name": data.get("name", ""),
                    "email": data.get("email", ""),
                    "role": data.get("jobTitle", "")
                })
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Person":
                        people.append({
                            "name": item.get("name", ""),
                            "email": item.get("email", ""),
                            "role": item.get("jobTitle", "")
                        })
        except Exception:
            continue
    return people