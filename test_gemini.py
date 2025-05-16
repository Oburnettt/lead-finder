import google.generativeai as genai

genai.configure(api_key="AIzaSyAqyvck8yeaAOW4wf2Ln6nPCcUxH9V7a7w")

model = genai.GenerativeModel("models/gemini-pro")

prompt = """
Who is the decision maker at CGS Imaging in Toledo, Ohio?
Return:
- Full Name
- Job Title
- Publicly listed email address (if available)
- Public phone number (if available)
- Label each contact as Direct or General
Only use publicly listed information from LinkedIn or the company's website.
"""

response = model.generate_content(prompt)
print(response.text)