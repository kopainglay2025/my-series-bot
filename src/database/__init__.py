from umongo.frameworks.motor_asyncio import MotorAsyncIOInstance
from motor.motor_asyncio import AsyncIOMotorClient
import config

# Asynchronous Database Connection
MoviesDB = AsyncIOMotorClient(config.MONGO_URL)

# Database
db = MoviesDB["MoviesBot1"]
instance = MotorAsyncIOInstance(db)


# Collections
usersdb = db["users"]  # Users Collection
chatsdb = db["chats"]  # Chats Collection


# Importing other modules
from .chats import *