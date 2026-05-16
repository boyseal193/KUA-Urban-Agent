import os
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def geocode_address(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"

    params = {
        "address": address,
        "key": GOOGLE_API_KEY
    }

    response = requests.get(url, params=params).json()

    if response["status"] != "OK":
        return {"lat": None, "lng": None}

    location = response["results"][0]["geometry"]["location"]

    return {
        "lat": location["lat"],
        "lng": location["lng"]
    }