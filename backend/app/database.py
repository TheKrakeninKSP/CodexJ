import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME")

client: AsyncIOMotorClient


def get_client() -> AsyncIOMotorClient:
    return client


def get_db():
    global client
    if not DB_NAME:
        raise RuntimeError("DB_NAME environment variable is not set.")
    return client[DB_NAME]


async def connect_db():
    global client
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        # Ping to verify connection
        if not DB_NAME:
            raise RuntimeError("DB_NAME environment variable is not set.")
        await client.admin.command("ping")
        print(f"MongoDB Connection Established.")
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError("Failed to connect to MongoDB during startup.") from exc
    except PyMongoError as exc:
        raise RuntimeError("MongoDB connection failed during startup.") from exc


async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")
