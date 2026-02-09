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
STRING_SESSION = "1BVtsOLUBu72KFhV7sZVbwUYUFwiZTjtTfx0sa3W9XIyv2hXgJpeUro73Kcfh4eOAbQfY5eaA7F94hu_IJewBZBo8tPxIms5htSviY52VxD0LGfiMHHpaOT_TV3glIJ7kO7qR860KL_uM8man138aKq7Wa0cghYj1XrkkP8maWZTqP3vbn9HBZcPyB2F4SrFvbZqGVrVG2eI8Np4aPmGIbktQ73OTMsHxxw4RhDQuIKpVzHG9GRxoxv199n6g3EnUZEV9LavkxOoAnNYOQmVbgv2gSdY-oOALwg-j5bZx4N27khMph-6X60GQ2wNaAfSXoduVS0Tm76f8Fi0pnJhferIGz4CV_U4="
API_KEY = "HEYBRO1"
# =========================================

CACHE = {}
CACHE_TTL = 300
client = None


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


async def resolve_user(username: str):
    username = username.lstrip("@").strip()

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

    data = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "bio": full.full_user.about if full.full_user else None,
        "status": parse_status(user),
        "is_bot": bool(user.bot),
        "is_verified": bool(user.verified),
        "is_premium": bool(user.premium),
        "is_fake": bool(user.fake),
        "is_scam": bool(user.scam),
    }

    CACHE[username] = (time.time(), data)
    return data


async def channel_stats(username: str):
    try:
        entity = await client.get_entity(username)
    except:
        return None

    if not isinstance(entity, Channel):
        return None

    full = await client(GetFullChannelRequest(entity))
    return {
        "channel_id": entity.id,
        "title": entity.title,
        "subscribers": full.full_chat.participants_count,
        "online": full.full_chat.online_count,
    }


@app.get("/lookup")
async def lookup(username: str, key: str):
    if key != API_KEY:
        raise HTTPException(401, "Invalid API key")

    user = await resolve_user(username)
    ch = await channel_stats(username)

    if ch:
        user["channel"] = ch

    return {
        "ok": True,
        "results": {
            username: user
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
