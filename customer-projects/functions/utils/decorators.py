import json
from functools import wraps
import logging
from .database_connection import get_connection

logger = logging.getLogger()

CUSTOMERS = {
    "yHA3jfw6TJ1fwkyIXYg7E5docfqvCkfyaJdlb0nw": "kleineprints",
    "dIgf2CEBIn8LBdNoysujxaFaIaDVR92T8VqREyzN": "pokal-total",
}


class Request:
    db = None
    customer = None
    method = None
    queryStringParameters = None
    pathParameters = None
    body = None
    context = None

    def __init__(self, event, context, customer, db_connection):
        self.db = db_connection
        self.customer = customer
        self.event = event
        self.context = context
        self.method = event.get("httpMethod")
        self.queryStringParameters = event.get("queryStringParameters")
        self.pathParameters = event.get("pathParameters")
        # if body is a string, parse it as JSON
        if isinstance(event.get("body"), str):
            self.body = json.loads(event.get("body"))
        else:
            self.body = event.get("body", {})


def api(handler):
    """
    Decorator für AWS Lambda Handler, der Antworten entsprechend formatiert
    und Fehlerbehandlung bietet.
    """

    @wraps(handler)
    async def wrapper(event, context):
        try:
            # OPTIONS requests answers with 200 OK
            if event.get("httpMethod") == "OPTIONS":
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Credentials": True,
                    },
                    "body": json.dumps({}),
                }

            # get customer from headers
            customer = CUSTOMERS.get(event.get("headers", {}).get("x-api-key"))
            if not customer:
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized"}),
                }

            response = await handler(
                Request(event, context, customer, get_connection())
            )

            # Sicherstellen, dass wir ein standardisiertes Antwortformat haben
            if not isinstance(response, dict):
                response = {"statusCode": 200, "body": response}

            # Standardwerte für statusCode und body
            status_code = response.get("statusCode", 200)
            body = response.get("body", {})

            # Konvertiere body zu JSON-String, wenn es kein String ist
            if not isinstance(body, str):
                body = json.dumps(body, default=str)

            # Rückgabe im API-Gateway-Format
            return {
                "statusCode": status_code,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": True,
                },
                "body": body,
            }
        except Exception as e:
            logger.error(f"Unbehandelte Ausnahme: {str(e)}")
            error_response = {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": True,
                },
                "body": json.dumps({"error": "Internal Server Error"}),
            }
            return error_response

    return wrapper
