import math


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(r * c, 2)


def distance_score_to_point(property_lat, property_lng, target_lat, target_lng):
    distance = haversine_km(property_lat, property_lng, target_lat, target_lng)

    if distance <= 0.5:
        score = 5
    elif distance <= 1:
        score = 4
    elif distance <= 2:
        score = 3
    elif distance <= 3:
        score = 2
    else:
        score = 1

    return {
        "distance_km": distance,
        "score": score
    }