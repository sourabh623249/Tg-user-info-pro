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

# ============ ENV CONFIG ============
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
API_KEY = os.getenv("API_KEY")

if not STRING_SESSION or not STRING_SESSION.startswith("1"):
    raise RuntimeError("INVALID STRING_SESSION")
# ===================================

CACHE = {}
CACHE_TTL = 300
client = None


# ============ LIFESPAN ============
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
    version="FINAL",
    lifespan=lifespan
)


# ============ HELPERS ============
def parse_status(user):
    s = user.status
    if isinstance(s, UserStatusOnline):
        return "online"
    if isinstance(s, UserStatusOffline):
        return "offline"
    if isinstance(s, UserStatusRecently):
        return "recently"
    if isinstance(s, UserStatusLastWeek):
        return "last_week"
    if isinstance(s, UserStatusLastMonth):
        return "last_month"
    return "hidden"


# ============ RESOLVER ============
async def resolve_target(q: str):
    q = q.strip()

    if q in CACHE:
        ts, data = CACHE[q]
        if time.time() - ts < CACHE_TTL:
            return data

    # --- chat_id case ---
    if q.lstrip("-").isdigit():
        entity = await client.get_entity(int(q))
    else:
        try:
            r = await client(ResolveUsernameRequest(q.lstrip("@")))
            if r.users:
                entity = r.users[0]
            elif r.chats:
                entity = r.chats[0]
            else:
                raise HTTPException(404, "Not found")
        except (UsernameInvalidError, UsernameNotOccupiedError):
            raise HTTPException(404, "Username not found")

    # --- USER ---
    if isinstance(entity, User):
        full = await client(GetFullUserRequest(entity.id))
        data = {
            "type": "user",
            "id": entity.id,
            "username": entity.username,
            "first_name": entity.first_name,
            "last_name": entity.last_name,
            "lang_code": entity.lang_code,
            "bio": full.full_user.about if full.full_user else None,
            "status": parse_status(entity),
            "flags": {
                "bot": bool(entity.bot),
                "verified": bool(entity.verified),
                "premium": bool(entity.premium),
                "scam": bool(entity.scam),
                "fake": bool(entity.fake),
                "deleted": bool(entity.deleted),
            }
        }

    # --- CHANNEL / GROUP ---
    elif isinstance(entity, Channel):
        full = await client(GetFullChannelRequest(entity))
        data = {
            "type": "channel",
            "id": entity.id,
            "title": entity.title,
            "username": entity.username,
            "subscribers": full.full_chat.participants_count,
            "online_count": full.full_chat.online_count,
            "linked_chat_id": full.full_chat.linked_chat_id
        }

    else:
        raise HTTPException(404, "Unsupported entity")

    CACHE[q] = (time.time(), data)
    return data


# ============ API ============
@app.get("/")
async def root():
    return {
        "service": "Telegram OSINT Ultimate API",
        "status": "running"
    }


@app.get("/lookup")
async def lookup(
    q: str = Query(..., description="username OR chat_id"),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API key")

    data = await resolve_target(q)

    return {
        "ok": True,
        "query": q,
        "data": data
    }


# ============ RUN ============
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
