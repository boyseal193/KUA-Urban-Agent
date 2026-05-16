# config.py

IDEALISTA_DEFAULT_FILTERS = {
    "city_slug": "barcelona-barcelona",
    "max_price": 1000000,
    "min_m2": 200,
    "max_m2": 300,
    "property_types": ["locales", "naves"],
    "ground_floor_only": True,
    "sale_only": True,
}


def build_idealista_search_url(filters: dict | None = None) -> str:
    final_filters = IDEALISTA_DEFAULT_FILTERS.copy()

    if filters:
        final_filters.update({k: v for k, v in filters.items() if v is not None})

    city_slug = final_filters["city_slug"]
    parts = []

    if final_filters.get("max_price"):
        parts.append(f"con-precio-hasta_{final_filters['max_price']}")

    if final_filters.get("min_m2"):
        parts.append(f"metros-cuadrados-mas-de_{final_filters['min_m2']}")

    if final_filters.get("max_m2"):
        parts.append(f"metros-cuadrados-menos-de_{final_filters['max_m2']}")

    for property_type in final_filters.get("property_types", []):
        parts.append(property_type)

    if final_filters.get("ground_floor_only"):
        parts.append("en-planta-calle")

    if final_filters.get("sale_only"):
        parts.append("venta-solo-inmueble")

    filter_string = ",".join(parts)

    return f"https://www.idealista.com/en/venta-locales/{city_slug}/{filter_string}/"