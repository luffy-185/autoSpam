import asyncio
import time
import os
import logging
from typing import Dict
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for health checks (required for Render)
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

@app.route('/ping')
def ping():
    return "pong", 200


class TelegramBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_string = os.getenv('SESSION_STRING')
        self.owner_id = int(os.getenv('OWNER_ID'))

        self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)

        self.spam_tasks: Dict[int, asyncio.Task] = {}  # chat_id -> task
        self.bot_user_id = None
        self.start_time = time.time()

    def get_uptime(self):
        uptime_seconds = time.time() - self.start_time
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    async def start(self):
        await self.client.start()
        self.bot_user_id = (await self.client.get_me()).id
        logger.info(f"Bot started! ID: {self.bot_user_id}")

        self.client.add_event_handler(self.handle_message, events.NewMessage)
        await self.client.run_until_disconnected()

    async def handle_message(self, event):
        try:
            if event.message.text and event.message.text.startswith('/'):
                if event.sender_id == self.owner_id:
                    await self.handle_command(event)
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def handle_command(self, event):
        text = event.message.text.strip()
        chat_id = event.chat_id if hasattr(event, 'chat_id') else event.peer_id.user_id

        if text.startswith('/spam '):
            parts = text.split(' ', 2)
            if len(parts) < 3:
                await event.reply("Usage: /spam <message> <delay>")
                return
            try:
                msg = parts[1]
                delay = int(parts[2])
            except:
                await event.reply("❌ Invalid parameters")
                return
            await self.start_spam(chat_id, msg, delay)
            await event.reply(f"✅ Started spam in this chat every {delay}s")

        elif text == '/stop_spam':
            if chat_id in self.spam_tasks:
                self.spam_tasks[chat_id].cancel()
                del self.spam_tasks[chat_id]
                await event.reply("✅ Stopped spam in this chat")
            else:
                await event.reply("❌ No spam running in this chat")

        elif text == '/stop_all_spam':
            stopped = await self.stop_all_spam()
            await event.reply(f"✅ Stopped {stopped} spam tasks")

        elif text == '/status':
            uptime = self.get_uptime()
            spam_count = len(self.spam_tasks)
            await event.reply(
                f"⏱ Uptime: {uptime}\n"
                f"🤖 Bot ID: {self.bot_user_id}\n"
                f"🚀 Spam Tasks: {spam_count}"
            )

        elif text == '/help':
            help_text = """🤖 Bot Commands (Owner Only):

**Spam**
• /spam <msg> <delay> - spam in current chat
• /stop_spam - stop spam in current chat
• /stop_all_spam - stop all spam tasks

**Info**
• /status - show bot status
• /help - show this help
"""
            await event.reply(help_text)

    async def start_spam(self, chat_id: int, msg: str, delay: int):
        if chat_id in self.spam_tasks:
            self.spam_tasks[chat_id].cancel()
        async def spam_loop():
            try:
                while True:
                    await self.client.send_message(chat_id, msg)
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                pass
        task = asyncio.create_task(spam_loop())
        self.spam_tasks[chat_id] = task

    async def stop_all_spam(self):
        stopped = len(self.spam_tasks)
        for task in self.spam_tasks.values():
            task.cancel()
        self.spam_tasks.clear()
        return stopped


# Flask server in thread
def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    bot = TelegramBot()
    while True:
        try:
            await bot.start()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(main())
