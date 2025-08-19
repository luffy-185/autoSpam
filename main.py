import json
import asyncio
import logging
import threading
from datetime import datetime
from typing import Dict, Set
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto

# Import keep_alive Flask server
try:
    from keep_alive import keep_alive
    KEEP_ALIVE_AVAILABLE = True
except ImportError:
    print("⚠️ keep_alive.py not found - running without web server")
    KEEP_ALIVE_AVAILABLE = False

# ==== CONFIG ====
API_ID = int(os.getenv("API_ID"))
API_HASH = int(os.getenv("API_HASH"))
SESSION = int(os.getenv("SESSION_STRING"))
BOT_USERNAME = "slave_waifu_bot"
DB_FILE = "ZDbx.json"

# ==== GLOBAL STATE ====
class AutoGrabState:
    def __init__(self):
        self.enabled_chats: Set[int] = set()  # Chat IDs where grab is enabled
        self.global_enabled: bool = False     # Global on/off state
        self.db: Dict[str, str] = {}         # Photo ID -> Name mapping
        self.start_time = datetime.now()     # Bot start time
        
    def load_db(self):
        """Load the character database"""
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                self.db = json.load(f)
            print(f"✅ Loaded DB with {len(self.db)} entries")
        except FileNotFoundError:
            print(f"❌ DB file {DB_FILE} not found!")
            self.db = {}
        except Exception as e:
            print(f"❌ Error loading DB: {e}")
            self.db = {}
    
    def is_enabled(self, chat_id: int) -> bool:
        """Check if auto-grab is enabled for a chat"""
        return self.global_enabled or chat_id in self.enabled_chats
    
    def enable_chat(self, chat_id: int):
        """Enable auto-grab for a specific chat"""
        self.enabled_chats.add(chat_id)
    
    def disable_chat(self, chat_id: int):
        """Disable auto-grab for a specific chat"""
        self.enabled_chats.discard(chat_id)
    
    def enable_all(self):
        """Enable auto-grab globally"""
        self.global_enabled = True
        self.enabled_chats.clear()  # Clear individual chat settings
    
    def disable_all(self):
        """Disable auto-grab globally and for all chats"""
        self.global_enabled = False
        self.enabled_chats.clear()
    
    def get_uptime(self) -> str:
        """Get bot uptime as a formatted string"""
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# Initialize state
state = AutoGrabState()

def setup_logging():
    """Setup logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('autograb.log'),
            logging.StreamHandler()
        ]
    )

async def search_character(photo_id: str, photo_access_hash: str) -> str:
    """Search for character name in database"""
    stable_id = f"{photo_id}_{photo_access_hash}"
    return state.db.get(stable_id, None)

async def main():
    setup_logging()
    
    # Start keep_alive server if available
    if KEEP_ALIVE_AVAILABLE:
        try:
            print("🌐 Starting keep_alive server...")
            keep_alive()
        except Exception as e:
            print(f"⚠️ Failed to start keep_alive server: {e}")
    
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    
    me = await client.get_me()
    print(f"✅ Auto-Grab Bot started as {me.username or me.first_name}")
    
    # Load character database
    state.load_db()
    
    @client.on(events.NewMessage(pattern=r'^/grab\s+(on|off|onall|offall)$'))
    async def handle_grab_command(event):
        """Handle /grab on/off/onall/offall commands"""
        command = event.pattern_match.group(1).lower()
        chat_id = event.chat_id
        
        try:
            if command == "on":
                state.enable_chat(chat_id)
                await event.reply("✅ **Auto-grab ENABLED** for this chat!")
                
            elif command == "off":
                state.disable_chat(chat_id)
                await event.reply("❌ **Auto-grab DISABLED** for this chat!")
                
            elif command == "onall":
                state.enable_all()
                await event.reply("🌍 **Auto-grab ENABLED GLOBALLY** for all chats!")
                
            elif command == "offall":
                state.disable_all()
                await event.reply("🚫 **Auto-grab DISABLED** for all chats!")
                
        except Exception as e:
            logging.error(f"Error in grab command: {e}")
            await event.reply("❌ Error processing command!")
    
    @client.on(events.NewMessage(pattern=r'^/status$'))
    async def handle_status_command(event):
        """Handle /status command"""
        try:
            chat_id = event.chat_id
            is_enabled = state.is_enabled(chat_id)
            
            status_msg = f"""
📊 **Auto-Grab Status**

🔄 **Current Chat:** {'✅ ON' if is_enabled else '❌ OFF'}
🌍 **Global Mode:** {'✅ ON' if state.global_enabled else '❌ OFF'}
📋 **Individual Chats:** {len(state.enabled_chats)} enabled
⏱️ **Uptime:** {state.get_uptime()}
📚 **Database:** {len(state.db)} characters loaded
🤖 **Bot:** {BOT_USERNAME}
            """.strip()
            
            await event.reply(status_msg)
            
        except Exception as e:
            logging.error(f"Error in status command: {e}")
            await event.reply("❌ Error getting status!")
    
    @client.on(events.NewMessage)
    async def handle_auto_grab(event):
        """Main auto-grab logic"""
        try:
            # Skip if not enabled for this chat
            if not state.is_enabled(event.chat_id):
                return
            
            # Skip if not from waifu bot
            if not event.sender or event.sender.username != BOT_USERNAME.lstrip('@'):
                return
            
            # Skip if no photo
            if not isinstance(event.media, MessageMediaPhoto):
                return
            
            # Skip if message doesn't contain /grab keyword
            if not event.message or '/grab' not in event.message.lower():
                return
            
            # Extract photo info
            photo = event.media.photo
            photo_id = str(photo.id)
            photo_access_hash = str(photo.access_hash)
            
            # Search in database
            character_name = await search_character(photo_id, photo_access_hash)
            
            if character_name:
                # Found in database - send grab command
                grab_msg = f"/grab {character_name}"
                await event.reply(grab_msg)
                logging.info(f"✅ Auto-grabbed: {character_name} in chat {event.chat_id}")
            else:
                # Not found - send dots
                await event.reply("..")
                logging.info(f"❓ Character not found in DB for chat {event.chat_id}")
                
        except Exception as e:
            logging.error(f"Error in auto-grab: {e}")
    
    print("🚀 Auto-Grab Bot is running...")
    print("Commands:")
    print("  /grab on     - Enable for current chat")
    print("  /grab off    - Disable for current chat") 
    print("  /grab onall  - Enable for all chats")
    print("  /grab offall - Disable for all chats")
    print("  /status      - Show status info")
    print("\nPress Ctrl+C to stop")
    
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\n👋 Auto-Grab Bot stopped!")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
