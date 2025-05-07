import datetime
import json
from .utils.decorators import api
from .utils.response import APIResponse
from .utils.database_connection import get_connection
import pymongo
from bson import ObjectId


TABLE_NAME = "jep_tools__customer_project"


@api
def collection(request):
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    projects = (
        request.db[TABLE_NAME]
        .find({"customer_id": customer_id, "is_deleted": False})
        .sort([("created_at", pymongo.DESCENDING), ("_id", pymongo.DESCENDING)])
    )
    return APIResponse.ok({"projects": list(projects)})


@api
def get(request):
    id = request.pathParameters.get("id")
    if not id:
        return APIResponse.bad_request("id is required")
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")
    project = request.db[TABLE_NAME].find_one(
        {"_id": ObjectId(id), "customer_id": customer_id}
    )
    if not project:
        return APIResponse.not_found()
    return APIResponse.ok(project)


@api
def create(request):
    collection = request.db[TABLE_NAME]
    # copy_project_id = request.pathParameters.get("id") # ObjectId(id)
    # customer_id = request.queryStringParameters.get("customer_id")
    # if copy_project_id and not customer_id:
    #    return APIResponse.bad_request("customer_id is required")

    inc_body = request.body

    datetime_current = datetime.datetime.now(datetime.timezone.utc)

    # if copy_project_id:
    #    copy_project = collection.find_one(
    #        {"_id": copy_project_id, "customer_id": customer_id}
    #    )
    #    if not copy_project:
    #        return APIResponse.not_found("project not found")
    #    current_change = copy_project.get("current")

    current_change = inc_body.get("current")

    new_change = {
        "token": current_change["token"],
        "thumbnail_url": current_change["thumbnail_url"],
        "variant": {
            "id": current_change["variant"].get("id", None),
            "name": current_change["variant"].get("name", None),
        },
        "created_at": datetime_current,
    }

    # check if token_old alread exists in DB
    existing_project = collection.find_one(
        {"changes.token": inc_body["token_old"]}
    )

    available_until = datetime_current + datetime.timedelta(days=30)
    if not existing_project:
        # create new project
        new_project = {
            "name": inc_body.get("name", ""),
            "tool": inc_body["tool"],
            "source": inc_body["source"],
            "customer_id": inc_body["customer_id"],
            "template_name": inc_body.get("template_name", ""),
            "product": {
                "id": inc_body["product"]["id"],
                "name": inc_body["product"]["name"],
                "handle": inc_body["product"]["handle"],
            },
            "changes": [new_change],
            "current": new_change,
            "is_deleted": False,
            "created_at": datetime_current,
            "updated_at": datetime_current,
            "available_until": available_until,
        }
        new_project = collection.insert_one(new_project)
        project = collection.find_one({"_id": new_project.inserted_id})
        return APIResponse.ok(project)
    else:
        # set current to new change and append new change to changes in mongodb
        update_operation = {
            "$push": {"changes": new_change},
            "$set": {
                "current": new_change,
                "updated_at": datetime_current,
                "available_until": available_until,
            },
        }
        if inc_body.get("customer_id") and existing_project.get("customer_id"):
            update_operation["$set"]["customer_id"] = inc_body["customer_id"]

        updated = collection.update_one(
            {"_id": existing_project["_id"]}, update_operation
        )
        if updated.modified_count == 1:
            project = collection.find_one({"_id": existing_project["_id"]})
            return APIResponse.ok(project)

    return APIResponse.error_unknown("unknown error occured")


@api
def update(request):
    project = request.body
    id = request.pathParameters.get("id")
    if not id:
        return APIResponse.bad_request("id is required")
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    updated = request.db[TABLE_NAME].update_one(
        {"_id": ObjectId(id), "customer_id": customer_id}, {"$set": project}
    )
    return APIResponse.ok(updated)


@api
def delete(request):
    id = request.pathParameters.get("id")
    if not id:
        return APIResponse.bad_request("id is required")
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    updated = request.db[TABLE_NAME].update_one(
        {"_id": ObjectId(id), "customer_id": customer_id},
        {
            "$set": {
                "is_deleted": True,
                "deleted_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
    )
    if updated.modified_count == 1:
        return APIResponse.ok_nobody()
    return APIResponse.error_unknown("unknown error occured")


def events_produce(event, context):
    db_connection = get_connection()
    if event.get("Records"):
        for record in event["Records"]:
            body = record["Sns"].get("Message", {})
            if type(body) == str:
                body = json.loads(body)

            collection = db_connection[body["tenant"]][TABLE_NAME]
            # find project by token
            project = collection.find_one({"changes.token": body["token"]})
            if not project:
                raise Exception(f"project by token {body['token']} not found")

            # update project
            updated = collection.update_one(
                {"_id": project["_id"]},
                {
                    "$set": {
                        "available_until": datetime.datetime.fromisoformat(
                            body["expire_date"]
                        ),
                        "sales_order": {
                            "order_id": body["sales_order"]["order_id"],
                            "line_item_id": body["sales_order"]["line_item_id"],
                            "created_at": datetime.datetime.fromisoformat(
                                body["sales_order"]["created_at"]
                            ),
                        },
                        "updated_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ),
                    },
                },
            )
            if updated.modified_count != 1:
                raise Exception("project not updated")
