import os, json, asyncio, time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto
from keep_alive import keep_alive

# ==== CONFIG ====
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION_STRING")
OWNER_ID = int(os.getenv("OWNER_ID"))
WAIFU_BOT_ID = int(os.getenv("WAIFU_BOT_ID"))
GRAB_KEYWORD = "/grab"
DB_FILE = "db.json"

# ==== LOAD DB ====
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Warning: {DB_FILE} contains invalid JSON.")
        return {}

DB = load_db()

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving database: {e}")
        return False

# ==== STATES ====
chat_states = {}  # {chat_id: {"grab": True}}
grab_global = True
bot_start_time = time.time()

# ==== CLIENT ====
client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

# ==== OWNER ONLY DECORATOR ====
def owner_only(func):
    async def wrapper(event):
        if event.sender_id != OWNER_ID:
            await event.reply("❌ You are not authorized")
            return
        await func(event)
    return wrapper

def is_grab_on(chat_id):
    return grab_global and chat_states.get(chat_id, {}).get("grab", False)

# ==== UNIQUE IMAGE ID ====
def get_unique_image_id(photo):
    if hasattr(photo, 'file_reference') and photo.file_reference:
        return f"ref_{photo.file_reference.hex()}"
    elif hasattr(photo, 'id') and hasattr(photo, 'access_hash'):
        return f"{photo.id}_{photo.access_hash}"
    return str(getattr(photo, 'id', 'unknown'))

def find_character_by_id(image_id):
    if not image_id:
        return None
    if grab_global is False:
        return None
    if image_id in DB:
        return DB[image_id]
    for stored_id, name in DB.items():
        if '_' in image_id and '_' in stored_id:
            if image_id.split('_')[0] == stored_id.split('_')[0]:
                return name
    return None

# ==== AUTOGRAB ====
@client.on(events.NewMessage())
async def autograb_handler(event):
    if not event.message:
        return
    if WAIFU_BOT_ID and event.sender_id != WAIFU_BOT_ID:
        return
    if not event.media or not isinstance(event.media, MessageMediaPhoto):
        return
    if GRAB_KEYWORD.lower() not in (event.message.message or "").lower():
        return
    if not is_grab_on(event.chat_id):
        return

    photo = event.media.photo
    unique_id = get_unique_image_id(photo)
    char_name = find_character_by_id(unique_id)
    if char_name:
        try:
            await event.reply(f"/grab {char_name}")
        except: pass
    else:
        await event.reply(GRAB_KEYWORD)

# ==== ADD CHARACTER ====
@client.on(events.NewMessage(pattern=r"^/addchar (.+)$"))
@owner_only
async def add_character(event):
    char_name = event.pattern_match.group(1).strip()
    reply = await event.get_reply_message()
    if not reply or not reply.media or not isinstance(reply.media, MessageMediaPhoto):
        await event.reply("❌ Reply to a message with an image to add character")
        return
    photo = reply.media.photo
    unique_id = get_unique_image_id(photo)
    DB[unique_id] = char_name
    if save_db():
        await event.reply(f"✅ Added {char_name}\nID: `{unique_id}`")
    else:
        await event.reply("❌ Error saving database")

# ==== GRAB ON/OFF ====
@client.on(events.NewMessage(pattern=r"^/grab on$"))
@owner_only
async def grab_on(event):
    chat_states.setdefault(event.chat_id, {})["grab"] = True
    await event.reply("✅ Grab ON (this chat)")

@client.on(events.NewMessage(pattern=r"^/grab off$"))
@owner_only
async def grab_off(event):
    chat_states.setdefault(event.chat_id, {})["grab"] = False
    await event.reply("🛑 Grab OFF (this chat)")

@client.on(events.NewMessage(pattern=r"^/grab onall$"))
@owner_only
async def grab_onall(event):
    global grab_global
    grab_global = True
    await event.reply("🌍 Grab ON (all chats)")

@client.on(events.NewMessage(pattern=r"^/grab offall$"))
@owner_only
async def grab_offall(event):
    global grab_global
    grab_global = False
    await event.reply("🌍 Grab OFF (all chats)")

# ==== STATUS ====
@client.on(events.NewMessage(pattern=r"^/status$"))
@owner_only
async def status(event):
    uptime_seconds = int(time.time() - bot_start_time)
    h, m, s = uptime_seconds // 3600, (uptime_seconds % 3600) // 60, uptime_seconds % 60
    st = chat_states.get(event.chat_id, {})
    msg = f"""📊 Status:
⏰ Uptime: {h:02d}:{m:02d}:{s:02d}
🌍 Grab Global: {"✅" if grab_global else "❌"}
🎯 Grab Here: {"✅" if st.get("grab", False) else "❌"}
📚 DB Entries: {len(DB)}
"""
    await event.reply(msg)

# ==== MAIN ====
async def main():
    keep_alive()
    await client.start()
    print("🚀 Bot started")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
