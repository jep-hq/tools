import base64
import inspect
import json
import logging
import os
import re
import sys
import traceback
import zlib
from functools import wraps
from typing import Any, Callable, Dict, List, Tuple

param_pattern = re.compile(
    r"^<" r"((?P<type>[a-zA-Z0-9-_\.]+)\:)?" r"(?P<name>[a-zA-Z0-9-_\.]+)" r">$"
)

params_expr = re.compile(r"<([a-zA-Z0-9-_\.]+\:)?[a-zA-Z0-9-_\.]+>")


def _url_convert(path: str) -> str:
    path = "^{}$".format(path)  # full match
    path = re.sub(r"<[a-zA-Z0-9-_\.]+>", r"([a-zA-Z0-9-_\.]+)", path)
    path = re.sub(r"<string\:[a-zA-Z0-9-_\.]+>", r"([a-zA-Z0-9-_\.]+)", path)
    path = re.sub(r"<int\:[a-zA-Z0-9-_\.]+>", r"([0-9]+)", path)
    path = re.sub(r"<float\:[a-zA-Z0-9-_\.]+>", "([+-]?[0-9]+.[0-9]+)", path)
    path = re.sub(
        r"<uuid\:[a-zA-Z0-9_]+>",
        "([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        path,
    )

    return path


def _converters(value: str, pathArg: str) -> Any:
    match = param_pattern.match(pathArg)
    if match:
        arg_type = match.groupdict()["type"]
        if arg_type == "int":
            return int(value)
        elif arg_type == "float":
            return float(value)
        elif arg_type == "string":
            return value
        elif arg_type == "uuid":
            return value
        else:
            return value
    else:
        return value


def _path_converters(path: str) -> str:
    path = re.sub(r"<([a-zA-Z0-9-_\.]+\:)?", "{", path)
    return re.sub(r">", "}", path)


class Request:
    def __init__(self):
        self.args = {}
        self.json = {}
        self.data_raw = None
        self.remote_addr = ""
        self.headers = {}

    def get_data(self):
        return self.data_raw


class RouteEntry(object):
    """Decode request path."""

    def __init__(
        self,
        endpoint: Callable,
        path: str,
        method: List = ["GET"],
        cors: bool = True,
        token: bool = False,
        payload_compression_method: str = "",
        binary_b64encode: bool = False,
        ttl=None,
        description: str = None,
        tag: Tuple = None,
    ) -> None:
        """Initialize route object."""
        self.endpoint = endpoint
        self.path = path
        self.openapi_path = _path_converters(self.path)
        self.method = method
        self.cors = cors
        self.token = token
        self.compression = payload_compression_method
        self.b64encode = binary_b64encode
        self.ttl = ttl
        self.description = description or self.endpoint.__doc__
        self.tag = tag
        if self.compression and self.compression not in [
            "gzip",
            "zlib",
            "deflate",
        ]:
            raise ValueError(
                f"'{payload_compression_method}' is not a supported compression"
            )
        self.request = Request()

    def __eq__(self, other) -> bool:
        """Check for equality."""
        return self.__dict__ == other.__dict__

    def _get_path_args(self) -> Tuple:
        route_args = [i.group() for i in params_expr.finditer(self.path)]
        args = [param_pattern.match(arg).groupdict() for arg in route_args]
        return args


class API(object):
    """API."""

    FORMAT_STRING = "[%(name)s] - [%(levelname)s] - %(message)s"

    def __init__(
        self,
        name: str,
        version: str = "0.0.1",
        description: str = None,
        configure_logs: bool = True,
        debug: bool = False,
    ) -> None:
        """Initialize API object."""
        self.name: str = name
        self.description: str = description
        self.version: str = version
        self.routes: Dict = {}
        self.context: Dict = {}
        self.event: Dict = {}
        self.debug: bool = debug
        self.log = logging.getLogger(self.name)
        if configure_logs:
            self._configure_logging()

        self._add_methods_to_route()

    def _add_methods_to_route(self):
        methods = [
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "DELETE",
            "CONNECT",
            "OPTIONS",
            "TRACE",
            "PATCH",
        ]

        for method in methods:
            self.routes[method] = Dict = {}

    def _get_parameters(self, route: RouteEntry) -> List[Dict]:
        argspath_schema = {
            "default": {"type": "string"},
            "string": {"type": "string"},
            "str": {"type": "string"},
            "uuid": {"type": "string", "format": "uuid"},
            "int": {"type": "integer"},
            "float": {"type": "number", "format": "float"},
        }

        args_in_path = route._get_path_args()
        endpoint_args = inspect.signature(route.endpoint).parameters
        endpoint_args_names = list(endpoint_args.keys())

        parameters: List[Dict] = []
        for arg in args_in_path:
            annotation = endpoint_args[arg["name"]]
            endpoint_args_names.remove(arg["name"])

            if arg["type"] is not None:
                schema = argspath_schema[arg["type"]]
            else:
                schema = argspath_schema["default"]

            parameter = {
                "name": arg["name"],
                "in": "path",
                "schema": {"type": schema["type"]},
            }
            if schema.get("format"):
                parameter["schema"]["format"] = schema.get("format")

            if annotation.default is not inspect.Parameter.empty:
                parameter["schema"]["default"] = annotation.default
            else:
                parameter["required"] = True

            parameters.append(parameter)

        for name, arg in endpoint_args.items():
            if name not in endpoint_args_names:
                continue
            parameter = {"name": name, "in": "query", "schema": {}}
            if arg.default is not inspect.Parameter.empty:
                parameter["schema"]["default"] = arg.default
            elif arg.kind == inspect.Parameter.VAR_KEYWORD:
                parameter["schema"]["format"] = "dict"
            else:
                parameter["schema"]["format"] = "string"
                parameter["required"] = True

            parameters.append(parameter)
        return parameters

    def _configure_logging(self) -> None:
        if self._already_configured(self.log):
            return

        handler = logging.StreamHandler(sys.stdout)
        # Timestamp is handled by lambda itself so the
        # default FORMAT_STRING doesn't need to include it.
        formatter = logging.Formatter(self.FORMAT_STRING)
        handler.setFormatter(formatter)
        self.log.propagate = False
        if self.debug:
            level = logging.DEBUG
        else:
            level = logging.ERROR
        self.log.setLevel(level)
        self.log.addHandler(handler)

    def _already_configured(self, log) -> bool:
        if not log.handlers:
            return False

        for handler in log.handlers:
            if isinstance(handler, logging.StreamHandler):
                if handler.stream == sys.stdout:
                    return True

        return False

    def _add_route(self, path: str, endpoint: callable, **kwargs) -> None:
        methods = kwargs.pop("methods", ["GET"])
        cors = kwargs.pop("cors", True)
        token = kwargs.pop("token", "")
        payload_compression = kwargs.pop("payload_compression_method", "")
        binary_encode = kwargs.pop("binary_b64encode", False)
        ttl = kwargs.pop("ttl", None)
        description = kwargs.pop("description", None)
        tag = kwargs.pop("tag", None)

        if kwargs:
            raise TypeError(
                "TypeError: route() got unexpected keyword "
                "arguments: %s" % ", ".join(list(kwargs))
            )

        for method in methods:
            if path in self.routes[method]:
                raise ValueError(
                    'Duplicate route detected: "{}"\n'
                    "URL paths must be unique.".format(path)
                )

            self.routes[method][path] = RouteEntry(
                endpoint,
                path,
                method,
                cors,
                token,
                payload_compression,
                binary_encode,
                ttl,
                description,
                tag,
            )

    def _url_matching(self, url: str, method: str) -> str:
        for path, function in self.routes[method].items():
            route_expr = _url_convert(path)
            expr = re.compile(route_expr)
            if expr.match(url):
                return path

        return ""

    def _get_matching_args(self, route: str, url: str) -> Dict:
        url_expr = re.compile(_url_convert(route))

        route_args = [i.group() for i in params_expr.finditer(route)]
        url_args = url_expr.match(url).groups()

        names = [
            param_pattern.match(arg).groupdict()["name"] for arg in route_args
        ]

        args = [
            _converters(u, route_args[id])
            for id, u in enumerate(url_args)
            if u != route_args[id]
        ]

        return dict(zip(names, args))

    def _validate_token(self, token: str = None) -> bool:
        env_token = os.environ.get("TOKEN")

        if not token or not env_token:
            return False

        if token == env_token:
            return True

        return False

    def route(self, path: str, **kwargs) -> callable:
        """Register route."""

        def _register_view(endpoint):
            self._add_route(path, endpoint, **kwargs)
            return endpoint

        return _register_view

    def pass_context(self, f: callable) -> callable:
        """Decorator: pass the API Gateway context to the function."""

        @wraps(f)
        def new_func(*args, **kwargs) -> callable:
            return f(self.context, *args, **kwargs)

        return new_func

    def pass_event(self, f: callable) -> callable:
        """Decorator: pass the API Gateway event to the function."""

        @wraps(f)
        def new_func(*args, **kwargs) -> callable:
            return f(self.event, *args, **kwargs)

        return new_func

    def response(
        self,
        status: int,
        content_type: str,
        response_body: Any,
        cors: bool = True,
        accepted_methods: Tuple = [],
        accepted_compression: str = "",
        compression: str = "",
        b64encode: bool = False,
        ttl: int = None,
        location: str = None,
        headers: dict = None,
    ):
        """Return HTTP response.
        including response code (status), headers and body

        statusCode = {
            "OK": 200,
            "EMPTY": 204,
            "NOK": 400,
            "FOUND": 302,
            "NOT_FOUND": 404,
            "CONFLICT": 409,
            "ERROR": 500,
        }
        """

        binary_types = [
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

        # statusCode[status]
        messageData = {
            "statusCode": status,
            "headers": {"Content-Type": content_type},
        }
        cors = True
        if cors:
            messageData["headers"]["Access-Control-Allow-Origin"] = "*"
            messageData["headers"]["Access-Control-Allow-Methods"] = ",".join(
                accepted_methods
            )
            messageData["headers"]["Access-Control-Allow-Credentials"] = "true"

        if location:
            messageData["headers"]["Location"] = location

        if compression and compression in accepted_compression:
            messageData["headers"]["Content-Encoding"] = compression
            if isinstance(response_body, str):
                response_body = bytes(response_body, "utf-8")

            if compression == "gzip":
                gzip_compress = zlib.compressobj(
                    9, zlib.DEFLATED, zlib.MAX_WBITS | 16
                )
                response_body = (
                    gzip_compress.compress(response_body)
                    + gzip_compress.flush()
                )
            elif compression == "zlib":
                zlib_compress = zlib.compressobj(
                    9, zlib.DEFLATED, zlib.MAX_WBITS
                )
                response_body = (
                    zlib_compress.compress(response_body)
                    + zlib_compress.flush()
                )
            elif compression == "deflate":
                deflate_compress = zlib.compressobj(
                    9, zlib.DEFLATED, -zlib.MAX_WBITS
                )
                response_body = (
                    deflate_compress.compress(response_body)
                    + deflate_compress.flush()
                )
            else:
                return self.response(
                    500,
                    "application/json",
                    json.dumps(
                        {
                            "errorMessage": f"Unsupported compression mode: {compression}"
                        }
                    ),
                )

        if ttl:
            messageData["headers"]["Cache-Control"] = f"max-age={ttl}"

        if (
            content_type in binary_types or not isinstance(response_body, str)
        ) and b64encode:
            messageData["isBase64Encoded"] = True
            messageData["body"] = base64.b64encode(response_body).decode()
        else:
            messageData["body"] = response_body

        # overwrite headers with custom headers
        if headers:
            messageData["headers"].update(headers)

        return messageData

    def __call__(self, event, context):
        """Initialize route and handlers."""
        self.log.debug(json.dumps(event.get("headers", {})))
        self.log.debug(json.dumps(event.get("queryStringParameters", {})))
        self.log.debug(json.dumps(event.get("pathParameters", {})))

        self.event = event
        self.context = context

        headers = event.get("headers", {}) or {}
        headers = dict((key.lower(), value) for key, value in headers.items())

        resource_path = event.get("path", None)
        if resource_path is None:
            return self.response(
                400,
                "application/json",
                json.dumps({"errorMessage": "Missing route parameter"}),
            )

        http_method = event["httpMethod"]
        url_key = self._url_matching(resource_path, http_method)
        if not url_key:
            return self.response(
                400,
                "application/json",
                json.dumps(
                    {"errorMessage": "not found: {}".format(resource_path)}
                ),
            )

        route_entry = self.routes[http_method][url_key]
        request_params = event.get("multiValueQueryStringParameters", {}) or {}
        request_params_raw = event.get("queryStringParameters", {}) or {}
        if route_entry.token:
            if not self._validate_token(request_params.get("access_token")):
                return self.response(
                    500,
                    "application/json",
                    json.dumps({"message": "Invalid access token"}),
                )
        """
        if http_method not in route_entry.methods:
            return self.response(
                400,
                "application/json",
                json.dumps(
                    {"errorMessage": "Unsupported method: {}".format(http_method)}
                ),
            )
        """

        # remove access_token from kwargs
        request_params.pop("access_token", False)
        request_params_raw.pop("access_token", False)

        function_kwargs = self._get_matching_args(
            route_entry.path, resource_path
        )

        # if http_method == "POST":
        #    function_kwargs.update(dict(body=event.get("body")))

        try:
            route_entry.request.args = request_params.copy()
            route_entry.request.args_raw = request_params_raw.copy()
            route_entry.request.remote_addr = event["requestContext"][
                "identity"
            ]["sourceIp"]
            route_entry.request.headers = headers
            if http_method in ["POST", "PUT", "PATCH"]:
                try:
                    route_entry.request.data_raw = event.get("body", "")
                    route_entry.request.json = json.loads(
                        route_entry.request.data_raw
                    )
                except:
                    route_entry.request.data_raw = None
                    route_entry.request.json = {}

            response = route_entry.endpoint(
                request=route_entry.request, **function_kwargs
            )
        except Exception as err:
            traceback.print_exc()
            self.log.error(str(err))
            response = (
                json.dumps({"errorMessage": str(err)}),
                500,
            )

        content_type = "application/json"
        location = None
        if len(response) > 2:
            content_type = response[2]
        if len(response) > 3:
            location = response[3]

        return self.response(
            response[1],
            content_type,
            response[0],
            cors=route_entry.cors,
            accepted_methods=[route_entry.method],
            accepted_compression=headers.get("accept-encoding", ""),
            compression=route_entry.compression,
            b64encode=route_entry.b64encode,
            ttl=route_entry.ttl,
            location=location,
        )
