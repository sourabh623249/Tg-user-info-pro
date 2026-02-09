import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
    Channel
)

# ================= CONFIG =================
API_ID = 39826607
API_HASH = "186e5c1ce0542f87a7a2f00f08ab3afb"
STRING_SESSION = "PUT_YOUR_STRING_SESSION_HERE"
API_KEY = "HEYBRO1"
# =========================================

CACHE = {}
CACHE_TTL = 300
client = None


# ================= LIFESPAN =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = TelegramClient(
        StringSession(STRING_SESSION),
        API_ID,
        API_HASH
    )
    await client.start()
    print("[+] Telethon connected")

    yield

    await client.disconnect()
    print("[-] Telethon disconnected")


app = FastAPI(
    title="Telegram OSINT Ultimate API",
    version="FINAL-RICH",
    lifespan=lifespan
)


# ================= HELPERS =================
def parse_status(user):
    if isinstance(user.status, UserStatusOnline):
        return "online"
    if isinstance(user.status, UserStatusOffline):
        return "offline"
    if isinstance(user.status, UserStatusRecently):
        return "recently"
    if isinstance(user.status, UserStatusLastWeek):
        return "last_week"
    if isinstance(user.status, UserStatusLastMonth):
        return "last_month"
    return "unknown"


# ================= CORE USER =================
async def resolve_user(username: str):
    # auto-fix wrong inputs like telegram=TTN5PANEL
    username = username.split("=")[-1].lstrip("@").strip()

    if username in CACHE:
        ts, data = CACHE[username]
        if time.time() - ts < CACHE_TTL:
            return data

    try:
        r = await client(ResolveUsernameRequest(username))
    except (UsernameInvalidError, UsernameNotOccupiedError):
        raise HTTPException(404, "Username not found")

    if not r.users:
        raise HTTPException(404, "No user data")

    user = r.users[0]
    full = await client(GetFullUserRequest(user.id))

    profile_photo_cdn = (
        f"https://t.me/i/userpic/320/{user.username}.jpg"
        if user.username and user.photo else None
    )

    data = {
        "user_id": user.id,
        "access_hash": user.access_hash,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "lang_code": user.lang_code,

        "status": parse_status(user),
        "bio": full.full_user.about if full.full_user else None,

        "is_bot": bool(user.bot),
        "is_verified": bool(user.verified),
        "is_premium": bool(user.premium),
        "is_scam": bool(user.scam),
        "is_fake": bool(user.fake),
        "is_deleted": bool(user.deleted),

        "has_profile_photo": bool(user.photo),
        "profile_photo_cdn": profile_photo_cdn,
        "dc_id": user.photo.dc_id if user.photo else None,
    }

    CACHE[username] = (time.time(), data)
    return data


# ================= CHANNEL STATS =================
async def channel_stats(username: str):
    try:
        entity = await client.get_entity(username)
    except Exception:
        return None

    if not isinstance(entity, Channel):
        return None

    full = await client(GetFullChannelRequest(entity))

    return {
        "channel_id": entity.id,
        "title": entity.title,
        "username": entity.username,
        "subscribers": full.full_chat.participants_count,
        "online_count": full.full_chat.online_count,
        "linked_chat_id": full.full_chat.linked_chat_id
    }


# ================= API =================
@app.get("/")
async def root():
    return {
        "service": "Telegram OSINT Ultimate API",
        "status": "running",
        "cache_size": len(CACHE)
    }


@app.get("/lookup")
async def lookup(
    username: str = Query(...),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API key")

    clean_username = username.split("=")[-1].lstrip("@").strip()

    user_data = await resolve_user(clean_username)

    ch = await channel_stats(clean_username)
    if ch:
        user_data["channel_stats"] = ch

    return {
        "ok": True,
        "count": 1,
        "results": {
            clean_username: {
                "ok": True,
                "data": user_data
            }
        }
    }


# ================= RUN =================
if __name__ == "__main__":
    import uvicorn
    print("[+] Telegram OSINT Ultimate API")
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
