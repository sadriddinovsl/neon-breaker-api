from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import hashlib, hmac, urllib.parse, os, json
from database import init_db, get_pool
from dotenv import load_dotenv

load_dotenv()

# ── Lifespan (запуск БД) ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

# ── Создаём app ───────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sadriddinovsl.github.io"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Проверка подписи Telegram ─────────────────────────────────────
def verify_telegram_data(init_data: str) -> dict | None:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", os.getenv("BOT_TOKEN").encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if hmac.compare_digest(expected, received_hash):
            return json.loads(parsed.get("user", "{}"))
        return None
    except Exception:
        return None

# ── Модели ────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    init_data: str
    language: str = "ru"

class SaveResultRequest(BaseModel):
    init_data: str
    score: int
    round: int

# ── Регистрация ───────────────────────────────────────────────────
@app.post("/api/register")
async def register(req: RegisterRequest):
    user = verify_telegram_data(req.init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid Telegram data")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, language)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name
        """, user["id"], user.get("username"), user.get("first_name"), user.get("last_name"), req.language)

        await conn.execute("""
            INSERT INTO user_stats (telegram_id) VALUES ($1)
            ON CONFLICT DO NOTHING
        """, user["id"])

        stats = await conn.fetchrow(
            "SELECT * FROM user_stats WHERE telegram_id = $1", user["id"]
        )

    return {
        "ok": True,
        "user": {"id": user["id"], "first_name": user.get("first_name")},
        "stats": dict(stats)
    }

# ── Сохранить результат ───────────────────────────────────────────
@app.post("/api/save-result")
async def save_result(req: SaveResultRequest):
    user = verify_telegram_data(req.init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid Telegram data")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO game_sessions (telegram_id, score, round_reached)
            VALUES ($1, $2, $3)
        """, user["id"], req.score, req.round)

        await conn.execute("""
            UPDATE user_stats SET
                best_score   = GREATEST(best_score, $2),
                best_round   = GREATEST(best_round, $3),
                games_played = games_played + 1,
                total_score  = total_score + $2,
                total_coins  = total_coins + $2,
                updated_at   = NOW()
            WHERE telegram_id = $1
        """, user["id"], req.score, req.round)

    return {"ok": True, "coins_earned": req.score}

# ── Статистика ────────────────────────────────────────────────────
@app.get("/api/stats/{telegram_id}")
async def get_stats(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            "SELECT * FROM user_stats WHERE telegram_id = $1", telegram_id
        )
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(stats)

# ── Лидерборд ─────────────────────────────────────────────────────
@app.get("/api/leaderboard")
async def leaderboard():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.first_name, u.username, s.best_score, s.games_played
            FROM user_stats s
            JOIN users u ON u.telegram_id = s.telegram_id
            ORDER BY s.best_score DESC
            LIMIT 10
        """)
    return [dict(r) for r in rows]