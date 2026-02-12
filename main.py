import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import (
    User,
    Channel,
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)

# ========== HARDCODED CREDENTIALS ==========
API_ID = 27293496
API_HASH = "d722d4a9b3a05b313f532762475a421b"
BOT_TOKEN = "8120937724:AAHBugYjdjUGAL0AA5mRTfLbr81B6SGh1e0"
API_KEY = "HACK" 
# ===========================================

CACHE = {}
CACHE_TTL = 300
client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = TelegramClient(MemorySession(), API_ID, API_HASH)
    print("[+] Connecting to Telegram...")
    await client.start(bot_token=BOT_TOKEN)
    me = await client.get_me()
    print(f"[+] Bot Started: {me.first_name} (@{me.username})")
    yield
    await client.disconnect()

app = FastAPI(title="TG OSINT Full Engine", lifespan=lifespan)

def parse_status(user):
    if not hasattr(user, 'status') or user.status is None:
        return "hidden/long_ago"
    status_map = {
        UserStatusOnline: "online",
        UserStatusOffline: "offline",
        UserStatusRecently: "recently",
        UserStatusLastWeek: "last_week",
        UserStatusLastMonth: "last_month"
    }
    for cls, label in status_map.items():
        if isinstance(user.status, cls): return label
    return "unknown"

async def resolve_any(q: str):
    q = q.strip()
    if q in CACHE:
        ts, data = CACHE[q]
        if time.time() - ts < CACHE_TTL: return data

    try:
        target = int(q) if q.lstrip("-").isdigit() else q.lstrip("@")
        entity = await client.get_entity(target)
        
        # --- USER DATA ---
        if isinstance(entity, User):
            full = await client(GetFullUserRequest(entity.id))
            photo_url = f"https://t.me/i/userpic/320/{entity.username}.jpg" if entity.username else None
            
            data = {
                "type": "user",
                "id": entity.id,
                "username": f"@{entity.username}" if entity.username else None,
                "first_name": entity.first_name,
                "last_name": entity.last_name,
                "full_name": f"{entity.first_name or ''} {entity.last_name or ''}".strip(),
                "bio": full.full_user.about if full.full_user else None,
                "status": parse_status(entity),
                "dc_id": entity.photo.dc_id if entity.photo else "Unknown",
                "is_bot": bool(entity.bot),
                "is_verified": bool(entity.verified),
                "is_premium": bool(entity.premium),
                "is_scam": bool(entity.scam),
                "is_fake": bool(entity.fake),
                "is_restricted": bool(entity.restricted),
                "restriction_reason": entity.restriction_reason if entity.restricted else None,
                "profile_pic": photo_url,
                "common_chats_count": full.full_user.common_chats_count if hasattr(full.full_user, 'common_chats_count') else 0
            }

        # --- CHANNEL / GROUP DATA ---
        elif isinstance(entity, Channel):
            full = await client(GetFullChannelRequest(entity))
            data = {
                "type": "channel" if entity.broadcast else "group",
                "id": entity.id,
                "title": entity.title,
                "username": f"@{entity.username}" if entity.username else None,
                "about": full.full_chat.about if hasattr(full.full_chat, 'about') else None,
                "subscribers": full.full_chat.participants_count if hasattr(full.full_chat, 'participants_count') else 0,
                "verified": bool(entity.verified),
                "scam": bool(entity.scam),
                "fake": bool(entity.fake),
                "restricted": bool(entity.restricted)
            }
        else:
            raise HTTPException(400, "Unsupported entity")

        CACHE[q] = (time.time(), data)
        return data

    except Exception as e:
        raise HTTPException(404, f"Not Found: {str(e)}")

@app.get("/")
async def home():
    return {"status": "running", "engine": "FastAPI + Telethon"}

@app.get("/lookup")
async def lookup(q: str = Query(..., description="Username or ID"), key: str = Query(...)):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API Key")
    result = await resolve_any(q)
    return {"ok": True, "results": result, "dev": "@HeyBroTech"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
