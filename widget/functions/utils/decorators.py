import json
import logging
from functools import wraps
from bson import ObjectId
from .database_connection import get_connection
from .aws_lambda_proxy import LambdaApi
from .response import APIResponse

logger = logging.getLogger(__name__)

# Standardized CORS Headers
CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent"
}


# Custom JSON encoder to handle MongoDB ObjectId
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super(JSONEncoder, self).default(obj)


def api(handler):
    """
    Decorator for AWS Lambda functions with API Gateway integration.
    - Formats responses in correct API Gateway format using LambdaApi
    - Adds CORS headers
    - Includes error handling
    - Returns proxy integration compatible responses
    """

    # Create LambdaApi instance for response handling
    lambda_api = LambdaApi("api", debug=True)

    @wraps(handler)
    def wrapper(event, context):
        logger.debug(f"Event: {event}")

        # Create a mock route entry for use with LambdaApi
        class RouteEntry:
            def __init__(self, method, cors=True):
                self.method = method
                self.cors = cors
                self.compression = ""
                self.b64encode = False
                self.ttl = None

        # Get database connection
        db_connection = get_connection()

        http_method = event.get("httpMethod", "GET")
        headers = event.get("headers", {}) or {}
        headers.update(CORS_HEADERS)  # Apply standard CORS headers
        route_entry = RouteEntry(method=http_method)

        # OPTIONS requests for CORS
        if http_method == "OPTIONS":
            return lambda_api.process_response(
                route_entry=route_entry,
                response=(
                    {},
                    200,
                ),  # No need to specify content-type, it's the default
                headers=headers,
            )

        # Create Request object
        request = Request(event, context, db=db_connection["jeptools__widget"])

        # Execute handler
        response = handler(request)

        # Handle tuple response from APIResponse methods
        if isinstance(response, tuple) and len(response) == 2:
            return lambda_api.process_response(
                route_entry=RouteEntry(method=http_method),
                response=response,  # APIResponse already returns properly formatted tuples
                headers=headers,
            )

        # If the handler returned a direct API Gateway response
        return response

    return wrapper


class Request:
    """Encapsulation of Lambda event and context data."""

    def __init__(self, event, context, customer=None, db=None):
        self.event = event
        self.context = context
        self.customer = customer
        self.db = db
        self.method = event.get("httpMethod")
        self.pathParameters = event.get("pathParameters", {}) or {}
        self.queryStringParameters = (
            event.get("queryStringParameters", {}) or {}
        )
        self.body = self._parse_body(event.get("body"))

    def _parse_body(self, body):
        """Parse request body as JSON."""
        if not body:
            return {}
        try:
            return json.loads(body)
        except Exception as e:
            logger.error(f"Error parsing JSON body: {str(e)}")
            return {}
