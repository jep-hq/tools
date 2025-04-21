import base64
import json
import logging
import sys
import zlib
from typing import Any, Dict, List, Optional, Union


class LambdaResponse:
    """Simplified class for creating Lambda responses."""

    BINARY_TYPES = [
        "application/octet-stream",
        "application/x-protobuf",
        "application/x-tar",
        "application/zip",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/webp",
        "image/jp2",
    ]

    @staticmethod
    def create(
        status: int,
        content_type: str,
        body: Any,
        cors: bool = True,
        accepted_methods: List[str] = ["GET"],
        accepted_compression: str = "",
        compression: str = "",
        b64encode: bool = False,
        ttl: Optional[int] = None,
        location: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Creates a formatted Lambda response"""

        response_headers = {"Content-Type": content_type}

        # Add CORS headers
        if cors:
            response_headers.update(
                {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": ",".join(accepted_methods),
                    "Access-Control-Allow-Credentials": "true",
                }
            )

        # Redirection header
        if location:
            response_headers["Location"] = location

        # Cache-Control
        if ttl:
            response_headers["Cache-Control"] = f"max-age={ttl}"

        # Custom headers
        if headers:
            response_headers.update(headers)

        # Prepare response
        response = {
            "statusCode": status,
            "headers": response_headers,
        }

        # Apply compression if supported
        if compression and compression in accepted_compression:
            response_headers["Content-Encoding"] = compression
            body_bytes = body.encode("utf-8") if isinstance(body, str) else body

            match compression:
                case "gzip":
                    compressor = zlib.compressobj(
                        9, zlib.DEFLATED, zlib.MAX_WBITS | 16
                    )
                    body = compressor.compress(body_bytes) + compressor.flush()
                case "zlib":
                    compressor = zlib.compressobj(
                        9, zlib.DEFLATED, zlib.MAX_WBITS
                    )
                    body = compressor.compress(body_bytes) + compressor.flush()
                case "deflate":
                    compressor = zlib.compressobj(
                        9, zlib.DEFLATED, -zlib.MAX_WBITS
                    )
                    body = compressor.compress(body_bytes) + compressor.flush()
                case _:
                    return LambdaResponse.create(
                        500,
                        "application/json",
                        json.dumps(
                            {
                                "errorMessage": f"Unsupported compression mode: {compression}"
                            }
                        ),
                    )

        # Base64 encoding for binary content
        is_binary = (
            content_type in LambdaResponse.BINARY_TYPES
            or not isinstance(body, str)
        )
        if is_binary and b64encode:
            response["isBase64Encoded"] = True
            response["body"] = base64.b64encode(body).decode()
        else:
            response["body"] = body

        return response


class LambdaApi:
    def __init__(self, name: str, debug: bool = False):
        self.name = name
        self.debug = debug
        self.log = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        logger = logging.getLogger(self.name)
        if logger.handlers:
            return logger

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(name)s] - [%(levelname)s] - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.propagate = False
        logger.setLevel(logging.DEBUG if self.debug else logging.ERROR)
        logger.addHandler(handler)
        return logger

    def process_response(self, route_entry, response, headers):
        """Processes the endpoint response"""
        # Default values
        content_type = "application/json"
        location = None

        # Extract optional parameters from the response
        if len(response) > 2:
            content_type = response[2]
        if len(response) > 3:
            location = response[3]

        return LambdaResponse.create(
            status=response[1],
            content_type=content_type,
            body=response[0],
            cors=route_entry.cors,
            accepted_methods=[route_entry.method],
            accepted_compression=headers.get("accept-encoding", ""),
            compression=route_entry.compression,
            b64encode=route_entry.b64encode,
            ttl=route_entry.ttl,
            location=location,
        )

    def handle_error(self, error):
        """Error handling"""
        self.log.error(str(error))
        return LambdaResponse.create(
            status=500,
            content_type="application/json",
            body=json.dumps({"errorMessage": str(error)}),
        )
