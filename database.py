import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

pool = None

async def init_db():
    global pool
    db_url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL = {db_url}")  # покажет в логах что читается
    if not db_url:
        raise Exception("DATABASE_URL is not set!")
    pool = await asyncpg.create_pool(
        db_url,
        min_size=2,
        max_size=10,
        statement_cache_size=0
    )

async def get_pool():
    return pool
