import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), min_size=2, max_size=10)

async def get_pool():
    return pool