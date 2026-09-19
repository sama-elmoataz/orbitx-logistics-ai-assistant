import json
import re
import sqlite3
from difflib import SequenceMatcher

import requests
from langchain_core.tools import tool

from src.config import (
    DATABASE_PATH,
    ORS_API_KEY,
)
from src.reranker import (
    create_reranker,
    rerank_documents,
)
from src.retrieval import retrieve_documents


ranker = create_reranker()


EGYPT_LOCATION_HINTS = {
    "egypt",
    "cairo",
    "new cairo",
    "nasr city",
    "heliopolis",
    "maadi",
    "mokattam",
    "zamalek",
    "dokki",
    "mohandessin",
    "giza",
    "6 october",
    "6th october",
    "october city",
    "sheikh zayed",
    "alexandria",
    "mansoura",
    "tanta",
    "ismailia",
    "suez",
    "port said",
    "fayoum",
    "minya",
    "aswan",
    "luxor",
    "hurghada",
    "sharm el sheikh",
}


def get_shipment_record(tracking_id):
    connection = sqlite3.connect(
        DATABASE_PATH
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            tracking_id,
            origin,
            origin_lat,
            origin_lon,
            destination,
            destination_lat,
            destination_lon,
            service,
            status,
            current_location,
            current_lat,
            current_lon,
            expected_delivery,
            last_update,
            delivery_attempts,
            notes
        FROM shipments
        WHERE tracking_id = ?
        """,
        (
            tracking_id.strip().upper(),
        ),
    )

    row = cursor.fetchone()

    connection.close()

    if not row:
        return None

    columns = [
        "tracking_id",
        "origin",
        "origin_lat",
        "origin_lon",
        "destination",
        "destination_lat",
        "destination_lon",
        "service",
        "status",
        "current_location",
        "current_lat",
        "current_lon",
        "expected_delivery",
        "last_update",
        "delivery_attempts",
        "notes",
    ]

    return dict(
        zip(
            columns,
            row,
        )
    )


@tool
def search_knowledge_base(query):
    """
    Search the OrbitX knowledge base for
    company policies, services, pricing,
    restrictions, insurance, returns,
    claims and other company information.
    """

    documents = retrieve_documents(
        query
    )

    ranked_documents = rerank_documents(
        query,
        documents,
        ranker,
    )

    results = []

    for document in ranked_documents:

        page = document.metadata.get(
            "page",
            "unknown",
        )

        if isinstance(
            page,
            int,
        ):
            page += 1

        results.append(
            (
                f"[Source: page {page}]\n"
                f"{document.page_content}"
            )
        )

    return "\n\n".join(
        results
    )


@tool
def track_shipment(tracking_id):
    """
    Track an OrbitX shipment using its
    tracking ID.
    """

    shipment = get_shipment_record(
        tracking_id
    )

    if not shipment:

        return (
            "No OrbitX shipment was found "
            f"with tracking ID "
            f"{tracking_id.strip().upper()}."
        )

    result = {
        "tracking_id":
            shipment["tracking_id"],

        "origin":
            shipment["origin"],

        "destination":
            shipment["destination"],

        "service":
            shipment["service"],

        "status":
            shipment["status"],

        "current_location":
            shipment["current_location"],

        "expected_delivery":
            shipment["expected_delivery"],

        "last_update":
            shipment["last_update"],

        "delivery_attempts":
            shipment["delivery_attempts"],

        "notes":
            shipment["notes"],
    }

    return json.dumps(
        result,
        ensure_ascii=False,
    )


def normalize_location_text(value):
    value = str(
        value
    ).lower().strip()

    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def has_egypt_hint(location):
    normalized = normalize_location_text(
        location
    )

    for hint in EGYPT_LOCATION_HINTS:

        if hint in normalized:
            return True

    return False


def is_egypt_location(
    location_data,
):
    if not location_data:
        return False

    country_code = str(
        location_data.get(
            "country_code",
            "",
        )
    ).strip().upper()

    country = str(
        location_data.get(
            "country",
            "",
        )
    ).strip().lower()

    return (
        country_code
        in {
            "EG",
            "EGY",
        }
        or country == "egypt"
    )


def location_match_score(
    query,
    location_data,
):
    if not location_data:
        return 0.0

    query_text = normalize_location_text(
        query
    )

    candidate_values = [
        location_data.get(
            "name",
            "",
        ),
        location_data.get(
            "locality",
            "",
        ),
        location_data.get(
            "neighbourhood",
            "",
        ),
        location_data.get(
            "county",
            "",
        ),
        location_data.get(
            "region",
            "",
        ),
    ]

    label = location_data.get(
        "label",
        "",
    )

    if label:

        candidate_values.append(
            label.split(
                ","
            )[0]
        )

    scores = []

    for candidate in candidate_values:

        candidate_text = (
            normalize_location_text(
                candidate
            )
        )

        if not candidate_text:
            continue

        similarity = SequenceMatcher(
            None,
            query_text,
            candidate_text,
        ).ratio()

        if (
            query_text
            == candidate_text
        ):
            similarity = 1.0

        elif (
            query_text
            in candidate_text
            or candidate_text
            in query_text
        ):
            similarity = max(
                similarity,
                0.92,
            )

        scores.append(
            similarity
        )

    if not scores:
        return 0.0

    return max(
        scores
    )


def feature_to_location(
    feature,
):
    geometry = feature.get(
        "geometry",
        {},
    )

    coordinates = geometry.get(
        "coordinates"
    )

    if not coordinates:
        return None

    properties = feature.get(
        "properties",
        {},
    )

    return {
        "coordinates":
            coordinates,

        "label":
            properties.get(
                "label",
                "",
            ),

        "name":
            properties.get(
                "name",
                "",
            ),

        "country":
            properties.get(
                "country",
                "",
            ),

        "country_code":
            properties.get(
                "country_a",
                "",
            ),

        "region":
            properties.get(
                "region",
                "",
            ),

        "county":
            properties.get(
                "county",
                "",
            ),

        "locality":
            properties.get(
                "locality",
                "",
            ),

        "neighbourhood":
            properties.get(
                "neighbourhood",
                "",
            ),

        "layer":
            properties.get(
                "layer",
                "",
            ),

        "confidence":
            properties.get(
                "confidence",
                0,
            ),
    }


def select_best_location(
    query,
    features,
):
    locations = []

    for feature in features:

        location = feature_to_location(
            feature
        )

        if location:
            locations.append(
                location
            )

    if not locations:
        return None

    best_location = max(
        locations,
        key=lambda location: (
            location_match_score(
                query,
                location,
            )
        ),
    )

    return best_location


def geocode_location(
    location,
    country_code=None,
):
    if not ORS_API_KEY:
        return None

    location = str(
        location
    ).strip()

    if not location:
        return None

    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )

    params = {
        "text":
            location,

        "size":
            5,

        "layers":
            "coarse",
    }

    if country_code:

        params[
            "boundary.country"
        ] = country_code

    headers = {
        "Authorization":
            ORS_API_KEY
    }

    try:

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        features = data.get(
            "features",
            [],
        )

        return select_best_location(
            location,
            features,
        )

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
    ):
        return None


def resolve_location(
    location,
):
    egypt_result = geocode_location(
        location,
        country_code="EG",
    )

    global_result = geocode_location(
        location
    )

    if (
        not egypt_result
        and not global_result
    ):
        return None

    if (
        egypt_result
        and not global_result
    ):
        return egypt_result

    if (
        global_result
        and not egypt_result
    ):
        return global_result

    if has_egypt_hint(
        location
    ):
        return egypt_result

    if (
        is_egypt_location(
            global_result
        )
    ):
        return global_result

    egypt_score = location_match_score(
        location,
        egypt_result,
    )

    global_score = location_match_score(
        location,
        global_result,
    )

    if (
        not is_egypt_location(
            global_result
        )
        and global_score
        > egypt_score
    ):
        return global_result

    if (
        global_score >= 0.85
        and egypt_score < 0.65
    ):
        return global_result

    return egypt_result


def resolve_quote_locations(
    origin,
    destination,
):
    origin_data = resolve_location(
        origin
    )

    destination_data = (
        resolve_location(
            destination
        )
    )

    if not origin_data:

        return {
            "type":
                "invalid_origin"
        }

    if not destination_data:

        return {
            "type":
                "invalid_destination"
        }

    origin_is_egypt = (
        is_egypt_location(
            origin_data
        )
    )

    destination_is_egypt = (
        is_egypt_location(
            destination_data
        )
    )

    if (
        origin_is_egypt
        and destination_is_egypt
    ):

        return {
            "type":
                "domestic",

            "origin":
                origin_data,

            "destination":
                destination_data,
        }

    return {
        "type":
            "international",

        "origin":
            origin_data,

        "destination":
            destination_data,
    }


def get_route_details(
    origin_coordinates,
    destination_coordinates,
):
    if not ORS_API_KEY:
        return None

    url = (
        "https://api.heigit.org/"
        "openrouteservice/v2/"
        "directions/driving-car/"
        "geojson"
    )

    headers = {
        "Authorization":
            ORS_API_KEY,

        "Content-Type":
            "application/json",

        "Accept":
            "application/geo+json",
    }

    payload = {
        "coordinates": [
            origin_coordinates,
            destination_coordinates,
        ]
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        features = data.get(
            "features",
            [],
        )

        if not features:
            return None

        feature = features[0]

        summary = (
            feature[
                "properties"
            ][
                "summary"
            ]
        )

        route_path = (
            feature[
                "geometry"
            ][
                "coordinates"
            ]
        )

        return {
            "distance_km":
                round(
                    summary[
                        "distance"
                    ]
                    / 1000,
                    2,
                ),

            "duration_minutes":
                round(
                    summary[
                        "duration"
                    ]
                    / 60
                ),

            "route_path":
                route_path,
        }

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
    ):
        return None


def get_shipment_map_data(
    tracking_id,
):
    shipment = get_shipment_record(
        tracking_id
    )

    if not shipment:
        return None

    origin_coordinates = [
        shipment[
            "origin_lon"
        ],
        shipment[
            "origin_lat"
        ],
    ]

    destination_coordinates = [
        shipment[
            "destination_lon"
        ],
        shipment[
            "destination_lat"
        ],
    ]

    current_coordinates = [
        shipment[
            "current_lon"
        ],
        shipment[
            "current_lat"
        ],
    ]

    route_path = []

    distance_km = None
    duration_minutes = None

    if (
        shipment["service"]
        != "International"
    ):

        route = get_route_details(
            origin_coordinates,
            destination_coordinates,
        )

        if route:

            route_path = route[
                "route_path"
            ]

            distance_km = route[
                "distance_km"
            ]

            duration_minutes = route[
                "duration_minutes"
            ]

        else:

            route_path = [
                origin_coordinates,
                destination_coordinates,
            ]

    else:

        route_path = [
            origin_coordinates,
            destination_coordinates,
        ]

    points = [
        {
            "name":
                "Origin",

            "location":
                shipment[
                    "origin"
                ],

            "coordinates":
                origin_coordinates,

            "color": [
                15,
                23,
                42,
            ],
        },

        {
            "name":
                "Latest recorded location",

            "location":
                shipment[
                    "current_location"
                ],

            "coordinates":
                current_coordinates,

            "color": [
                14,
                165,
                233,
            ],
        },

        {
            "name":
                "Destination",

            "location":
                shipment[
                    "destination"
                ],

            "coordinates":
                destination_coordinates,

            "color": [
                37,
                99,
                235,
            ],
        },
    ]

    return {
        "tracking_id":
            shipment[
                "tracking_id"
            ],

        "points":
            points,

        "route_path":
            route_path,

        "distance_km":
            distance_km,

        "duration_minutes":
            duration_minutes,
    }


@tool
def estimate_delivery_quote(
    origin,
    destination,
    weight_kg,
    service_type,
    insurance=False,
    declared_value=0,
):
    """
    Estimate a live OrbitX domestic delivery
    quote within Egypt.

    OrbitX also offers shipping to selected
    international destinations, but
    international pricing is handled
    separately.

    Required information:
    origin, destination, package weight and
    service type.

    Supported domestic services:
    Standard, Express and Same-Day.
    """

    if not ORS_API_KEY:

        return (
            "The delivery quote service "
            "is temporarily unavailable."
        )

    try:

        weight_kg = float(
            weight_kg
        )

    except (
        TypeError,
        ValueError,
    ):

        return (
            "Please provide a valid "
            "package weight."
        )

    if weight_kg <= 0:

        return (
            "Package weight must be "
            "greater than 0 kg."
        )

    if weight_kg > 30:

        return (
            "OrbitX live delivery quotes "
            "support packages up to 30 kg."
        )

    normalized_service = (
        str(
            service_type
        )
        .strip()
        .lower()
        .replace(
            "_",
            "-"
        )
    )

    service_map = {
        "standard":
            "Standard",

        "express":
            "Express",

        "same-day":
            "Same-Day",

        "same day":
            "Same-Day",
    }

    if (
        normalized_service
        not in service_map
    ):

        return (
            "Please choose one of the "
            "supported domestic services: "
            "Standard, Express or Same-Day."
        )

    service = service_map[
        normalized_service
    ]

    location_result = (
        resolve_quote_locations(
            origin,
            destination,
        )
    )

    location_type = (
        location_result[
            "type"
        ]
    )

    if (
        location_type
        == "invalid_origin"
    ):

        return (
            "I couldn't identify the origin "
            "location. Please check the "
            "location name and try again."
        )

    if (
        location_type
        == "invalid_destination"
    ):

        return (
            "I couldn't identify the "
            "destination location. Please "
            "check the location name and "
            "try again."
        )

    origin_data = (
        location_result[
            "origin"
        ]
    )

    destination_data = (
        location_result[
            "destination"
        ]
    )

    if (
        location_type
        == "international"
    ):

        result = {
            "available":
                False,

            "quote_type":
                "international",

            "origin":
                origin_data[
                    "label"
                ],

            "destination":
                destination_data[
                    "label"
                ],

            "origin_country":
                origin_data.get(
                    "country",
                    "",
                ),

            "destination_country":
                destination_data.get(
                    "country",
                    "",
                ),

            "title":
                "International shipment",

            "message":
                (
                    "OrbitX offers shipping to "
                    "selected international "
                    "destinations. Live "
                    "international pricing is "
                    "not available in this "
                    "calculator. Please request "
                    "an international quote "
                    "through OrbitX support."
                ),
        }

        return json.dumps(
            result,
            ensure_ascii=False,
        )

    origin_coordinates = (
        origin_data[
            "coordinates"
        ]
    )

    destination_coordinates = (
        destination_data[
            "coordinates"
        ]
    )

    route = get_route_details(
        origin_coordinates,
        destination_coordinates,
    )

    if not route:

        return (
            "I couldn't calculate a road route "
            "between those locations. Please "
            "check the locations and try again."
        )

    distance_km = route[
        "distance_km"
    ]

    duration_minutes = route[
        "duration_minutes"
    ]

    if (
        service == "Same-Day"
        and distance_km > 60
    ):

        result = {
            "available":
                False,

            "quote_type":
                "domestic_unavailable",

            "service":
                service,

            "reason":
                (
                    "Same-Day delivery is "
                    "available only for routes "
                    "up to 60 km."
                ),

            "recommended_service":
                "Express",

            "origin":
                origin_data[
                    "label"
                ],

            "destination":
                destination_data[
                    "label"
                ],

            "distance_km":
                distance_km,
        }

        return json.dumps(
            result,
            ensure_ascii=False,
        )

    pricing = {
        "Standard": {
            "base_fee":
                45,

            "extra_weight":
                12,

            "distance_rate":
                0.55,

            "distance_threshold":
                30,
        },

        "Express": {
            "base_fee":
                70,

            "extra_weight":
                16,

            "distance_rate":
                0.75,

            "distance_threshold":
                30,
        },

        "Same-Day": {
            "base_fee":
                95,

            "extra_weight":
                20,

            "distance_rate":
                1.00,

            "distance_threshold":
                0,
        },
    }

    rules = pricing[
        service
    ]

    base_fee = float(
        rules[
            "base_fee"
        ]
    )

    extra_weight_fee = 0.0

    if weight_kg > 2:

        extra_weight_fee = (
            weight_kg - 2
        ) * rules[
            "extra_weight"
        ]

    billable_distance = max(
        0,
        distance_km
        - rules[
            "distance_threshold"
        ],
    )

    distance_fee = (
        billable_distance
        * rules[
            "distance_rate"
        ]
    )

    insurance_fee = 0.0

    if insurance:

        try:

            declared_value = float(
                declared_value
            )

        except (
            TypeError,
            ValueError,
        ):

            return (
                "Please provide a valid "
                "declared shipment value."
            )

        if declared_value <= 0:

            return (
                "A declared value is required "
                "when shipment insurance "
                "is selected."
            )

        if declared_value > 50000:

            return (
                "The maximum declared value "
                "supported by this quote tool "
                "is 50,000 EGP."
            )

        insurance_fee = max(
            20,
            declared_value * 0.02,
        )

    subtotal = (
        base_fee
        + extra_weight_fee
        + distance_fee
        + insurance_fee
    )

    estimated_price = round(
        subtotal,
        2,
    )

    result = {
        "available":
            True,

        "quote_type":
            "domestic",

        "origin":
            origin_data[
                "label"
            ],

        "destination":
            destination_data[
                "label"
            ],

        "distance_km":
            distance_km,

        "estimated_drive_time_minutes":
            duration_minutes,

        "weight_kg":
            weight_kg,

        "service":
            service,

        "insurance":
            bool(
                insurance
            ),

        "declared_value":
            (
                float(
                    declared_value
                )
                if insurance
                else 0
            ),

        "price_breakdown": {
            "base_fee":
                round(
                    base_fee,
                    2,
                ),

            "extra_weight_fee":
                round(
                    extra_weight_fee,
                    2,
                ),

            "distance_fee":
                round(
                    distance_fee,
                    2,
                ),

            "insurance_fee":
                round(
                    insurance_fee,
                    2,
                ),

            "subtotal":
                round(
                    subtotal,
                    2,
                ),
        },

        "estimated_price":
            estimated_price,

        "currency":
            "EGP",
    }

    return json.dumps(
        result,
        ensure_ascii=False,
    )


TOOLS = [
    search_knowledge_base,
    track_shipment,
    estimate_delivery_quote,
]