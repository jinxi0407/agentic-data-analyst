"""Small read-only entity context shared by direct and interactive queries."""

import json
from functools import lru_cache

from app.tools.database import fetch_all


@lru_cache(maxsize=1)
def city_metadata():
    rows = fetch_all("SELECT DISTINCT city, province FROM users ORDER BY city, province")
    result = []
    for row in rows:
        city = row["city"]
        alias = city[:-1] if city.endswith("市") else city
        matches = [r for r in rows if r["city"].removesuffix("市") == alias]
        result.append({"field": "users.city", "value": city, "province": row["province"],
                       "verified_aliases": [alias] if len(matches) == 1 else []})
    return result


def entity_context():
    return ("Verified city storage values and same-city suffix aliases (not region mappings):\n"
            + json.dumps(city_metadata(), ensure_ascii=False)
            + "\nOnly normalize a city to its uniquely verified same-city value. Do not infer a city "
            "from a province/region. An absent named city remains that city; empty results are valid. "
            "Do not replace it with an existing city or ask merely because no rows exist.")
