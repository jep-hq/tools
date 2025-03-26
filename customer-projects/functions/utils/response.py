import json
import logging
from bson import json_util

logger = logging.getLogger(__name__)


class APIResponse:
    @staticmethod
    def _track_message(message, detail, level="warning"):
        if level == "error":
            logger.error(f"{message}: {detail}")
        else:
            logger.warning(f"{message}: {detail}")

    @staticmethod
    def not_authorized(message="not authorized", detail=""):
        APIResponse._track_message(message, detail)
        return json.dumps({"error": message}, default=str), 401

    @staticmethod
    def error_unknown(message="unknown error occured", detail=""):
        APIResponse._track_message(message, detail)
        return json.dumps({"error": message}, default=str), 500

    @staticmethod
    def ok(data):
        return json.dumps(data, default=str), 200

    @staticmethod
    def ok_nobody():
        return "", 204

    @staticmethod
    def not_found(message="not found", detail=""):
        APIResponse._track_message(message, detail)
        return json.dumps({"error": message}, default=str), 404

    @staticmethod
    def bad_request(message="bad request", detail=""):
        APIResponse._track_message(message, detail)
        return json.dumps({"error": message}, default=str), 400
