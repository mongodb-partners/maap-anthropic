from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import logging
import logging.handlers
import asyncio
import os
import threading
import uvicorn

# Load environment variables
load_dotenv()

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = "event_logs"
MONGODB_COLLECTION = "logs"

# Async MongoDB client
mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[MONGODB_DB_NAME]
collection = db[MONGODB_COLLECTION]

# Directory path for logs
logs_dir = "logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)
    print(f"Created directory: {logs_dir}")
else:
    print(f"Directory '{logs_dir}' already exists.")

# Configure file-based logging
log_file_name = f"./{logs_dir}/BufferedLogging.log"
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
file_handler = logging.handlers.TimedRotatingFileHandler(
    log_file_name, when="midnight", backupCount=10
)
file_handler.suffix = "%Y-%m-%d.log"
file_handler.setFormatter(formatter)

# Logger setup
logger = logging.getLogger("maap_logger")
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)


# Pydantic model for incoming log requests
class LogRequest(BaseModel):
    level: str
    message: str
    app_name: str


# Log buffer and lock
log_buffer = []
log_lock = threading.Lock()
flush_interval = int(os.getenv("FLUSH_INTERVAL", 60))  # Default to 60 seconds
delete_logs_older_than = int(
    os.getenv("DELETE_LOGS_OLDER_THAN", 30)
)  # Default to 30 days


async def flush_logs():
    """
    Periodically flush logs from the buffer to MongoDB.
    """
    global log_buffer
    while True:
        await asyncio.sleep(flush_interval)
        with log_lock:
            buffer_copy = log_buffer[:]
            log_buffer.clear()

        if buffer_copy:
            try:
                await collection.insert_many(buffer_copy)
                logger.info(f"Flushed {len(buffer_copy)} logs to MongoDB.")
            except Exception as e:
                logger.error(f"Failed to flush logs to MongoDB: {e}")


async def delete_old_logs():
    """
    Periodically delete log files older than the configured number of days.
    """
    while True:
        await asyncio.sleep(86400)  # Check once every 24 hours
        cutoff_date = datetime.now() - timedelta(days=delete_logs_older_than)
        for file_name in os.listdir(logs_dir):
            file_path = os.path.join(logs_dir, file_name)
            if os.path.isfile(file_path):
                file_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_modified_time < cutoff_date:
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted old log file: {file_name}")
                    except Exception as e:
                        logger.error(f"Failed to delete log file {file_name}: {e}")


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown.
    Initialize the capped collection and start background tasks during startup.
    """
    # Ensure the capped collection exists
    collection_list = await db.list_collection_names()
    if MONGODB_COLLECTION not in collection_list:
        try:
            await db.create_collection(
                MONGODB_COLLECTION,
                capped=True,
                size=1073741824,  # 1 GB (in bytes)
                max=100000,  # Max 100,000 documents
            )

            logger.info(f"Capped collection '{MONGODB_COLLECTION}' created.")
        except Exception as e:
            logger.error(f"Error creating capped collection: {e}")
    else:
        logger.info(f"Capped collection '{MONGODB_COLLECTION}' already exists.")

    # Start background tasks
    flusher_task = asyncio.create_task(flush_logs())
    deleter_task = asyncio.create_task(delete_old_logs())

    try:
        yield  # Startup complete, yield control back to the app
    finally:
        flusher_task.cancel()
        deleter_task.cancel()
        try:
            await flusher_task
            await deleter_task
        except asyncio.CancelledError:
            pass


# FastAPI app initialization with lifespan
app = FastAPI(
    title="MAAP Buffered Async Logging Service",
    version="1.0",
    lifespan=lifespan_context,
)


# API endpoints
@app.post("/log")
async def log_message(request: LogRequest):
    """
    Log a message to file and buffer it for MongoDB.
    """
    log_level = request.level.upper()
    if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise HTTPException(status_code=400, detail="Invalid log level")

    # Log the message to file
    log_function = getattr(logger, log_level.lower())
    log_message = f"[{request.app_name}] {request.message}"
    log_function(log_message)

    # Prepare log document
    log_document = {
        "timestamp": datetime.now().isoformat(),
        "level": log_level,
        "message": request.message,
        "app_name": request.app_name,
    }

    # Add log to buffer
    with log_lock:
        log_buffer.append(log_document)

    return {"status": "success", "message": "Log recorded"}


@app.get("/")
async def root():
    """
    Health check endpoint.
    """
    return {"status": "Logging service is running..."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8181)
