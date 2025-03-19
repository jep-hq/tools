from .utils.decorators import api
from .utils.response import APIResponse


projects = [
    {"id": 1, "name": "Project 1", "customer": "Customer 1"},
    {"id": 2, "name": "Project 2", "customer": "Customer 2"},
]

TABLE_NAME = "jep_tools__customer_project"


@api
def list(request):
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    projects = request.db.get(TABLE_NAME).find({"customer_id": customer_id})
    return APIResponse.ok({"projects": list(projects)})


@api
def get(request):
    id = request.pathParameters.get("id")
    if not id:
        return APIResponse.bad_request("id is required")
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")
    project = request.db.get(TABLE_NAME).find_one(
        {"_id": id, "customer_id": customer_id}
    )
    if not project:
        return APIResponse.not_found()
    return APIResponse.ok(project)


@api
def create(request):
    project = request.body
    new_project = request.db.get(TABLE_NAME).insert_one(project)
    return APIResponse.ok(new_project)


@api
def update(request):
    project = request.body
    id = request.pathParameters.get("id")
    if not id:
        return APIResponse.bad_request("id is required")
    customer_id = request.queryStringParameters.get("customer_id")
    if not customer_id:
        return APIResponse.bad_request("customer_id is required")

    updated = request.db.get(TABLE_NAME).update_one(
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

    deleted = request.db.get(TABLE_NAME).delete_one(
        {"_id": id, "customer_id": customer_id}
    )
    return APIResponse.ok_nobody()
