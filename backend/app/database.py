import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/codexj")

client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    return client


def get_db():
    return client["codexj"]


async def connect_db():
    global client
    client = AsyncIOMotorClient(MONGODB_URI)
    # Ping to verify connection
    await client.admin.command("ping")
    print("Connected to MongoDB.")


async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")
