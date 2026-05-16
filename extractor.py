import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_property_from_text(raw_text: str):
    prompt = f"""
Extract structured commercial real estate data from the listing text below.

Return ONLY valid JSON. No markdown. No explanation.

Fields required:
source
listing_url
address
city
neighbourhood
gba_m2
asking_price
asking_rent_month
rent_per_m2
ceiling_height
loading_access
access_type
floor_level
building_type
current_use
description
price_per_m2_nra
nra_efficiency

Rules:
- If missing, use null
- loading_access must be true or false
- If rent_per_m2 is missing but rent and size exist, calculate it
- If nra_efficiency is unknown, use 0.75
- city defaults to Barcelona if obvious

LISTING TEXT:
{raw_text}
"""

    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You extract real estate data into strict JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content

    return json.loads(content)