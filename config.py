from os import getenv, environ
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API credentials
API_ID = int(getenv("API_ID"))
API_HASH = getenv("API_HASH")
BOT_TOKEN = getenv("BOT_TOKEN")

# Owner and logger details
OWNER_ID = int(getenv("OWNER_ID"))
LOGGER_ID = int(getenv("LOGGER_ID"))

# MongoDB configuration
MONGO_URL = getenv("MONGO_URL")

# Channel and subscription settings
AUTH_CHANNEL = int(getenv("AUTH_CHANNEL"))
FSUB = getenv("FSUB")  # Accepts "True" or "False" as string

# Bot behavior configuration
CACHE_TIME = int(environ["CACHE_TIME"])
FILE_AUTO_DEL_TIMER = int(environ["FILE_AUTO_DEL_TIMER"])

# Miscellaneous
GROUP_LINK = getenv("GROUP_LINK")
COLLECTION_NAME = getenv("COLLECTION_NAME")