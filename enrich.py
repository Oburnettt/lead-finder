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

def scrape_contact_info_from_site(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text()
            email = extract_email_from_text(text)
            name_title = extract_name_and_title_from_text(text)
            return {
                "email": email,
                "name_title": name_title
            }
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
    return {"email": None, "name_title": None}