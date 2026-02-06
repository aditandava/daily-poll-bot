import asyncio
import os
import random
import requests
import datetime
import json
import logging
import tempfile
import shutil
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageActionPinMessage
from telethon.tl.functions.messages import GetPollVotesRequest
from telegram import Bot, constants
from telegram.error import RetryAfter, BadRequest, TimedOut

# --- CONFIGURATION & SETUP ---
# Configure logging for professional debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load Environment Variables (Fail Fast if missing)
try:
    API_ID = int(os.environ["APP_ID"])
    API_HASH = os.environ["APP_HASH"]
    SESSION_STRING = os.environ["SESSION_KEY"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    GROUP_ID = int(os.environ["GROUP_ID"])
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
except KeyError as e:
    logger.critical(f"❌ Missing Environment Variable: {e}")
    exit(1)

# File Paths
DB_FILE = "quotes_db.txt"
STREAK_FILE = "streak_data.json"
LAST_POLL_FILE = "last_poll_id.txt"

# --- CONTENT ASSETS ---
BACKUP_QUOTES = [
    "Discipline is choosing between what you want now and what you want most.",
    "The pain of study is temporary; the pain of regret is forever.",
    "Don't stop when you're tired. Stop when you're done.",
    "Your future self is watching you right now through memories.",
    "Do something today that your future self will thank you for."
]

POLL_TEMPLATES = [
    {"q": "How many study hours did you hit today? ⏳", "a": ["0h (Rest day) 😴", "1-3h (Good start) 💡", "3-6h (Solid work) 🔨", "6-8h (Impressive) 🔥", "8-10h (Beast mode) ⚡", "10-12h (Legend) 🚀", "12h+ (Unstoppable) 👑"]},
    {"q": "Deep Work hours today? 🧠", "a": ["0h (Recharge) 📵", "1-3h (Building habit) 🌱", "3-6h (Locked in) 🔒", "6-8h (Flow state) 🌊", "8-10h (Academic weapon) ⚔️", "10-12h (Genius level) 💎", "12h+ (Superhuman) 🏆"]},
    {"q": "Total focused study time? ⏱️", "a": ["0h (Off day) 💀", "1-3h (Progress made) 🕐", "3-6h (Consistent) 🕒", "6-8h (Dedicated) 🕓", "8-10h (Committed) 🕔", "10-12h (Elite focus) 🕕", "12h+ (God tier) 🕛"]},
    {"q": "Productive study hours today? 🤥", "a": ["0h (Honest rest) 😅", "1-3h (Small wins) 👍", "3-6h (Strong effort) 💪", "6-8h (Fire output) 🔥", "8-10h (Crushing it) ⚡", "10-12h (Champion) 🎯", "12h+ (Absolute legend) 💯"]},
    {"q": "Actual study time (be honest)? 📊", "a": ["0h (Recovery) 🤡", "1-3h (Starting strong) 🐌", "3-6h (Solid grind) 🆗", "6-8h (Intense work) 😤", "8-10h (Peak performance) 🥵", "10-12h (Unmatched) 🦾", "12h+ (Next level) 🧠"]},
    {"q": "Study hours grinded today? 📝", "a": ["0h (Break day) 🏖️", "1-3h (Good effort) 📖", "3-6h (Making moves) ✍️", "6-8h (Serious grind) 🔄", "8-10h (Dominating) 🧹", "10-12h (Scholar mode) 📚", "12h+ (Certified genius) 🎓"]},
    {"q": "How long did you study? ⏳", "a": ["0h (Chill day) 💤", "1-3h (Early bird) 🌅", "3-6h (Day warrior) ☀️", "6-8h (Evening grinder) 🌆", "8-10h (Night owl) 🌃", "10-12h (Full cycle) 🌌", "12h+ (Time bender) ✨"]},
    {"q": "Study session duration today? ⌚", "a": ["0h (Resting) 🛌", "1-3h (Walking forward) 🚶", "3-6h (Running hard) 🏃", "6-8h (Cycling through) 🚴", "8-10h (Lifting heavy) 🏋️", "10-12h (Superhero) 🦸", "12h+ (Titan status) 🔱"]},
    {"q": "Time spent studying? 📖", "a": ["0h (Pause) 😶", "1-3h (Writing history) 📝", "3-6h (Page turner) 📕", "6-8h (Book master) 📗", "8-10h (Knowledge seeker) 📘", "10-12h (Wisdom holder) 📙", "12h+ (Library itself) 📚"]},
    {"q": "Today's study grind hours? 💪", "a": ["0h (Smile break) 🫠", "1-3h (Happy start) 🙂", "3-6h (Cheerful grind) 😊", "6-8h (Grinning wide) 😁", "8-10h (Star struck) 🤩", "10-12h (Cool cat) 😎", "12h+ (Gold medalist) 🥇"]},
    {"q": "Hours of focused work? 🎯", "a": ["0h (Float day) 🎈", "1-3h (Big tent) 🎪", "3-6h (Artist) 🎨", "6-8h (Performer) 🎭", "8-10h (Director) 🎬", "10-12h (Bullseye) 🎯", "12h+ (Trophy hunter) 🏅"]},
    {"q": "Study time tracker? ⏲️", "a": ["0h (Stop) 🟥", "1-3h (Warming up) 🟧", "3-6h (Caution ready) 🟨", "6-8h (Go green) 🟩", "8-10h (Blue sky) 🟦", "10-12h (Purple reign) 🟪", "12h+ (All colors) 🟫"]},
    {"q": "How much did you grind? 🔥", "a": ["0h (Ice cool) 🧊", "1-3h (Temperature rising) 🌡️", "3-6h (Temperature rising) 🌡️", "6-8h (Spicy hot) 🌶️", "8-10h (On fire) 🔥", "10-12h (Volcano) 🌋", "12h+ (Literal sun) ☀️"]},
    {"q": "Study hours completed? ✅", "a": ["0h (Marked off) ❌", "1-3h (Started) ⬜", "3-6h (Yellow flag) 🟨", "6-8h (Orange zone) 🟧", "8-10h (Green light) 🟩", "10-12h (Blue ribbon) 🟦", "12h+ (Purple heart) 🟪"]},
    {"q": "Grind time today? ⚡", "a": ["0h (Battery rest) 🪫", "1-3h (Charging up) 🔋", "3-6h (Plugged in) 🔌", "6-8h (Electric) ⚡", "8-10h (Lightning) 🌩️", "10-12h (Thunderstorm) ⛈️", "12h+ (Tornado force) 🌪️"]},
    {"q": "How many hours studied? 📚", "a": ["0h (Chill mode) 🌴", "1-3h (Baby steps) 👶", "3-6h (Growing strong) 🌿", "6-8h (Blooming) 🌸", "8-10h (Full bloom) 🌺", "10-12h (Garden master) 🌻", "12h+ (Forest legend) 🌳"]},
    {"q": "Study duration check? 🎓", "a": ["0h (No cap) 🧢", "1-3h (Rookie gains) 🏃‍♂️", "3-6h (Pro moves) 🏋️‍♂️", "6-8h (Expert level) 🥷", "8-10h (Master class) 🧙", "10-12h (Sensei status) 🥋", "12h+ (Final boss) 👹"]},
    {"q": "Total grind hours? 💎", "a": ["0h (Stone) 🪨", "1-3h (Bronze) 🥉", "3-6h (Silver) 🥈", "6-8h (Gold) 🥇", "8-10h (Platinum) 💿", "10-12h (Diamond) 💎", "12h+ (Unranked legend) 👑"]}
]

# --- 🛡️ ROBUST DATA HANDLING ---
def load_data(filepath, default_value):
    """Loads JSON data safely. Returns default_value on failure."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ Error loading {filepath}: {e}")
            return default_value
    return default_value

def save_data(filepath, data):
    """Atomic save: writes to temp file first, then renames. Prevents corruption."""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp)
            tmp_name = tmp.name
        shutil.move(tmp_name, filepath)
    except Exception as e:
        logger.error(f"❌ Failed to save {filepath}: {e}")

def get_last_poll_id():
    if os.path.exists(LAST_POLL_FILE):
        try:
            with open(LAST_POLL_FILE, "r") as f:
                return int(f.read().strip())
        except: return None
    return None

def save_last_poll_id(msg_id):
    with open(LAST_POLL_FILE, "w") as f:
        f.write(str(msg_id))

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except: return []
    return []

def save_db(quote):
    quotes = load_db()
    quotes.append(quote)
    if len(quotes) > 20: # Increased history slightly
        quotes = quotes[-20:] 
    with open(DB_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))

# --- RANK SYSTEM ---
def get_rank_info(days):
    if days >= 50: return "👹 DEMON", None, 0
    if days >= 25: return "👑 WARLORD", "👹 DEMON", 50 - days
    if days >= 15: return "🎖️ Commander", "👑 WARLORD", 25 - days
    if days >= 8:  return "🛡️ Veteran", "🎖️ Commander", 15 - days
    if days >= 4:  return "⚔️ Soldier", "🛡️ Veteran", 8 - days
    return "🌱 Initiate", "⚔️ Soldier", 4 - days

# --- CORE LOGIC ---
async def process_streaks(client, bot, last_poll_id):
    logger.info(f"🔍 Processing Poll ID: {last_poll_id}")
    
    # 1. STOP POLL (Bot API)
    try:
        await bot.stop_poll(chat_id=GROUP_ID, message_id=last_poll_id)
        logger.info("🛑 Poll closed. Results visible.")
        await asyncio.sleep(2) 
    except BadRequest as e:
        if "Poll has already been closed" in str(e):
            logger.info("ℹ️ Poll was already closed.")
        else:
            logger.warning(f"⚠️ Poll stop warning: {e}")
    except Exception as e:
        logger.error(f"❌ Critical error stopping poll: {e}")

    # 2. READ VOTES (Telethon User Client)
    winning_options = [b'5', b'6'] 
    successful_user_ids = set()

    try:
        for option in winning_options:
            offset = ''
            while True:
                results = await client(GetPollVotesRequest(
                    peer=GROUP_ID, id=last_poll_id, option=option, offset=offset, limit=50
                ))
                if not results.users: break
                for user in results.users: successful_user_ids.add(str(user.id))
                offset = results.next_offset
                if not offset: break    
    except Exception as e:
        logger.error(f"⚠️ Could not fetch votes: {e}")
        return None

    # 3. UPDATE STREAKS
    old_streaks = load_data(STREAK_FILE, {})
    new_streaks = {}

    for uid in successful_user_ids:
        current_streak = old_streaks.get(uid, 0)
        new_streaks[uid] = current_streak + 1

    save_data(STREAK_FILE, new_streaks)
    
    if not new_streaks:
        return "📉 **No one hit 10h+ yesterday.**\n\nStreaks have been reset to zero.\nToday is a new beginning. 💀"

    # 4. GENERATE LEADERBOARD VISUALS
    sorted_streaks = sorted(new_streaks.items(), key=lambda x: x[1], reverse=True)
    
    msg = "🏆 <b>10H+ WARRIOR LEADERBOARD</b> 🏆\n"
    msg += "<i>Consistency is the only currency.</i>\n\n"
    
    max_streak = sorted_streaks[0][1]
    
    for i, (uid, streak) in enumerate(sorted_streaks):
        if i >= 15: break 
        
        try:
            # Attempt to fetch user details. Fail gracefully if user is privacy-restricted.
            try:
                user_entity = await client.get_entity(int(uid))
                name = user_entity.first_name if user_entity.first_name else "Unknown"
                name = name.replace("<", "&lt;").replace(">", "&gt;") 
            except:
                name = "Hidden Warrior"

            rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            title, next_title, days_left = get_rank_info(streak)
            
            # Dynamic Bar Generation
            filled_len = int((streak / max_streak) * 10)
            filled_len = max(1, filled_len) 
            bar = "▰" * filled_len + "▱" * (10 - filled_len)
            
            progress_text = f"<i>Next: {next_title} in {days_left}d</i>" if next_title else "<i>Max Rank Achieved</i>"
            msg += f"<b>{rank_emoji} {name}</b> [{title}]\n<code>{bar}</code> {streak} Days\n{progress_text}\n\n"
        except Exception:
            continue
            
    msg += "👇 <i>Vote 10h+ below to join the ranks.</i>"
    return msg

def get_unique_motivation():
    existing_quotes = load_db()
    
    # Try AI Generation 3 times
    for attempt in range(3):
        logger.info(f"🧠 AI Generation Attempt {attempt+1}...")
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            prompt = "Write exactly ONE savage, short, high-intensity study motivation . Max 15 words. No hashtags. No quotes. Output ONLY the text. you can use hindi too ."
            payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 1.1}
            
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                quote = response.json()['choices'][0]['message']['content'].strip()
                # Clean up formatting artifacts
                quote = quote.replace('"', '').replace("Here's a quote:", "").strip()
                if '\n' in quote: quote = quote.split('\n')[0]
                
                if quote not in existing_quotes:
                    return quote
        except Exception as e:
            logger.warning(f"AI Gen Failed: {e}")
            continue
    
    # Fallback Logic
    available_backups = [q for q in BACKUP_QUOTES if q not in existing_quotes]
    return random.choice(available_backups) if available_backups else random.choice(BACKUP_QUOTES)

# --- MAIN ENGINE ---
async def main():
    logger.info("🚀 Booting StudyBot v3.0 [Enhanced]")
    
    # Initialize Bot API
    bot = Bot(token=BOT_TOKEN) 
    
    # Prepare Motivation
    final_quote = get_unique_motivation()
    save_db(final_quote)

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        
        # --- STEP 1: SYSTEM STATUS (Bot) ---
        try:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            display_text = f"🟢 <b>SYSTEM ONLINE</b>\n📅 {date_str} | ⚙️ v2.0"
            status_msg = await bot.send_message(
                chat_id=GROUP_ID, text=display_text, parse_mode=constants.ParseMode.HTML
            )
            await asyncio.sleep(5)
            await status_msg.delete()
        except Exception as e: logger.error(f"Startup Msg Error: {e}")

        # --- STEP 2: LEADERBOARD & CLOSE OLD POLL ---
        last_poll_id = get_last_poll_id()
        if last_poll_id:
            streak_msg = await process_streaks(client, bot, last_poll_id)
            if streak_msg:
                try:
                    await bot.send_message(GROUP_ID, streak_msg, parse_mode=constants.ParseMode.HTML)
                    logger.info("✅ Leaderboard Delivered.")
                except Exception as e: logger.error(f"Leaderboard Send Error: {e}")
        
        await asyncio.sleep(3)

        # --- STEP 3: NEW POLL (Bot) ---
        template = random.choice(POLL_TEMPLATES)
        try:
            logger.info("📤 sending new poll...")
            poll_msg = await bot.send_poll(
                chat_id=GROUP_ID,
                question=template['q'],
                options=template['a'],
                is_anonymous=False, # MANDATORY for tracking
                allows_multiple_answers=False
            )
            save_last_poll_id(poll_msg.message_id) 
            logger.info("✅ Poll Sent.")
            
            # Pinning Logic
            try: 
                await bot.pin_chat_message(chat_id=GROUP_ID, message_id=poll_msg.message_id)
                await asyncio.sleep(1) # Wait for service message to arrive
                
                # Clean up "Pinned Message" notification
                history = await client.get_messages(GROUP_ID, limit=3)
                for msg in history:
                    if isinstance(msg.action, MessageActionPinMessage):
                        await msg.delete()
                        break
            except Exception as e: logger.warning(f"Pinning/Cleanup Warning: {e}")

        except Exception as e: 
            logger.critical(f"❌ FAILED TO SEND POLL: {e}")
            return # Exit if poll fails, critical error

        await asyncio.sleep(5)

        # --- STEP 4: TAGGING MEMBERS (Bot) ---
        # Robust user fetching
        try:
            users = await client.get_participants(GROUP_ID, aggressive=True)
            
            # --- FILTER: EXCLUDE LOTUS_DARK ---
            members = [
                u for u in users 
                if not u.bot 
                and not u.deleted 
                and (u.username is None or u.username.lower() != 'lotus_dark')
            ]

            if members:
                logger.info(f"🤖 Tagging {len(members)} members...")
                chunk_size = 5
                chunks = [members[i:i + chunk_size] for i in range(0, len(members), chunk_size)]
                
                for chunk in chunks:
                    mentions = []
                    for u in chunk:
                        if u.username:
                            mentions.append(f"@{u.username}")
                        else:
                            # Sanitize name for HTML
                            clean_name = u.first_name.replace("<", "&lt;").replace(">", "&gt;")
                            mentions.append(f"<a href='tg://user?id={u.id}'>{clean_name}</a>")
                    
                    text_body = " ".join(mentions)
                    
                    try:
                        await bot.send_message(GROUP_ID, text_body, parse_mode=constants.ParseMode.HTML)
                        await asyncio.sleep(2.5) # Prevent FloodWait
                    except RetryAfter as e:
                        logger.warning(f"⏳ FloodWait detected. Sleeping {e.retry_after}s...")
                        await asyncio.sleep(e.retry_after + 2)
                    except Exception as e:
                        logger.error(f"Tagging Error: {e}")
                        await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Participant Fetch Error: {e}")

        # --- STEP 5: MOTIVATION (Bot) ---
        try:
            await bot.send_message(
                GROUP_ID, 
                f"💀 <b>{final_quote}</b>\n\n👇 <i>Vote 10h+ or Reset. Your Choice.</i>", 
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e: logger.error(f"Quote Send Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
