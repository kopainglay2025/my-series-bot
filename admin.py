# admin.py
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def is_admin(user_id: int) -> bool:
    try:
        return int(user_id) == int(ADMIN_ID)
    except Exception:
        return False