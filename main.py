import os
import time
import asyncio
import random
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
    UserStatusLastMonth
)

# ================= ENV =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
API_KEY = os.getenv("API_KEY")

CACHE_TTL = 300
CACHE = {}
client = None
# ======================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = TelegramClient(
        StringSession(STRING_SESSION),
        API_ID,
        API_HASH,
        flood_sleep_threshold=60
    )
    await client.start()
    print("[+] Telethon connected")
    yield
    await client.disconnect()
    print("[-] Telethon disconnected")


app = FastAPI(
    title="Telegram OSINT Ultimate API",
    version="vFinal",
    lifespan=lifespan
)

# ================= HELPERS =================
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


def cache_get(key):
    v = CACHE.get(key)
    if not v:
        return None
    ts, data = v
    if time.time() - ts > CACHE_TTL:
        CACHE.pop(key, None)
        return None
    return data


def cache_set(key, data):
    CACHE[key] = (time.time(), data)


async def anti_ban_sleep():
    await asyncio.sleep(random.uniform(0.3, 0.8))


# ================= CORE =================
async def resolve_username(username: str):
    username = username.lstrip("@").lower().strip()

    cached = cache_get(username)
    if cached:
        return cached

    await anti_ban_sleep()

    try:
        r = await client(ResolveUsernameRequest(username))
    except (UsernameInvalidError, UsernameNotOccupiedError):
        raise HTTPException(404, "Username not found")

    # -------- USER --------
    if r.users:
        u: User = r.users[0]
        full = await client(GetFullUserRequest(u.id))

        data = {
            "type": "user",
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "bio": full.full_user.about if full.full_user else None,
            "status": parse_status(u),
            "flags": {
                "bot": bool(u.bot),
                "verified": bool(u.verified),
                "premium": bool(u.premium),
                "scam": bool(u.scam),
                "fake": bool(u.fake),
                "deleted": bool(u.deleted)
            }
        }

        cache_set(username, data)
        return data

    # -------- CHANNEL / GROUP --------
    if r.chats:
        ch: Channel = r.chats[0]
        full = await client(GetFullChannelRequest(ch))

        data = {
            "type": "channel",
            "id": ch.id,
            "title": ch.title,
            "username": ch.username,
            "subscribers": full.full_chat.participants_count,
            "online": full.full_chat.online_count,
            "linked_chat_id": full.full_chat.linked_chat_id
        }

        cache_set(username, data)
        return data

    raise HTTPException(404, "Entity not found")


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

    data = await resolve_username(username)

    return {
        "ok": True,
        "result": data
    }


@app.post("/bulk")
async def bulk(
    usernames: list[str],
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API key")

    results = {}
    for u in usernames[:20]:
        try:
            results[u] = await resolve_username(u)
        except Exception as e:
            results[u] = {"error": str(e)}

    return {
        "ok": True,
        "count": len(results),
        "results": results
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
