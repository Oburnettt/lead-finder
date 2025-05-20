import re
import requests
from bs4 import BeautifulSoup

def extract_email_from_text(text):
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def extract_name_and_title_from_text(text):
    lines = text.splitlines()
    for line in lines:
        lower = line.lower()
        if any(role in lower for role in ["owner", "marketing", "manager", "director", "ceo", "president"]):
            return line.strip()
    return None

from urllib.parse import urljoin

def scrape_contact_info_from_site(website, matched_roles):
    result = {}
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(website, headers=headers, timeout=10)
        if response.status_code != 200:
            return result

        soup = BeautifulSoup(response.text, "html.parser")
        base_url = urljoin(website, "/")
        subpage_keywords = [
            "about", "team", "staff", "doctors", "leadership",
            "our-team", "meet", "bios", "people", "company", "who-we-are"
        ]

        visited = set()
        pages_to_scrape = [website]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(keyword in href.lower() for keyword in subpage_keywords):
                full_url = urljoin(base_url, href)
                if full_url.startswith(base_url) and full_url not in visited:
                    pages_to_scrape.append(full_url)
                    visited.add(full_url)

        for url in pages_to_scrape:
            try:
                page_res = requests.get(url, headers=headers, timeout=8)
                if page_res.status_code != 200:
                    continue
                page_soup = BeautifulSoup(page_res.text, "html.parser")
                page_text = page_soup.get_text(separator="\n")
                lines = [line.strip() for line in page_text.split("\n") if line.strip()]

                for line in lines:
                    for role in matched_roles:
                        if role.lower() in line.lower():
                            result["title"] = role.title()
                            result["name"] = line.strip()
                            break
                    if "name" in result:
                        break

                if "name" in result:
                    email = extract_email_from_text(page_text)
                    if email:
                        result["email"] = email
                    result["phone"] = ""
                    break

            except Exception as inner_e:
                print(f"Error scraping subpage {url}: {inner_e}")

    except Exception as e:
        print(f"Failed to scrape {website}: {e}")

    return result