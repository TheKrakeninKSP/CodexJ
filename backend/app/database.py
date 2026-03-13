import os
import ssl
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/codexj")
DB_NAME = os.getenv("MONGODB_DB", "codexj")
MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "10000"))

client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    return client


def get_db():
    return client[DB_NAME]


def _build_client_options() -> dict:
    # Atlas/SRV endpoints require TLS. On some environments, explicitly providing
    # a CA bundle prevents TLS handshake failures.
    options = {
        "serverSelectionTimeoutMS": MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    }

    if MONGODB_URI.startswith("mongodb+srv://"):
        options["tls"] = True
        # Defer import to avoid hard dependency if users are on local Mongo only.
        try:
            import certifi
            options["tlsCAFile"] = certifi.where()
        except ImportError:
            pass

    return options


async def connect_db():
    global client
    client = AsyncIOMotorClient(MONGODB_URI, **_build_client_options())
    try:
        # Ping to verify connection
        await client.admin.command("ping")
        print(f"Connected to MongoDB database '{DB_NAME}'.")
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            "Failed to connect to MongoDB during startup. "
            "If using MongoDB Atlas, verify IP allowlist, URI credentials, and TLS CA trust. "
            f"Python/OpenSSL: {ssl.OPENSSL_VERSION}. "
            "You can also set DB_REQUIRED_ON_STARTUP=false to continue without DB."
        ) from exc
    except PyMongoError as exc:
        raise RuntimeError("MongoDB connection failed during startup.") from exc


async def close_db():
    global client
    if client:
        client.close()
        client = None
        print("MongoDB connection closed.")
