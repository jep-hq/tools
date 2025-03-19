import os
from pymongo.mongo_client import MongoClient


DB_URI = os.environ.get("TES_DB_URI")
DB_CONNECTION = MongoClient(DB_URI)


def get_connection():
    global DB_CONNECTION
    if not connection_is_valid():
        DB_CONNECTION = MongoClient(DB_URI)
    return DB_CONNECTION


def connection_is_valid():
    if not DB_CONNECTION:
        return False
    try:
        DB_CONNECTION.server_info()
        return True
    except Exception:
        return False
