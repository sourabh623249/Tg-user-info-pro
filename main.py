import os
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
    User,
    Channel,
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)

# ================= ENV =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
API_KEY = os.getenv("API_KEY")

if not STRING_SESSION or not STRING_SESSION.startswith("1"):
    raise RuntimeError("INVALID STRING_SESSION")
# =======================================

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
    version="FINAL-RICH-NO-LOSS",
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


# ================= CORE RESOLVER =================
async def resolve_any(target: str):
    target = target.strip()

    if target in CACHE:
        ts, data = CACHE[target]
        if time.time() - ts < CACHE_TTL:
            return data

    # -------- resolve by chat_id --------
    if target.lstrip("-").isdigit():
        entity = await client.get_entity(int(target))
    else:
        try:
            r = await client(ResolveUsernameRequest(target.lstrip("@")))
            if r.users:
                entity = r.users[0]
            elif r.chats:
                entity = r.chats[0]
            else:
                raise HTTPException(404, "Not found")
        except (UsernameInvalidError, UsernameNotOccupiedError):
            raise HTTPException(404, "Username not found")

    # ================= USER =================
    if isinstance(entity, User):
        full = await client(GetFullUserRequest(entity.id))

        profile_photo_cdn = (
            f"https://t.me/i/userpic/320/{entity.username}.jpg"
            if entity.username and entity.photo else None
        )

        data = {
            "type": "user",
            "user_id": entity.id,
            "access_hash": entity.access_hash,
            "username": entity.username,
            "first_name": entity.first_name,
            "last_name": entity.last_name,
            "lang_code": entity.lang_code,

            "status": parse_status(entity),
            "bio": full.full_user.about if full.full_user else None,

            "is_bot": bool(entity.bot),
            "is_verified": bool(entity.verified),
            "is_premium": bool(entity.premium),
            "is_scam": bool(entity.scam),
            "is_fake": bool(entity.fake),
            "is_deleted": bool(entity.deleted),

            "has_profile_photo": bool(entity.photo),
            "profile_photo_cdn": profile_photo_cdn,
            "dc_id": entity.photo.dc_id if entity.photo else None,
        }

    # ================= CHANNEL / GROUP =================
    elif isinstance(entity, Channel):
        full = await client(GetFullChannelRequest(entity))

        data = {
            "type": "channel",
            "channel_id": entity.id,
            "title": entity.title,
            "username": entity.username,
            "subscribers": full.full_chat.participants_count,
            "online_count": full.full_chat.online_count,
            "linked_chat_id": full.full_chat.linked_chat_id
        }

    else:
        raise HTTPException(404, "Unsupported entity")

    CACHE[target] = (time.time(), data)
    return data


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
    q: str = Query(..., description="username OR chat_id"),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API key")

    data = await resolve_any(q)

    return {
        "ok": True,
        "count": 1,
        "results": {
            q: {
                "ok": True,
                "data": data
            }
        }
    }


# ================= RUN =================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
