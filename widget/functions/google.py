import os
import datetime
import json
import requests
from .utils.decorators import api
from .utils.response import APIResponse
import pymongo
from bson import ObjectId


TABLE_NAMES = {
    "customer": "customer",
    "google_map_static": "google_map_static",
    "google_places": "google_places",
}


def get_customer(request):
    return request.db[TABLE_NAMES["customer"]].find_one(
        {"api_key": request.event["headers"].get("x-api-key")}
    )


def get_place(place_id):
    """
    Fetch place details from Google Places API by place_id
    """
    api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError(
            "Missing required environment variables: GOOGLE_API_KEY"
        )

    fields = [
        "name",
        "displayName",
        "formattedAddress",
        "location",
        "rating",
        "reviews",
        "photos",
    ]

    # Google Places API - Place Details endpoint
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    params = {
        "key": api_key,
        "fields": ",".join(fields),
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return response.json()


@api
def places(request):
    customer = get_customer(request)
    if not customer:
        return APIResponse.not_authorized()

    # find places by code and customer_id
    place_id = request.pathParameters.get("id")
    if not place_id:
        return APIResponse.bad_request("code is required")
    place = request.db[TABLE_NAMES["google_places"]].find_one(
        {"place_id": place_id, "customer_id": customer["_id"]},
    )

    # ChIJ5Q-z7fsqkUcRGewaeQWCHZA
    should_update = False
    # If place doesn't exist or needs updating
    if not place:
        should_update = True
    elif place.get("updated_at"):
        updated_at = place["updated_at"]
        current_time = datetime.datetime.now(datetime.timezone.utc)

        # Fix the datetime comparison by ensuring both are timezone-aware
        if (
            isinstance(updated_at, datetime.datetime)
            and updated_at.tzinfo is None
        ):
            # Convert naive datetime to aware datetime with UTC timezone
            updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)

        # Now compare the datetimes (both timezone-aware)
        if updated_at < current_time - datetime.timedelta(days=30):
            should_update = True

    if should_update:
        # Get fresh data from Google API
        place_data = get_place(place_id)

        # Prepare document for db
        if not place:
            place = {
                "place_id": place_id,
                "customer_id": customer["_id"],
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }

        place.update(
            {
                "name": place_data.get("name"),
                "displayName": place_data.get("displayName"),
                "address": place_data.get("formattedAddress"),
                "rating": place_data.get("rating"),
                "reviews": place_data.get("reviews"),
                "photos": place_data.get("photos"),
                "location": place_data.get("location"),
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )

        # Insert or update in database
        if "_id" in place:
            request.db[TABLE_NAMES["google_places"]].update_one(
                {"_id": place["_id"]}, {"$set": place}
            )
        else:
            result = request.db[TABLE_NAMES["google_places"]].insert_one(place)
            place["_id"] = result.inserted_id

    # Clean the response before returning
    if "_id" in place and isinstance(place["_id"], ObjectId):
        place["_id"] = str(place["_id"])
    if "customer_id" in place and isinstance(place["customer_id"], ObjectId):
        place["customer_id"] = str(place["customer_id"])

    return APIResponse.ok({"place": place})
