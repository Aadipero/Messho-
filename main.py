import os
import io
import time
import asyncio
import sqlite3
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8824327960:AAEO_wyYbfuLRigvg78AZzOiaW0pmFg6_p4")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8423151783"))

# Proof Channel
PROOF_CHANNEL = "@provingc"
PROOF_CHANNEL_URL = "https://t.me/provingc"

# Setup / How To Order Guide Link
SETUP_GUIDE_URL = "https://t.me/meesho_setup/5"

# GitHub Pages Verification URL
VERIFY_WEBAPP_URL = "https://aadipero.github.io/device-verify/"

# Confetti / Party Popper Effect ID
MESSAGE_CONFETTI_EFFECT_ID = "5046509860389126442"

# ----------------- CACHE (SPEED OPTIMIZATION) -----------------
# Telegram API rate limits ko bypass karne ke liye member check cache
MEMBERSHIP_CACHE = {}  # { (user_id, chat_id): (is_member_bool, expire_timestamp) }
CACHE_TTL = 30  # 30 seconds cache

# ----------------- CUSTOM EMOJI IDS -----------------
CUSTOM_EMOJI_IDS = {
    "cute_gift": "5449816553727998023",
    "cute_star": "5089460564141278042",
    "ref_link": "5271604874419647061",
    "stats": "5231200819986047254",
    "claim": "5449816553727998023",
    "referrals": "5985525762973768278",
    "check": "6028565819225542441",
    "channel": "6035277294036061660",
    "admin_add": "6034851808805918335",
    "stock": "5294118392905623955",
    "broadcast": "5780405967527089720",
    "users": "5985525762973768278",
    "edit": "5341715473882955310",
}

MESSAGE_EMOJI_IDS = {
    "party": "5989848973974704652", "stop": "5974083768233760323", "wave": "4983292515932177130", 
    "check": "5980930633298350051", "cross": "6158841463032519010", "warning": "5787656288934564517", 
    "link": "5292122921035133343", "stats": "5431577498364158238", "people": "5402211308017840657", 
    "box": "5415750994849976302", "green": "5416081784641168838", "red": "5420323339723881652", 
    "yellow": "5789570564448326827", "gear": "5341715473882955310", "plus": "5226945370684140473", 
    "megaphone": "5836698068061261980", "hourglass": "5451646226975955576", "repeat": "5264727218734524899", 
    "sparkles": "5089460564141278042"
}

MESSAGE_EMOJI_MAP = {
    "🎉": "party", "🛑": "stop", "👋": "wave", "✅": "check",
    "❌": "cross", "⚠️": "warning", "🔗": "link", "📊": "stats",
    "👥": "people", "📦": "box", "🟢": "green", "🔴": "red",
    "🟡": "yellow", "⚙️": "gear", "➕": "plus", "📢": "megaphone",
    "⏳": "hourglass", "🔁": "repeat", "✨": "sparkles"
}

def premium_button(text, callback_data=None, style=None, emoji_key=None, url=None, web_app=None):
    kwargs = {"text": text, "callback_data": callback_data}
    if style in ["primary", "success", "danger"]:
        kwargs["style"] = style
    if url is not None:
        kwargs.pop("callback_data", None)
        kwargs["url"] = url
    if web_app is not None:
        kwargs.pop("callback_data", None)
        kwargs["web_app"] = web_app
    emoji_id = CUSTOM_EMOJI_IDS.get(emoji_key or "")
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(**kwargs)

def parse_premium_markdown(text):
    clean_chars = []
    entities = []
    in_bold, in_code = False, False
    bold_start, code_start = 0, 0
    
    def utf16_len(s):
        return len(s.encode("utf-16-le")) // 2

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '*' and not in_code:
            curr_pos = utf16_len("".join(clean_chars))
            if not in_bold:
                in_bold, bold_start = True, curr_pos
            else:
                in_bold = False
                length = curr_pos - bold_start
                if length > 0:
                    entities.append(MessageEntity(type=MessageEntity.BOLD, offset=bold_start, length=length))
            i += 1
            continue
        elif ch == '`' and not in_bold:
            curr_pos = utf16_len("".join(clean_chars))
            if not in_code:
                in_code, code_start = True, curr_pos
            else:
                in_code = False
                length = curr_pos - code_start
                if length > 0:
                    entities.append(MessageEntity(type=MessageEntity.CODE, offset=code_start, length=length))
            i += 1
            continue
        else:
            clean_chars.append(ch)
            i += 1
            
    final_text = "".join(clean_chars)

    for emoji, key in sorted(MESSAGE_EMOJI_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        emoji_id = MESSAGE_EMOJI_IDS.get(key)
        if not emoji_id:
            continue
        start = 0
        while True:
            pos = final_text.find(emoji, start)
            if pos < 0:
                break
            offset = utf16_len(final_text[:pos])
            length = utf16_len(emoji)
            entities.append(MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=offset,
                length=length,
                custom_emoji_id=emoji_id,
            ))
            start = pos + len(emoji)
            
    entities.sort(key=lambda e: (e.offset, e.length))
    return final_text, entities

async def reply_premium(message, text, **kwargs):
    final_text, entities = parse_premium_markdown(text)
    kwargs.pop("parse_mode", None)
    try:
        return await message.reply_text(final_text, entities=entities or None, **kwargs)
    except Exception:
        return await message.reply_text(text, parse_mode="Markdown", **kwargs)

async def send_premium(bot, chat_id, text, **kwargs):
    final_text, entities = parse_premium_markdown(text)
    kwargs.pop("parse_mode", None)
    try:
        return await bot.send_message(chat_id=chat_id, text=final_text, entities=entities or None, **kwargs)
    except Exception:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", **kwargs)

async def edit_premium(message, text, **kwargs):
    final_text, entities = parse_premium_markdown(text)
    kwargs.pop("parse_mode", None)
    try:
        return await message.edit_text(final_text, entities=entities or None, **kwargs)
    except Exception as e:
        if "Message is not modified" in str(e):
            return message
        try:
            return await message.edit_text(text, parse_mode="Markdown", **kwargs)
        except Exception:
            return await message.reply_text(text, parse_mode="Markdown", **kwargs)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ----------------- FAST DATABASE CONFIG -----------------
DATA_DIR = os.getenv("DATA_DIR", "/data")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "bot_data.db")
except Exception:
    DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=10000;")
    return conn

def split_json_entries(raw_text: str):
    """Reliably splits multiple JSONs whether separated by --- or plain braces."""
    if "---" in raw_text:
        return [x.strip() for x in raw_text.split("---") if x.strip()]

    extracted = []
    stack = 0
    start_idx = None
    for idx, char in enumerate(raw_text):
        if char == '{':
            if stack == 0:
                start_idx = idx
            stack += 1
        elif char == '}':
            stack -= 1
            if stack == 0 and start_idx is not None:
                item = raw_text[start_idx:idx+1].strip()
                if item:
                    extracted.append(item)
                start_idx = None

    return extracted if extracted else ([raw_text.strip()] if raw_text.strip() else [])

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            credits INTEGER DEFAULT 0,
            claimed_count INTEGER DEFAULT 0,
            device_id TEXT UNIQUE,
            ip_address TEXT,
            last_start_time TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS meesho_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            is_claimed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS file_claims (
            user_id INTEGER,
            file_id INTEGER NOT NULL,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels_config_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            name TEXT,
            chat_id TEXT UNIQUE,
            url TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS join_requests (
            user_id INTEGER,
            chat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    c.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('points_meesho', 7)")
    conn.commit()

    # Old multi-block clean-up safely inside migration
    try:
        c.execute("SELECT id, content FROM meesho_files WHERE is_claimed = 0")
        for row_id, content in c.fetchall():
            if "---" in content or content.count('{"mobile":') > 1:
                parts = split_json_entries(content)
                if len(parts) > 1:
                    c.execute("DELETE FROM meesho_files WHERE id = ?", (row_id,))
                    for p in parts:
                        c.execute("INSERT INTO meesho_files (content, is_claimed) VALUES (?, 0)", (p,))
        conn.commit()
    except Exception as e:
        logging.error(f"Migration note: {e}")

    conn.close()

init_db()

# Asynchronous DB wrappers for non-blocking execution
async def db_get_required_points():
    def query():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT value FROM bot_settings WHERE key = 'points_meesho'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else 7
    return await asyncio.to_thread(query)

async def db_update_required_points(val: int):
    def query():
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('points_meesho', ?)", (val,))
        conn.commit()
        conn.close()
    return await asyncio.to_thread(query)

async def db_get_current_stock():
    def query():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM meesho_files WHERE is_claimed = 0")
        val = c.fetchone()[0]
        conn.close()
        return val
    return await asyncio.to_thread(query)

def parse_chat_id(val: str):
    val = str(val).strip()
    if val.startswith("-") or val.isdigit():
        try:
            return int(val)
        except ValueError:
            return val
    if not val.startswith("@") and not val.startswith("-"):
        return f"@{val}"
    return val

async def db_get_all_channels():
    def query():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, type, name, chat_id, url FROM channels_config_v2")
        rows = c.fetchall()
        conn.close()
        channels = []
        for r in rows:
            cid = parse_chat_id(r[3])
            channels.append({
                "db_id": r[0],
                "type": r[1],
                "name": r[2],
                "id": cid,
                "raw_id": str(r[3]).strip(),
                "url": r[4]
            })
        return channels
    return await asyncio.to_thread(query)

# ----------------- KEYBOARDS -----------------
async def get_join_keyboard():
    keyboard = []
    row = []
    channels = await db_get_all_channels()
    for ch in channels:
        row.append(premium_button(f"✨ {ch['name']}", None, "primary", "channel", url=ch["url"]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([premium_button("✅ ᴄʜᴇᴄᴋ ᴊᴏɪɴᴇᴅ", "check_join", "success", "check")])
    return InlineKeyboardMarkup(keyboard)

def get_verify_keyboard(bot_username: str = ""):
    clean_url = VERIFY_WEBAPP_URL
    if bot_username:
        sep = "&" if "?" in clean_url else "?"
        clean_url = f"{clean_url}{sep}bot={bot_username}"
    return InlineKeyboardMarkup([
        [premium_button("🛡️ ᴠᴇʀɪғʏ ᴅᴇᴠɪᴄᴇ ɴᴏᴡ", None, "primary", "check", web_app=WebAppInfo(url=clean_url))]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            premium_button("🔗 ʀᴇғᴇʀʀᴀʟ ʟɪɴᴋ", "ref_link", "primary", "ref_link"),
            premium_button("📊 ᴍʏ sᴛᴀᴛs", "my_stats", "primary", "stats"),
        ],
        [
            premium_button("🛍️ ᴡɪᴛʜᴅʀᴀᴡ sᴛᴏʀᴇ", "withdraw_menu", "success", "cute_gift"),
            premium_button("👥 ᴍʏ ɴᴇᴛᴡᴏʀᴋ", "my_referrals", "primary", "referrals"),
        ],
        [
            premium_button("📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ?", "how_to_order", "primary", "cute_star"),
        ],
        [
            premium_button("📢 ʟɪᴠᴇ ᴘʀᴏᴏғs ᴄʜᴀɴɴᴇʟ", None, "primary", "channel", url=PROOF_CHANNEL_URL)
        ]
    ])

async def get_withdraw_keyboard():
    stock = await db_get_current_stock()
    if stock > 0:
        claim_btn = premium_button(f"🛍️ ᴍᴇᴇsʜᴏ ғʀᴇᴇ ᴊsᴏɴ — ғʀᴇᴇ | {stock} ᴘᴄs", "confirm_claim_file", "success", "cute_gift")
    else:
        claim_btn = premium_button("🛍️ ᴍᴇᴇsʜᴏ ғʀᴇᴇ ᴊsᴏɴ — ᴏᴜᴛ ᴏғ sᴛᴏᴄᴋ", "stock_empty_alert", "danger", "cross")
        
    return InlineKeyboardMarkup([
        [claim_btn],
        [premium_button("🔙 ʙᴀᴄᴋ", "back_to_main", None, "repeat")]
    ])

async def get_admin_keyboard():
    pts = await db_get_required_points()
    return InlineKeyboardMarkup([
        [
            premium_button("➕ ᴀᴅᴅ ᴊsᴏɴs (ʙᴜʟᴋ)", "admin_bulk_files", "primary", "admin_add"),
        ],
        [
            premium_button(f"⚙️ ᴍɪɴ ᴘᴏɪɴᴛs ({pts}ᴘ)", "admin_edit_pts", "primary", "edit"),
            premium_button("📦 sᴛᴏᴄᴋ sᴛᴀᴛᴜs", "admin_stock", "success", "stock"),
        ],
        [
            premium_button("📢 ᴍᴀɴᴀɢᴇ ᴄʜᴀɴɴᴇʟs", "admin_channel_menu", "primary", "channel"),
            premium_button("👥 ᴜsᴇʀ sᴛᴀᴛs", "admin_users", "primary", "users"),
        ],
        [
            premium_button("➕ ᴀᴅᴅ ᴜsᴇʀ ᴘᴏɪɴᴛs", "admin_add_user_points", "primary", "admin_add"),
            premium_button("➖ ᴅᴇᴅᴜᴄᴛ ᴜsᴇʀ ᴘᴏɪɴᴛs", "admin_deduct_user_points", "danger", "edit"),
        ],
        [
            premium_button("📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ", "admin_broadcast_prompt", "primary", "broadcast"),
            premium_button("🔄 ʀᴇғʀᴇsʜ ᴘᴀɴᴇʟ", "admin_refresh", None, "repeat"),
        ]
    ])

async def get_admin_channel_keyboard():
    channels = await db_get_all_channels()
    kb = [
        [premium_button("➕ ᴀᴅᴅ ᴘᴜʙʟɪᴄ", "admin_add_public", "primary", "plus")],
        [premium_button("➕ ᴀᴅᴅ ᴘʀɪᴠᴀᴛᴇ", "admin_add_private", "primary", "plus")],
        [premium_button("➕ ᴀᴅᴅ ʀᴇǫᴜᴇsᴛ", "admin_add_request", "primary", "plus")]
    ]
    if channels:
        for ch in channels:
            kb.append([premium_button(f"❌ ᴅᴇʟᴇᴛᴇ {ch['name']}", f"admin_del_{ch['db_id']}", "danger", "cross")])
    kb.append([premium_button("🔙 ʙᴀᴄᴋ", "admin_back_to_panel")])
    return InlineKeyboardMarkup(kb)

# ----------------- PARALLEL NON-BLOCKING HELPERS -----------------
async def track_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if req:
        u_id = req.user_chat_id
        c_id = str(req.chat.id)
        def query():
            conn = get_db()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO join_requests (user_id, chat_id) VALUES (?, ?)", (u_id, c_id))
            conn.commit()
            conn.close()
        await asyncio.to_thread(query)

async def get_unjoined_channels(user_id: int, bot):
    channels = await db_get_all_channels()
    if not channels:
        return []

    def get_reqs():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT chat_id FROM join_requests WHERE user_id = ?", (user_id,))
        rows = {str(row[0]) for row in c.fetchall()}
        conn.close()
        return rows

    requested_chats = await asyncio.to_thread(get_reqs)
    now = time.time()
    unjoined = []

    for ch in channels:
        target_id = ch["id"]
        str_id = str(target_id)
        raw_str = ch["raw_id"]

        if str_id in requested_chats or raw_str in requested_chats:
            continue

        cache_key = (user_id, str_id)
        if cache_key in MEMBERSHIP_CACHE:
            is_mem, exp = MEMBERSHIP_CACHE[cache_key]
            if now < exp:
                if not is_mem:
                    unjoined.append(ch)
                continue

        try:
            member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status in ["member", "administrator", "creator", "restricted"]:
                MEMBERSHIP_CACHE[cache_key] = (True, now + CACHE_TTL)
                continue
            else:
                MEMBERSHIP_CACHE[cache_key] = (False, now + CACHE_TTL)
                unjoined.append(ch)
        except Exception:
            if str_id in requested_chats or raw_str in requested_chats:
                continue
            unjoined.append(ch)
            
    return unjoined

async def is_device_verified(user_id: int) -> bool:
    def query():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT device_id FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0])
    return await asyncio.to_thread(query)

async def send_welcome_dashboard(bot, user_id: int):
    pts = await db_get_required_points()
    welcome_text = (
        "╭─ *✨ ʟɪᴠᴇ sᴛᴏʀᴇ & ᴅᴀsʜʙᴏᴀʀᴅ ✨*\n"
        "│\n"
        "│ • *Auto Dispatch:* Active 24/7\n"
        "│ • *Instant Recovery:* Seamless Retrieval\n"
        f"│ • *Redeem Target:* `{pts} Verified Referrals`\n"
        f"│ • *Live Proofs:* Synchronized ({PROOF_CHANNEL})\n"
        "│\n"
        "╰───────────────────────────\n\n"
        "🔥 *FRESH STOCK AVAILABLE!*\n"
        "Select an option from below 👇"
    )
    return await send_premium(
        bot,
        user_id,
        welcome_text,
        reply_markup=get_main_keyboard(),
        message_effect_id=MESSAGE_CONFETTI_EFFECT_ID,
        disable_web_page_preview=True
    )

# ----------------- COMMAND & CALLBACK HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    args = context.args
    bot_info = await context.bot.get_me()

    if args and args[0].startswith("v_"):
        device_id = args[0].replace("v_", "")
        
        def handle_verification():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE device_id = ? AND user_id != ?", (device_id, user_id))
            if c.fetchone():
                conn.close()
                return "FRAUD", None, 0

            c.execute("SELECT referrer_id, device_id FROM users WHERE user_id = ?", (user_id,))
            u = c.fetchone()
            ref_id = None
            new_balance = 0

            if u:
                if not u[1]:
                    ref_id = u[0]
                    c.execute("UPDATE users SET device_id = ? WHERE user_id = ?", (device_id, user_id))
                    if ref_id:
                        c.execute("UPDATE users SET credits = credits + 1 WHERE user_id = ?", (ref_id,))
                        c.execute("SELECT credits FROM users WHERE user_id = ?", (ref_id,))
                        bal_row = c.fetchone()
                        new_balance = bal_row[0] if bal_row else 1
                    conn.commit()
            else:
                c.execute("INSERT INTO users (user_id, referrer_id, credits, claimed_count, device_id) VALUES (?, NULL, 0, 0, ?)", (user_id, device_id))
                conn.commit()
            conn.close()
            return "SUCCESS", ref_id, new_balance

        status, ref_id, new_balance = await asyncio.to_thread(handle_verification)
        if status == "FRAUD":
            await reply_premium(
                update.message,
                "╭─ *🛑 sᴇᴄᴜʀɪᴛʏ ᴀʟᴇʀᴛ 🛑*\n│\n│ ⚠️ *Device Already Registered!*\n│ • *Rule:* Only 1 account per device.\n╰───────────────────────────"
            )
            return

        await send_welcome_dashboard(context.bot, user_id)
        if ref_id:
            try:
                masked = str(user_id)[:4] + "****" + str(user_id)[-2:]
                alert_text = (
                    "╭─ *🎉 ʀᴇғᴇʀʀᴀʟ ʀᴇᴡᴀʀᴅ 🎉*\n"
                    "│\n"
                    f"│ 👤 *Verified User:* `{masked}`\n"
                    "│ 💰 *Reward:* `+1 Point`\n"
                    f"│ 📊 *Balance:* `{new_balance} Points`\n"
                    "╰───────────────────────────\n\n"
                    "🚀 *Keep inviting friends to earn more free files!*"
                )
                await send_premium(context.bot, ref_id, alert_text)
            except Exception:
                pass
        return

    def ensure_user():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            referrer = None
            if args and args[0].isdigit() and int(args[0]) != user_id:
                referrer = int(args[0])
            c.execute("INSERT INTO users (user_id, referrer_id, credits, claimed_count) VALUES (?, ?, 0, 0)", (user_id, referrer))
            conn.commit()
        conn.close()

    await asyncio.to_thread(ensure_user)

    unjoined = await get_unjoined_channels(user_id, context.bot)
    if unjoined:
        missing_names = "\n".join([f"• *{ch['name']}*" for ch in unjoined])
        text = (
            "╭─ *🛑 ᴍᴇᴍʙᴇʀsʜɪᴘ ʀᴇǫᴜɪʀᴇᴅ 🛑*\n"
            "│\n"
            "│ *Join our official channels to continue:*\n"
            f"{missing_names}\n"
            "╰───────────────────────────\n\n"
            "👉 *Tap the buttons below and click CHECK JOINED.*"
        )
        join_kb = await get_join_keyboard()
        await reply_premium(update.message, text, reply_markup=join_kb, disable_web_page_preview=True)
        return

    verified = await is_device_verified(user_id)
    if not verified:
        text = (
            "╭─ *🔒 ᴀᴄᴄᴏᴜɴᴛ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ 🔒*\n"
            "│\n"
            "│ ⚠️ *Physical Hardware Check Required!*\n"
            "│ Authorize your device to unlock instant claims.\n"
            "╰───────────────────────────"
        )
        await reply_premium(update.message, text, reply_markup=get_verify_keyboard(bot_info.username))
        return

    await send_welcome_dashboard(context.bot, user_id)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_user.id != ADMIN_ID:
        return
    pts = await db_get_required_points()
    stock = await db_get_current_stock()
    admin_kb = await get_admin_keyboard()
    await reply_premium(
        update.message,
        "╭─ *⚙️ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ ⚙️*\n"
        "│\n"
        "│ 📦 *Product:* `Meesho Free JSON`\n"
        f"│ 🎯 *Points Needed:* `{pts} Points`\n"
        f"│ 📊 *Stock Live:* `{stock} Files`\n"
        "╰───────────────────────────\n\n"
        "*Select an admin action below:*",
        reply_markup=admin_kb
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    bot_info = await context.bot.get_me()

    if data == "check_join":
        # Cache invalidate on manual check
        for k in list(MEMBERSHIP_CACHE.keys()):
            if k[0] == user_id:
                MEMBERSHIP_CACHE.pop(k, None)
                
        unjoined = await get_unjoined_channels(user_id, context.bot)
        if not unjoined:
            await query.answer("✅ Verified Successfully!", show_alert=False)
            verified = await is_device_verified(user_id)
            if not verified:
                text = (
                    "╭─ *🔒 ᴀᴄᴄᴏᴜɴᴛ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ 🔒*\n"
                    "│\n"
                    "│ ⚠️ *Final Step: Complete device authorization!*\n"
                    "╰───────────────────────────"
                )
                await edit_premium(query.message, text, reply_markup=get_verify_keyboard(bot_info.username))
            else:
                await send_welcome_dashboard(context.bot, user_id)
        else:
            names = ", ".join([ch["name"] for ch in unjoined])
            await query.answer(f"⚠️ Action Required!\nPlease join:\n{names}", show_alert=True)
            missing_names = "\n".join([f"• *{ch['name']}*" for ch in unjoined])
            text = (
                "╭─ *🛑 ᴍᴇᴍʙᴇʀsʜɪᴘ ʀᴇǫᴜɪʀᴇᴅ 🛑*\n"
                "│\n"
                f"{missing_names}\n"
                "╰───────────────────────────\n\n"
                "👉 *Tap buttons below and click CHECK JOINED.*"
            )
            join_kb = await get_join_keyboard()
            try:
                await edit_premium(query.message, text, reply_markup=join_kb, disable_web_page_preview=True)
            except Exception:
                pass
        return

    if data == "stock_empty_alert":
        await query.answer("🥺 Opps! Currently Out of Stock! Restocking soon. 🚀", show_alert=True)
        return

    if data == "how_to_order":
        guide_text = (
            "╭─ *📖 ʜᴏᴡ ᴛᴏ ᴏʀᴅᴇʀ & sᴇᴛᴜᴘ ɢᴜɪᴅᴇ 📖*\n"
            "│\n"
            "│ ✨ *Hey! Full process set-up is posted here:*\n"
            f"│ 🔗 `{SETUP_GUIDE_URL}`\n"
            "│\n"
            "│ • Complete step-by-step tutorial\n"
            "│ • Free Order Script details\n"
            "│ • 24/7 Support instructions\n"
            "╰───────────────────────────"
        )
        guide_kb = InlineKeyboardMarkup([
            [premium_button("👉 ᴏᴘᴇɴ sᴇᴛᴜᴘ ɢᴜɪᴅᴇ", None, "success", "cute_star", url=SETUP_GUIDE_URL)],
            [premium_button("🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ", "back_to_main", None, "repeat")]
        ])
        await edit_premium(query.message, guide_text, reply_markup=guide_kb, disable_web_page_preview=True)
        return

    await query.answer()

    if data == "ref_link":
        pts = await db_get_required_points()
        link = f"https://t.me/{bot_info.username}?start={user_id}"
        ref_text = (
            "╭─ *🔗 ʏᴏᴜʀ ᴇxᴄʟᴜsɪᴠᴇ ʟɪɴᴋ 🔗*\n"
            "│\n"
            f"│ `{link}`\n"
            "│\n"
            "│ • *Per Referral:* `+1 Point`\n"
            f"│ • *Redeem:* `{pts} Points = 1 Meesho JSON`\n"
            "╰───────────────────────────\n\n"
            "🚀 *Share this link in groups & channels to earn daily!*"
        )
        await reply_premium(query.message, ref_text, disable_web_page_preview=True)

    elif data == "my_stats":
        def get_stats():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT credits, claimed_count FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            credits = row[0] if row else 0
            claimed = row[1] if row else 0
            c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND device_id IS NOT NULL", (user_id,))
            my_refs = c.fetchone()[0]
            c.execute("""
                SELECT referrer_id, COUNT(user_id) as total_refs
                FROM users WHERE referrer_id IS NOT NULL AND device_id IS NOT NULL
                GROUP BY referrer_id ORDER BY total_refs DESC LIMIT 3
            """)
            top = c.fetchall()
            conn.close()
            return credits, claimed, my_refs, top

        credits, claimed, my_refs, top_users = await asyncio.to_thread(get_stats)
        pts = await db_get_required_points()

        leaderboard_str = ""
        rank_emojis = ["🥇", "🥈", "🥉"]
        if top_users:
            for idx, (top_id, count) in enumerate(top_users):
                medal = rank_emojis[idx] if idx < len(rank_emojis) else f"{idx+1}."
                leaderboard_str += f"│ {medal} `{top_id}` ➔ *{count} Refs*\n"
        else:
            leaderboard_str = "│ No top referrers yet!\n"

        stats_text = (
            "╭─ *📊 ᴀᴄᴄᴏᴜɴᴛ ᴏᴠᴇʀᴠɪᴇᴡ 📊*\n"
            "│\n"
            f"│ 💰 *Available Balance:* `{credits} Points`\n"
            f"│ 👥 *Verified Network:* `{my_refs} Users`\n"
            f"│ 🎁 *Total Claimed:* `{claimed} Files`\n"
            "│\n"
            f"│ 🎯 *Redeem Rate:* `{pts} Points ➔ 1 Free JSON`\n"
            "╰───────────────────────────\n\n"
            "🏆 *ᴛᴏᴘ ʀᴇғᴇʀʀᴇʀs ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ:*\n"
            f"{leaderboard_str}"
        )
        await reply_premium(query.message, stats_text)

    elif data == "my_referrals":
        def get_refs():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND device_id IS NOT NULL", (user_id,))
            count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND device_id IS NULL", (user_id,))
            pending = c.fetchone()[0]
            conn.close()
            return count, pending

        count, pending = await asyncio.to_thread(get_refs)
        refs_text = (
            "╭─ *👥 ʏᴏᴜʀ ɴᴇᴛᴡᴏʀᴋ 👥*\n"
            "│\n"
            f"│ ✅ *Active Verified:* `{count} Users` (+{count} Pts)\n"
            f"│ ⏳ *Pending Device Check:* `{pending} Users`\n"
            "╰───────────────────────────\n\n"
            "💡 *Points are credited immediately upon device activation.*"
        )
        await reply_premium(query.message, refs_text)

    elif data == "withdraw_menu":
        withdraw_text = (
            "╭─ *🛍️ ʟɪᴠᴇ sᴛᴏʀᴇ 🛍️*\n"
            "│\n"
            "│ 🔥 *FRESH STOCK AVAILABLE!*\n"
            "│ Select a voucher below 👇\n"
            "╰───────────────────────────"
        )
        withdraw_kb = await get_withdraw_keyboard()
        await edit_premium(query.message, withdraw_text, reply_markup=withdraw_kb)

    elif data == "back_to_main":
        pts = await db_get_required_points()
        welcome_text = (
            "╭─ *✨ ʟɪᴠᴇ sᴛᴏʀᴇ & ᴅᴀsʜʙᴏᴀʀᴅ ✨*\n"
            "│\n"
            "│ • *Auto Dispatch:* Active 24/7\n"
            "│ • *Instant Recovery:* Seamless Retrieval\n"
            f"│ • *Redeem Target:* `{pts} Verified Referrals`\n"
            f"│ • *Live Proofs:* Synchronized ({PROOF_CHANNEL})\n"
            "│\n"
            "╰───────────────────────────\n\n"
            "🔥 *FRESH STOCK AVAILABLE!*\n"
            "Select an option from below 👇"
        )
        await edit_premium(
            query.message,
            welcome_text,
            reply_markup=get_main_keyboard(),
            disable_web_page_preview=True
        )

    elif data == "confirm_claim_file":
        pts = await db_get_required_points()

        def process_redemption():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            user_credits = row[0] if row else 0

            if user_credits < pts:
                conn.close()
                return "LOW_POINTS", user_credits, None, None

            c.execute("SELECT id, content FROM meesho_files WHERE is_claimed = 0 ORDER BY id ASC LIMIT 1")
            file_item = c.fetchone()

            if not file_item:
                conn.close()
                return "NO_STOCK", user_credits, None, None

            f_id, f_content = file_item
            pieces = split_json_entries(f_content)
            single_to_deliver = pieces[0]

            c.execute("UPDATE meesho_files SET is_claimed = 1 WHERE id = ?", (f_id,))
            if len(pieces) > 1:
                for extra in pieces[1:]:
                    c.execute("INSERT INTO meesho_files (content, is_claimed) VALUES (?, 0)", (extra,))

            c.execute("UPDATE users SET credits = credits - ?, claimed_count = claimed_count + 1 WHERE user_id = ?", (pts, user_id))
            c.execute("INSERT INTO file_claims (user_id, file_id) VALUES (?, ?)", (user_id, f_id))
            conn.commit()
            conn.close()
            return "SUCCESS", user_credits, f_id, single_to_deliver

        res_status, user_credits, f_id, single_to_deliver = await asyncio.to_thread(process_redemption)

        if res_status == "LOW_POINTS":
            await query.answer(f"❌ Insufficient Points! You have {user_credits}, needed {pts}.", show_alert=True)
            return

        if res_status == "NO_STOCK":
            await query.answer("🥺 Opps! Currently Out of Stock! Restocking soon.", show_alert=True)
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *STOCK OVER ALERT*\nUser `{user_id}` attempted to withdraw Meesho JSON.", parse_mode="Markdown")
            except Exception:
                pass
            await reply_premium(
                query.message, 
                "╭─ *📦 ᴏᴜᴛ ᴏғ sᴛᴏᴄᴋ 📦*\n│\n│ 🥺 Meesho Free JSON files are exhausted.\n╰───────────────────────────",
                reply_markup=InlineKeyboardMarkup([
                    [premium_button("📢 ʟɪᴠᴇ ᴘʀᴏᴏғs ᴄʜᴀɴɴᴇʟ", None, "primary", "channel", url=PROOF_CHANNEL_URL)],
                    [premium_button("🔙 ʙᴀᴄᴋ", "back_to_main", None, "repeat")]
                ]),
                disable_web_page_preview=True
            )
            return

        file_data = io.BytesIO(single_to_deliver.strip().encode("utf-8"))
        file_data.name = f"meesho_free_json_{user_id}_{f_id}.txt"

        caption = (
            "╭─ *🎉 ᴅɪsᴘᴀᴛᴄʜ sᴜᴄᴄᴇssғᴜʟ 🎉*\n"
            "│\n"
            "│ 📦 *Item:* `Meesho Free JSON`\n"
            f"│ 💰 *Deducted:* `{pts} Points`\n"
            "│ ⚡ *Delivery:* Instant Auto-Dispatch\n"
            f"│ 📢 *Proof Channel:* {PROOF_CHANNEL}\n"
            "╰───────────────────────────"
        )
        
        await context.bot.send_document(
            chat_id=user_id,
            document=file_data,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [premium_button("📢 ᴄʜᴇᴄᴋ ᴘʀᴏᴏғs ʜᴇʀᴇ", None, "primary", "channel", url=PROOF_CHANNEL_URL)],
                [premium_button("🔙 ᴍᴀɪɴ ᴍᴇɴᴜ", "back_to_main", None, "repeat")]
            ])
        )

        try:
            masked_uid = str(user_id)[:4] + "****" + str(user_id)[-2:]
            proof_msg = (
                "╭─ *🎉 ɴᴇᴡ ᴏʀᴅᴇʀ ᴅɪsᴘᴀᴛᴄʜ 🎉*\n"
                "│\n"
                f"│ 👤 *User:* `{masked_uid}`\n"
                "│ 📦 *Item:* `Meesho Free JSON File`\n"
                "│ ✅ *Status:* Delivered 24/7\n"
                f"│ 🤖 *Bot:* @{bot_info.username}\n"
                "╰───────────────────────────"
            )
            await send_premium(context.bot, PROOF_CHANNEL, proof_msg, disable_web_page_preview=True)
        except Exception:
            pass

    elif data == "admin_stock":
        if user_id != ADMIN_ID:
            return
        stock = await db_get_current_stock()
        await reply_premium(query.message, f"╭─ *📦 sᴛᴏᴄᴋ sᴛᴀᴛᴜs*\n│\n│ Available Meesho JSON Files: `{stock}`\n╰──────────────────")

    elif data == "admin_users":
        if user_id != ADMIN_ID:
            return
        def get_user_stats():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE device_id IS NOT NULL")
            verified_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM file_claims")
            total_claims = c.fetchone()[0]
            conn.close()
            return total_users, verified_users, total_claims

        t_users, v_users, claims = await asyncio.to_thread(get_user_stats)
        await reply_premium(
            query.message,
            f"╭─ *👥 ᴜsᴇʀ sᴛᴀᴛs 👥*\n│\n│ • Total Registered: `{t_users}`\n│ • Verified Devices: `{v_users}`\n│ • Total Dispatches: `{claims}`\n╰───────────────────"
        )

    elif data == "admin_bulk_files":
        if user_id != ADMIN_ID:
            return
        context.user_data["admin_action"] = "bulk_add_files"
        instructions = (
            "╭─ *➕ ʙᴜʟᴋ ᴀᴅᴅ ᴊsᴏɴ ғɪʟᴇs*\n"
            "│\n"
            "│ Paste multiple JSON contents separated by `---` line:\n"
            "│ `{\"token\": \"abc1\"}`\n"
            "│ `---`\n"
            "│ `{\"token\": \"abc2\"}`\n"
            "╰───────────────────\n\n"
            "Send the message now:"
        )
        await reply_premium(query.message, instructions)

    elif data == "admin_edit_pts":
        if user_id != ADMIN_ID:
            return
        context.user_data["admin_action"] = "edit_points"
        await reply_premium(query.message, "⚙️ Reply with the new points required for 1 Meesho JSON:")

    elif data == "admin_channel_menu":
        if user_id != ADMIN_ID:
            return
        channels = await db_get_all_channels()
        info_lines = "\n".join([f"│ • {ch['name']} (`{ch['id']}`)" for ch in channels]) if channels else "│ No channels configured."
        channel_kb = await get_admin_channel_keyboard()
        await edit_premium(
            query.message,
            f"╭─ *📢 ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ*\n│ Total: `{len(channels)}`\n│\n{info_lines}\n╰───────────────────",
            reply_markup=channel_kb,
            disable_web_page_preview=True
        )

    elif data in ["admin_add_public", "admin_add_private", "admin_add_request"]:
        if user_id != ADMIN_ID:
            return
        ch_type = data.replace("admin_add_", "")
        context.user_data["admin_action"] = f"add_channel_{ch_type}"
        await reply_premium(
            query.message,
            "⚙️ *ADD CHANNEL*\nFormat: `Name | Chat ID | URL`\nExample: `Main | -100123456789 | https://t.me/+xyz`"
        )

    elif data.startswith("admin_del_"):
        if user_id != ADMIN_ID:
            return
        db_id = int(data.replace("admin_del_", ""))
        def del_ch():
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM channels_config_v2 WHERE id = ?", (db_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(del_ch)
        await query.answer("✅ Channel Deleted!", show_alert=True)
        channels = await db_get_all_channels()
        info_lines = "\n".join([f"│ • {ch['name']} (`{ch['id']}`)" for ch in channels]) if channels else "│ No channels configured."
        channel_kb = await get_admin_channel_keyboard()
        await edit_premium(
            query.message,
            f"╭─ *📢 ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ*\n│ Total: `{len(channels)}`\n│\n{info_lines}\n╰───────────────────",
            reply_markup=channel_kb,
            disable_web_page_preview=True
        )

    elif data == "admin_back_to_panel":
        if user_id != ADMIN_ID:
            return
        pts = await db_get_required_points()
        stock = await db_get_current_stock()
        admin_kb = await get_admin_keyboard()
        await edit_premium(
            query.message,
            f"╭─ *⚙️ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ*\n│ • Points: `{pts}p`\n│ • Stock: `{stock} pcs`\n╰───────────────────",
            reply_markup=admin_kb
        )

    elif data == "admin_broadcast_prompt":
        if user_id != ADMIN_ID:
            return
        context.user_data["admin_action"] = "broadcast"
        await reply_premium(query.message, "📢 Send the broadcast message text:")

    elif data in ["admin_add_user_points", "admin_deduct_user_points"]:
        if user_id != ADMIN_ID:
            return
        context.user_data["admin_action"] = data
        action_name = "ADD" if data == "admin_add_user_points" else "DEDUCT"
        await reply_premium(query.message, f"👤 *{action_name} USER POINTS*\nSend format: `USER_ID AMOUNT`")

    elif data == "admin_refresh":
        if user_id != ADMIN_ID:
            return
        pts = await db_get_required_points()
        stock = await db_get_current_stock()
        admin_kb = await get_admin_keyboard()
        await edit_premium(
            query.message, 
            f"╭─ *⚙️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ (ʀᴇғʀᴇsʜᴇᴅ)*\n│ • Points: `{pts}p`\n│ • Stock: `{stock} pcs`\n╰───────────────────", 
            reply_markup=admin_kb
        )

# ----------------- ADMIN INPUT HANDLER -----------------
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    admin_kb = await get_admin_keyboard()
    
    if user_id == ADMIN_ID and "admin_action" in context.user_data:
        action = context.user_data.pop("admin_action")
        
        if action == "bulk_add_files":
            entries = split_json_entries(text)
            def save_bulk():
                conn = get_db()
                c = conn.cursor()
                added = 0
                for item in entries:
                    if item:
                        c.execute("INSERT INTO meesho_files (content, is_claimed) VALUES (?, 0)", (item,))
                        added += 1
                conn.commit()
                conn.close()
                return added
            added = await asyncio.to_thread(save_bulk)
            await reply_premium(update.message, f"✅ Successfully added `{added}` individual Meesho JSON files!", reply_markup=admin_kb)

        elif action == "edit_points":
            if not text.isdigit() or int(text) <= 0:
                await reply_premium(update.message, "❌ Invalid point value.")
                return
            val = int(text)
            await db_update_required_points(val)
            await reply_premium(update.message, f"✅ Updated to `{val} Points` required.", reply_markup=admin_kb)

        elif action.startswith("add_channel_"):
            ch_type = action.replace("add_channel_", "")
            parts = [p.strip() for p in text.split("|")]
            if len(parts) != 3:
                channel_kb = await get_admin_channel_keyboard()
                await reply_premium(update.message, "❌ Use: `Name | Chat ID | URL`", reply_markup=channel_kb)
                return
            def add_ch():
                conn = get_db()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO channels_config_v2 (type, name, chat_id, url) 
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET type=excluded.type, name=excluded.name, url=excluded.url
                """, (ch_type, parts[0], parts[1].strip(), parts[2].strip()))
                conn.commit()
                conn.close()
            await asyncio.to_thread(add_ch)
            await reply_premium(update.message, "✅ Channel Added Successfully!", reply_markup=admin_kb)

        elif action in ["admin_add_user_points", "admin_deduct_user_points"]:
            try:
                parts = text.strip().split()
                target_id = int(parts[0])
                amount = int(parts[1])
                def update_user():
                    conn = get_db()
                    c = conn.cursor()
                    c.execute("SELECT credits FROM users WHERE user_id = ?", (target_id,))
                    row = c.fetchone()
                    if not row:
                        conn.close()
                        return None
                    old_p = int(row[0] or 0)
                    new_p = old_p + amount if action == "admin_add_user_points" else max(0, old_p - amount)
                    c.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_p, target_id))
                    conn.commit()
                    conn.close()
                    return new_p
                new_balance = await asyncio.to_thread(update_user)
                if new_balance is None:
                    await reply_premium(update.message, f"❌ User `{target_id}` not found.")
                else:
                    await reply_premium(update.message, f"✅ User `{target_id}` updated. New Balance: `{new_balance}`")
            except Exception:
                await reply_premium(update.message, "❌ Use format: `USER_ID AMOUNT`")

        elif action == "broadcast":
            def get_all_uids():
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT user_id FROM users")
                uids = [row[0] for row in c.fetchall()]
                conn.close()
                return uids
            users = await asyncio.to_thread(get_all_uids)
            sent = 0
            for uid in users:
                try:
                    await send_premium(context.bot, uid, f"╭─ *📢 ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ 📢*\n│\n│ {text}\n╰───────────────────", disable_web_page_preview=True)
                    sent += 1
                except Exception:
                    pass
            await reply_premium(update.message, f"✅ Broadcast delivered to `{sent}` users.", reply_markup=admin_kb)

# ----------------- ERROR HANDLER -----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

# ----------------- MAIN RUNNER (OPTIMIZED FOR 10-15+ PARALLEL USERS) -----------------
if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)      # Enables true multi-threaded parallel handling
        .connection_pool_size(30)      # Allows multiple outgoing connections simultaneously
        .connect_timeout(10.0)         # Fast 10s fallback instead of freezing for 60s
        .read_timeout(10.0)
        .write_timeout(10.0)
        .pool_timeout(5.0)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(ChatJoinRequestHandler(track_join_request))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_error_handler(error_handler)

    logging.info("Optimized high-concurrency bot running 24/7...")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
