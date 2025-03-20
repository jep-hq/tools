import datetime
from .utils.decorators import api
from .utils.response import APIResponse


TABLE_NAME = "jep_tools__customer_project"


@api
def collection(request):
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    projects = request.db[TABLE_NAME].find({"customer_id": customer_id})
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
        {"_id": id, "customer_id": customer_id}
    )
    if not project:
        return APIResponse.not_found()
    return APIResponse.ok(project)


@api
def create(request):
    collection = request.db[TABLE_NAME]
    copy_project_id = request.pathParameters.get("id")
    customer_id = request.pathParameters.get("id")
    if copy_project_id and not customer_id:
        return APIResponse.bad_request("customer_id is required")

    inc_body = request.body

    datetime_current = datetime.datetime.now(datetime.timezone.utc)

    if copy_project_id:
        copy_project = collection.find_one(
            {"_id": copy_project_id, "customer_id": customer_id}
        )
        if not copy_project:
            return APIResponse.not_found("project not found")

        current_change = copy_project.get("current")

    current_change = inc_body.get("current")

    new_change = {
        "token": current_change["token"],
        "thumbnail_url": current_change["thumbnail_url"],
        "variant": {
            "id": current_change["variant"]["id"],
            "name": current_change["variant"]["name"],
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
            "product": {
                "id": inc_body["product"]["id"],
                "name": inc_body["product"]["name"],
                "handle": inc_body["product"]["handle"],
            },
            "changes": [new_change],
            "current": new_change,
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
        {"_id": id, "customer_id": customer_id}, {"$set": project}
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

    deleted = request.db[TABLE_NAME].delete_one(
        {"_id": id, "customer_id": customer_id}
    )
    if deleted.deleted_count == 0:
        return APIResponse.not_found()
    return APIResponse.ok_nobody()
