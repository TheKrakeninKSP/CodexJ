import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "codexj")


def get_client(request: Request) -> AsyncIOMotorClient:
    return request.app.state.mongo_client


def get_db(client=Depends(get_client)):
    return client[DB_NAME]


def get_db_no_deps(db_name: str):
    client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return client[db_name]


async def connect_db(app: FastAPI):
    client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    try:
        # Ping to verify connection
        if not DB_NAME:
            raise RuntimeError("DB_NAME environment variable is not set.")
        await client.admin.command("ping")
        print(f"MongoDB Connection Established.")
        app.state.mongo_client = client
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError("Failed to connect to MongoDB during startup.") from exc
    except PyMongoError as exc:
        raise RuntimeError("MongoDB connection failed during startup.") from exc


async def close_db(app: FastAPI):
    app.state.mongo_client.close()
    print("MongoDB connection closed.")
