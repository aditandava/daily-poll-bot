import asyncio
import os
import random
import requests
import datetime
import json
import logging
import tempfile
import shutil
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageActionPinMessage
from telethon.tl.functions.messages import GetPollVotesRequest
from telegram import Bot, constants
from telegram.error import RetryAfter, BadRequest

# =============================================================
# LOGGING
# =============================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================
# 🎛️ FEATURE TOGGLES
# Set these in GitHub → Settings → Variables → Actions
# ---------------------------------------------------------
# FEATURE_POLL         ON/OFF  Send daily poll
# FEATURE_LEADERBOARD  ON/OFF  Show streak leaderboard
# FEATURE_TAGGING      ON/OFF  Tag all members
# FEATURE_MOTIVATION   ON/OFF  Send motivation quote
# FEATURE_PIN_POLL     ON/OFF  Pin the poll after sending
# FEATURE_STATUS_MSG   ON/OFF  Show system online message
# TAGGING_CHUNK_SIZE   number  Members per tag message (default 5)
# LEADERBOARD_TOP_N    number  Top N shown on leaderboard (default 15)
# =============================================================
def is_on(var_name, default="ON"):
    val = os.environ.get(var_name, default)
    if not val or val.strip() == "":
        return default.upper() == "ON"
    return val.strip().upper() == "ON"

FEATURE_POLL         = is_on("FEATURE_POLL")
FEATURE_LEADERBOARD  = is_on("FEATURE_LEADERBOARD")
FEATURE_TAGGING      = is_on("FEATURE_TAGGING")
FEATURE_MOTIVATION   = is_on("FEATURE_MOTIVATION")
FEATURE_PIN_POLL     = is_on("FEATURE_PIN_POLL")
FEATURE_STATUS_MSG   = is_on("FEATURE_STATUS_MSG")

TAGGING_CHUNK_SIZE   = int(os.environ.get("TAGGING_CHUNK_SIZE", "5") or "5")
LEADERBOARD_TOP_N    = int(os.environ.get("LEADERBOARD_TOP_N", "15") or "15")

logger.info(
    "\n╔══════════════════════════════════════╗"
    "\n║         FEATURE TOGGLE STATUS        ║"
    "\n╠══════════════════════════════════════╣"
    f"\n║  POLL          : {'✅ ON' if FEATURE_POLL else '❌ OFF'}                   ║"
    f"\n║  LEADERBOARD   : {'✅ ON' if FEATURE_LEADERBOARD else '❌ OFF'}                   ║"
    f"\n║  TAGGING       : {'✅ ON' if FEATURE_TAGGING else '❌ OFF'}                   ║"
    f"\n║  MOTIVATION    : {'✅ ON' if FEATURE_MOTIVATION else '❌ OFF'}                   ║"
    f"\n║  PIN POLL      : {'✅ ON' if FEATURE_PIN_POLL else '❌ OFF'}                   ║"
    f"\n║  STATUS MSG    : {'✅ ON' if FEATURE_STATUS_MSG else '❌ OFF'}                   ║"
    f"\n║  TAG CHUNK     : {TAGGING_CHUNK_SIZE}                             ║"
    f"\n║  LEADERBOARD N : {LEADERBOARD_TOP_N}                            ║"
    "\n╚══════════════════════════════════════╝"
)

# =============================================================
# SECRETS / ENV VARS
# =============================================================
try:
    API_ID         = int(os.environ["APP_ID"])
    API_HASH       = os.environ["APP_HASH"]
    SESSION_STRING = os.environ["SESSION_KEY"]
    BOT_TOKEN      = os.environ["BOT_TOKEN"]
    GROUP_ID       = int(os.environ["GROUP_ID"])
    GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
except KeyError as e:
    logger.critical(f"❌ Missing Environment Variable: {e}")
    exit(1)

# =============================================================
# FILE PATHS
# =============================================================
DB_FILE        = "quotes_db.txt"
STREAK_FILE    = "streak_data.json"
LAST_POLL_FILE = "last_poll_id.txt"

# =============================================================
# CONTENT ASSETS
# =============================================================
BACKUP_QUOTES = [
    "Discipline is choosing between what you want now and what you want most.",
    "The pain of study is temporary; the pain of regret is forever.",
    "Don't stop when you're tired. Stop when you're done.",
    "Your future self is watching you right now through memories.",
    "Do something today that your future self will thank you for."
]

POLL_TEMPLATES = [
    {"q": "How many study hours did you hit today? ⏳",    "a": ["0h (Rest day) 😴",     "1-3h (Good start) 💡",     "3-6h (Solid work) 🔨",    "6-8h (Impressive) 🔥",        "8-10h (Beast mode) ⚡",     "10-12h (Legend) 🚀",       "12h+ (Unstoppable) 👑"]},
    {"q": "Deep Work hours today? 🧠",                     "a": ["0h (Recharge) 📵",     "1-3h (Building habit) 🌱", "3-6h (Locked in) 🔒",     "6-8h (Flow state) 🌊",        "8-10h (Academic weapon) ⚔️","10-12h (Genius level) 💎",  "12h+ (Superhuman) 🏆"]},
    {"q": "Total focused study time? ⏱️",                  "a": ["0h (Off day) 💀",      "1-3h (Progress made) 🕐",  "3-6h (Consistent) 🕒",    "6-8h (Dedicated) 🕓",         "8-10h (Committed) 🕔",      "10-12h (Elite focus) 🕕",  "12h+ (God tier) 🕛"]},
    {"q": "Productive study hours today? 🤥",              "a": ["0h (Honest rest) 😅",  "1-3h (Small wins) 👍",     "3-6h (Strong effort) 💪",  "6-8h (Fire output) 🔥",       "8-10h (Crushing it) ⚡",    "10-12h (Champion) 🎯",      "12h+ (Absolute legend) 💯"]},
    {"q": "Actual study time (be honest)? 📊",             "a": ["0h (Recovery) 🤡",     "1-3h (Starting strong) 🐌","3-6h (Solid grind) 🆗",    "6-8h (Intense work) 😤",      "8-10h (Peak performance) 🥵","10-12h (Unmatched) 🦾",    "12h+ (Next level) 🧠"]},
    {"q": "Study hours grinded today? 📝",                 "a": ["0h (Break day) 🏖️",   "1-3h (Good effort) 📖",    "3-6h (Making moves) ✍️",   "6-8h (Serious grind) 🔄",     "8-10h (Dominating) 🧹",     "10-12h (Scholar mode) 📚",  "12h+ (Certified genius) 🎓"]},
    {"q": "How long did you study? ⏳",                    "a": ["0h (Chill day) 💤",    "1-3h (Early bird) 🌅",     "3-6h (Day warrior) ☀️",    "6-8h (Evening grinder) 🌆",   "8-10h (Night owl) 🌃",      "10-12h (Full cycle) 🌌",   "12h+ (Time bender) ✨"]},
    {"q": "Study session duration today? ⌚",              "a": ["0h (Resting) 🛌",      "1-3h (Walking forward) 🚶","3-6h (Running hard) 🏃",   "6-8h (Cycling through) 🚴",   "8-10h (Lifting heavy) 🏋️", "10-12h (Superhero) 🦸",    "12h+ (Titan status) 🔱"]},
    {"q": "Time spent studying? 📖",                       "a": ["0h (Pause) 😶",        "1-3h (Writing history) 📝","3-6h (Page turner) 📕",    "6-8h (Book master) 📗",        "8-10h (Knowledge seeker) 📘","10-12h (Wisdom holder) 📙","12h+ (Library itself) 📚"]},
    {"q": "Today's study grind hours? 💪",                 "a": ["0h (Smile break) 🫠",  "1-3h (Happy start) 🙂",    "3-6h (Cheerful grind) 😊", "6-8h (Grinning wide) 😁",     "8-10h (Star struck) 🤩",    "10-12h (Cool cat) 😎",     "12h+ (Gold medalist) 🥇"]},
    {"q": "Hours of focused work? 🎯",                     "a": ["0h (Float day) 🎈",    "1-3h (Big tent) 🎪",       "3-6h (Artist) 🎨",         "6-8h (Performer) 🎭",          "8-10h (Director) 🎬",       "10-12h (Bullseye) 🎯",     "12h+ (Trophy hunter) 🏅"]},
    {"q": "Study time tracker? ⏲️",                        "a": ["0h (Stop) 🟥",         "1-3h (Warming up) 🟧",     "3-6h (Caution ready) 🟨",  "6-8h (Go green) 🟩",           "8-10h (Blue sky) 🟦",       "10-12h (Purple reign) 🟪", "12h+ (All colors) 🟫"]},
    {"q": "How much did you grind? 🔥",                    "a": ["0h (Ice cool) 🧊",     "1-3h (Temp rising) 🌡️",   "3-6h (Heating up) 🌡️",    "6-8h (Spicy hot) 🌶️",         "8-10h (On fire) 🔥",        "10-12h (Volcano) 🌋",      "12h+ (Literal sun) ☀️"]},
    {"q": "Study hours completed? ✅",                     "a": ["0h (Marked off) ❌",   "1-3h (Started) ⬜",         "3-6h (Yellow flag) 🟨",    "6-8h (Orange zone) 🟧",        "8-10h (Green light) 🟩",    "10-12h (Blue ribbon) 🟦",  "12h+ (Purple heart) 🟪"]},
    {"q": "Grind time today? ⚡",                          "a": ["0h (Battery rest) 🪫", "1-3h (Charging up) 🔋",    "3-6h (Plugged in) 🔌",     "6-8h (Electric) ⚡",            "8-10h (Lightning) 🌩️",     "10-12h (Thunderstorm) ⛈️","12h+ (Tornado force) 🌪️"]},
    {"q": "How many hours studied? 📚",                    "a": ["0h (Chill mode) 🌴",   "1-3h (Baby steps) 👶",     "3-6h (Growing strong) 🌿", "6-8h (Blooming) 🌸",           "8-10h (Full bloom) 🌺",     "10-12h (Garden master) 🌻","12h+ (Forest legend) 🌳"]},
    {"q": "Study duration check? 🎓",                      "a": ["0h (No cap) 🧢",       "1-3h (Rookie gains) 🏃‍♂️","3-6h (Pro moves) 🏋️‍♂️",  "6-8h (Expert level) 🥷",       "8-10h (Master class) 🧙",   "10-12h (Sensei status) 🥋","12h+ (Final boss) 👹"]},
    {"q": "Total grind hours? 💎",                         "a": ["0h (Stone) 🪨",        "1-3h (Bronze) 🥉",         "3-6h (Silver) 🥈",         "6-8h (Gold) 🥇",               "8-10h (Platinum) 💿",       "10-12h (Diamond) 💎",      "12h+ (Unranked legend) 👑"]}
]

# =============================================================
# DATA HELPERS
# =============================================================
def load_data(filepath, default_value):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ Error loading {filepath}: {e}")
    return default_value

def save_data(filepath, data):
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
        except:
            return None
    return None

def save_last_poll_id(msg_id):
    with open(LAST_POLL_FILE, "w") as f:
        f.write(str(msg_id))

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except:
            return []
    return []

def save_db(quote):
    quotes = load_db()
    quotes.append(quote)
    if len(quotes) > 20:
        quotes = quotes[-20:]
    with open(DB_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))

# =============================================================
# RANK SYSTEM
# =============================================================
def get_rank_info(days):
    if days >= 50: return "👹 DEMON",      None,            0
    if days >= 25: return "👑 WARLORD",    "👹 DEMON",      50 - days
    if days >= 15: return "🎖️ Commander", "👑 WARLORD",    25 - days
    if days >= 8:  return "🛡️ Veteran",   "🎖️ Commander",  15 - days
    if days >= 4:  return "⚔️ Soldier",   "🛡️ Veteran",    8  - days
    return             "🌱 Initiate",     "⚔️ Soldier",    4  - days

# =============================================================
# CLOSE OLD POLL
# Always called when a previous poll ID exists.
# Ensures no poll stays open when a new one is being sent.
# This runs regardless of FEATURE_LEADERBOARD setting.
# =============================================================
async def close_old_poll(bot, last_poll_id):
    try:
        await bot.stop_poll(chat_id=GROUP_ID, message_id=last_poll_id)
        logger.info("🛑 Previous poll closed.")
        await asyncio.sleep(2)
    except BadRequest as e:
        if "Poll has already been closed" in str(e):
            logger.info("ℹ️ Poll was already closed.")
        else:
            logger.warning(f"⚠️ Poll stop warning: {e}")
    except Exception as e:
        logger.error(f"❌ Error closing poll: {e}")

# =============================================================
# LEADERBOARD — reads votes, updates streaks, returns message
# =============================================================
async def process_streaks(client, last_poll_id):
    logger.info(f"🔍 Reading votes for Poll ID: {last_poll_id}")

    # Options index 5 = 10-12h, index 6 = 12h+
    winning_options = [b'5', b'6']
    successful_user_ids = set()

    try:
        for option in winning_options:
            offset = b''
            while True:
                results = await client(GetPollVotesRequest(
                    peer=GROUP_ID, id=last_poll_id,
                    option=option, offset=offset, limit=50
                ))
                if not results.users:
                    break
                for user in results.users:
                    successful_user_ids.add(str(user.id))
                offset = results.next_offset
                if not offset:
                    break
    except Exception as e:
        logger.error(f"⚠️ Could not fetch votes: {e}")
        return None

    # Update streaks
    old_streaks = load_data(STREAK_FILE, {})
    new_streaks = {}
    for uid in successful_user_ids:
        new_streaks[uid] = old_streaks.get(uid, 0) + 1
    save_data(STREAK_FILE, new_streaks)

    if not new_streaks:
        return (
            "📉 <b>No one hit 10h+ yesterday.</b>\n\n"
            "Streaks have been reset to zero.\n"
            "Today is a new beginning. 💀"
        )

    # Build leaderboard
    sorted_streaks = sorted(new_streaks.items(), key=lambda x: x[1], reverse=True)
    max_streak = sorted_streaks[0][1]

    msg = "🏆 <b>10H+ WARRIOR LEADERBOARD</b> 🏆\n"
    msg += "<i>Consistency is the only currency.</i>\n\n"

    for i, (uid, streak) in enumerate(sorted_streaks):
        if i >= LEADERBOARD_TOP_N:
            break
        try:
            try:
                user_entity = await client.get_entity(int(uid))
                name = (user_entity.first_name or "Unknown").replace("<", "&lt;").replace(">", "&gt;")
            except:
                name = "Hidden Warrior"

            rank_emoji   = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            title, next_title, days_left = get_rank_info(streak)
            filled       = max(1, int((streak / max_streak) * 10))
            bar          = "▰" * filled + "▱" * (10 - filled)
            progress     = f"<i>Next: {next_title} in {days_left}d</i>" if next_title else "<i>Max Rank Achieved</i>"

            msg += f"<b>{rank_emoji} {name}</b> [{title}]\n<code>{bar}</code> {streak} Days\n{progress}\n\n"
        except Exception:
            continue

    msg += "👇 <i>Vote 10h+ below to keep your streak alive.</i>"
    return msg

# =============================================================
# MOTIVATION QUOTE
# =============================================================
def get_unique_motivation():
    existing_quotes = load_db()
    for attempt in range(3):
        logger.info(f"🧠 AI Quote Attempt {attempt + 1}...")
        try:
            url     = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            prompt  = (
                "Generate exactly ONE brutal, punchy motivation or tips line for study. "
                "Max 12 words. Raw energy, no fluff. Hinglish allowed. "
                "No hashtags, no quotes, no emojis. Output ONLY the line."
            )
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 1.1
            }
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                quote = response.json()['choices'][0]['message']['content'].strip()
                quote = quote.replace('"', '').replace("Here's a quote:", "").strip()
                if '\n' in quote:
                    quote = quote.split('\n')[0]
                if quote and quote not in existing_quotes:
                    return quote
        except Exception as e:
            logger.warning(f"AI Gen Failed (attempt {attempt+1}): {e}")

    available = [q for q in BACKUP_QUOTES if q not in existing_quotes]
    return random.choice(available) if available else random.choice(BACKUP_QUOTES)

# =============================================================
# MAIN
# =============================================================
async def main():
    logger.info("🚀 Booting StudyBot v4.0 [Feature Toggle Edition]")
    bot = Bot(token=BOT_TOKEN)

    # Pre-generate motivation before opening Telethon session
    final_quote = None
    if FEATURE_MOTIVATION:
        final_quote = get_unique_motivation()
        save_db(final_quote)
        logger.info(f"💬 Quote ready: {final_quote}")

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:

        # ── STEP 1: SYSTEM STATUS MESSAGE ────────────────────
        if FEATURE_STATUS_MSG:
            try:
                date_str   = datetime.datetime.now().strftime("%Y-%m-%d")
                status_msg = await bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"🟢 <b>SYSTEM ONLINE</b>\n📅 {date_str} | ⚙️ v4.0",
                    parse_mode=constants.ParseMode.HTML
                )
                await asyncio.sleep(5)
                await status_msg.delete()
                logger.info("✅ Status message sent and deleted.")
            except Exception as e:
                logger.error(f"Status Msg Error: {e}")
        else:
            logger.info("⏭️ SKIP: Status message (FEATURE_STATUS_MSG=OFF)")

        # ── STEP 2: CLOSE OLD POLL (always) + LEADERBOARD (toggle) ──
        last_poll_id = get_last_poll_id()

        if last_poll_id:
            # Always close old poll — prevents having two open polls
            await close_old_poll(bot, last_poll_id)

            # Show leaderboard only if feature is ON
            if FEATURE_LEADERBOARD:
                streak_msg = await process_streaks(client, last_poll_id)
                if streak_msg:
                    try:
                        await bot.send_message(
                            GROUP_ID,
                            streak_msg,
                            parse_mode=constants.ParseMode.HTML
                        )
                        logger.info("✅ Leaderboard delivered.")
                    except Exception as e:
                        logger.error(f"Leaderboard Send Error: {e}")
            else:
                logger.info("⏭️ SKIP: Leaderboard display (FEATURE_LEADERBOARD=OFF)")
        else:
            logger.info("ℹ️ No previous poll ID found — skipping close + leaderboard.")

        await asyncio.sleep(3)

        # ── STEP 3: SEND NEW POLL ─────────────────────────────
        if FEATURE_POLL:
            template = random.choice(POLL_TEMPLATES)
            try:
                logger.info("📤 Sending new poll...")
                poll_msg = await bot.send_poll(
                    chat_id=GROUP_ID,
                    question=template['q'],
                    options=template['a'],
                    is_anonymous=False,
                    allows_multiple_answers=False
                )
                save_last_poll_id(poll_msg.message_id)
                logger.info(f"✅ Poll sent (ID: {poll_msg.message_id})")

                # ── PIN POLL ──────────────────────────────────
                if FEATURE_PIN_POLL:
                    try:
                        await bot.pin_chat_message(
                        chat_id=GROUP_ID,
                        message_id=poll_msg.message_id,
                        disable_notification=False  
                        )
                        await asyncio.sleep(1)
                        # Clean up "pinned message" service notification
                        history = await client.get_messages(GROUP_ID, limit=3)
                        for msg in history:
                            if isinstance(msg.action, MessageActionPinMessage):
                                await msg.delete()
                                break
                        logger.info("✅ Poll pinned and notification cleaned.")
                    except Exception as e:
                        logger.warning(f"Pin Warning: {e}")
                else:
                    logger.info("⏭️ SKIP: Poll pinning (FEATURE_PIN_POLL=OFF)")

            except Exception as e:
                logger.critical(f"❌ FAILED TO SEND POLL: {e}")
        else:
            logger.info("⏭️ SKIP: Poll (FEATURE_POLL=OFF)")

        await asyncio.sleep(5)

        # ── STEP 4: TAG ALL MEMBERS ───────────────────────────
        if FEATURE_TAGGING:
            try:
                logger.info("👥 Fetching group participants...")
                users = await client.get_participants(GROUP_ID, aggressive=True)

                members = [
                    u for u in users
                    if not u.bot
                    and not u.deleted
                    and (u.username is None or u.username.lower() != 'lotus_dark')
                ]

                if not members:
                    logger.info("ℹ️ No members to tag.")
                else:
                    logger.info(f"🤖 Tagging {len(members)} members (chunk size: {TAGGING_CHUNK_SIZE})...")
                    chunks = [
                        members[i:i + TAGGING_CHUNK_SIZE]
                        for i in range(0, len(members), TAGGING_CHUNK_SIZE)
                    ]

                    for chunk in chunks:
                        mentions = []
                        for u in chunk:
                            if u.username:
                                mentions.append(f"@{u.username}")
                            else:
                                clean_name = (u.first_name or "User").replace("<", "&lt;").replace(">", "&gt;")
                                mentions.append(f"<a href='tg://user?id={u.id}'>{clean_name}</a>")
                        try:
                            await bot.send_message(
                                GROUP_ID,
                                " ".join(mentions),
                                parse_mode=constants.ParseMode.HTML
                            )
                            await asyncio.sleep(2.5)
                        except RetryAfter as e:
                            logger.warning(f"⏳ FloodWait — sleeping {e.retry_after}s...")
                            await asyncio.sleep(e.retry_after + 2)
                        except Exception as e:
                            logger.error(f"Tag chunk error: {e}")
                            await asyncio.sleep(2)

                    logger.info("✅ Tagging complete.")
            except Exception as e:
                logger.error(f"Participant Fetch Error: {e}")
        else:
            logger.info("⏭️ SKIP: Member tagging (FEATURE_TAGGING=OFF)")

        # ── STEP 5: MOTIVATION QUOTE ──────────────────────────
        if FEATURE_MOTIVATION and final_quote:
            try:
                await bot.send_message(
                    GROUP_ID,
                    f"💀 <b>{final_quote}</b>\n\n👇 <i>Vote 10h+ or Reset. Your Choice.</i>",
                    parse_mode=constants.ParseMode.HTML
                )
                logger.info("✅ Motivation quote sent.")
            except Exception as e:
                logger.error(f"Quote Send Error: {e}")
        else:
            logger.info("⏭️ SKIP: Motivation (FEATURE_MOTIVATION=OFF)")

    logger.info("✅ Bot cycle complete.")


if __name__ == "__main__":
    asyncio.run(main())

