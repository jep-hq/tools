import json
import logging
import traceback
from functools import wraps
from bson import ObjectId
from pymongo.errors import PyMongoError
from .database_connection import get_connection

logger = logging.getLogger(__name__)
CUSTOMERS = {
    "yHA3jfw6TJ1fwkyIXYg7E5docfqvCkfyaJdlb0nw": "kleineprints",
    "dIgf2CEBIn8LBdNoysujxaFaIaDVR92T8VqREyzN": "pokal-total",
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
    - Formats responses in correct API Gateway format
    - Adds CORS headers
    - Includes error handling
    - Returns proxy integration compatible responses
    """

    @wraps(handler)
    def wrapper(event, context):
        logger.debug(f"Event: {event}")

        try:
            # Get database connection
            db_connection = get_connection()

            # OPTIONS requests for CORS
            if event.get("httpMethod") == "OPTIONS":
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent",
                        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                        "Access-Control-Allow-Credentials": "true",
                    },
                    "body": "{}",
                }
            customer = CUSTOMERS.get(event.get("headers", {}).get("x-api-key"))
            if not customer:
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized"}),
                }
            # Create Request object
            request = Request(event, context, db=db_connection)

            # Execute handler
            response = handler(request)

            # Handle tuple response from APIResponse methods
            if isinstance(response, tuple) and len(response) == 2:
                body, status_code = response

                # API Gateway expects string for body
                if not isinstance(body, str):
                    body = json.dumps(body, cls=JSONEncoder)

                # Return API Gateway compatible response
                return {
                    "statusCode": status_code,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent",
                        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                        "Access-Control-Allow-Credentials": "true",
                    },
                    "body": body,
                }

            # If the handler returned a direct API Gateway response
            return response

        except PyMongoError as e:
            logger.error(f"MongoDB Error: {str(e)}")
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                },
                "body": json.dumps(
                    {"error": "Database error", "message": str(e)}
                ),
            }
        except Exception as e:
            logger.error(f"Unhandled exception: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                },
                "body": json.dumps(
                    {"error": "Internal server error", "message": str(e)}
                ),
            }

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
