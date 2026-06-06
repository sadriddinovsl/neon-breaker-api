import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        os.getenv("Render"),
        min_size=2,
        max_size=10,
        statement_cache_size=0  # обязательно для Supabase pooler
    )

async def get_pool():
    return pool