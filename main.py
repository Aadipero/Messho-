import os
import io
import sqlite3
import logging
import json
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

# GitHub Pages Verification URL
VERIFY_WEBAPP_URL = "https://aadipero.github.io/device-verify/"

# Confetti / Party Popper Effect ID
MESSAGE_CONFETTI_EFFECT_ID = "5046509860389126442"

CUSTOM_EMOJI_IDS = {
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
    return await message.reply_text(final_text, entities=entities or None, **kwargs)

async def send_premium(bot, chat_id, text, **kwargs):
    final_text, entities = parse_premium_markdown(text)
    kwargs.pop("parse_mode", None)
    return await bot.send_message(chat_id=chat_id, text=final_text, entities=entities or None, **kwargs)

async def edit_premium(message, text, **kwargs):
    final_text, entities = parse_premium_markdown(text)
    kwargs.pop("parse_mode", None)
    try:
        return await message.edit_text(final_text, entities=entities or None, **kwargs)
    except Exception as e:
        if "Message is not modified" in str(e):
            return message
        return await message.reply_text(final_text, entities=entities or None, **kwargs)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ----------------- DATABASE (PERSISTENT MOUNT) -----------------
DATA_DIR = os.getenv("DATA_DIR", "/data")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "bot_data.db")
except Exception:
    DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

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
    c.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('points_meesho', 3)")
    conn.commit()
    conn.close()

init_db()

def get_required_points():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM bot_settings WHERE key = 'points_meesho'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 3

def update_required_points(val: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('points_meesho', ?)", (val,))
    conn.commit()
    conn.close()

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

def get_all_channels():
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

def add_channel_config(ch_type: str, name: str, chat_id: str, url: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO channels_config_v2 (type, name, chat_id, url) 
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET type=excluded.type, name=excluded.name, url=excluded.url
    """, (ch_type, name, chat_id.strip(), url.strip()))
    conn.commit()
    conn.close()

def delete_channel_by_id(db_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM channels_config_v2 WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()

# ----------------- KEYBOARDS -----------------
def get_join_keyboard():
    keyboard = []
    row = []
    channels = get_all_channels()
    for ch in channels:
        row.append(premium_button(ch["name"], None, "primary", "channel", url=ch["url"]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([premium_button("CHECK JOINED", "check_join", "success", "check")])
    return InlineKeyboardMarkup(keyboard)

def get_verify_keyboard(bot_username: str = ""):
    clean_url = VERIFY_WEBAPP_URL
    if bot_username:
        sep = "&" if "?" in clean_url else "?"
        clean_url = f"{clean_url}{sep}bot={bot_username}"
    return InlineKeyboardMarkup([
        [premium_button("🛡️ Verify Device Now", None, "primary", "check", web_app=WebAppInfo(url=clean_url))]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            premium_button("My Referral Link", "ref_link", "primary", "ref_link"),
            premium_button("My Stats & Leaderboard", "my_stats", "success", "stats"),
        ],
        [
            premium_button("Withdraw Meesho JSON", "withdraw_menu", "success", "claim"),
            premium_button("My Referrals", "my_referrals", "primary", "referrals"),
        ],
        [
            premium_button("Live Proofs Channel", None, "primary", "channel", url=PROOF_CHANNEL_URL)
        ]
    ])

def get_admin_keyboard():
    pts = get_required_points()
    return InlineKeyboardMarkup([
        [
            premium_button("➕ Add Meesho JSONs (Bulk)", "admin_bulk_files", "primary", "admin_add"),
        ],
        [
            premium_button(f"⚙️ Min Points ({pts}p)", "admin_edit_pts", "primary", "edit"),
            premium_button("📦 Stock Status", "admin_stock", "success", "stock"),
        ],
        [
            premium_button("📢 Manage Channels", "admin_channel_menu", "primary", "channel"),
            premium_button("👥 User Stats", "admin_users", "primary", "users"),
        ],
        [
            premium_button("➕ Add User Points", "admin_add_user_points", "primary", "admin_add"),
            premium_button("➖ Deduct User Points", "admin_deduct_user_points", "danger", "edit"),
        ],
        [
            premium_button("📢 Broadcast Message", "admin_broadcast_prompt", "primary", "broadcast"),
            premium_button("🔄 Refresh Panel", "admin_refresh", None, "repeat"),
        ]
    ])

def get_admin_channel_keyboard():
    channels = get_all_channels()
    kb = [
        [premium_button("➕ Add Public Channel", "admin_add_public", "primary", "plus")],
        [premium_button("➕ Add Private Channel", "admin_add_private", "primary", "plus")],
        [premium_button("➕ Add Request Channel", "admin_add_request", "primary", "plus")]
    ]
    if channels:
        for ch in channels:
            kb.append([premium_button(f"❌ Delete {ch['name']} ({ch['type'].title()})", f"admin_del_{ch['db_id']}", "danger", "cross")])
    kb.append([premium_button("🔙 Back to Admin", "admin_back_to_panel")])
    return InlineKeyboardMarkup(kb)

# ----------------- TRACKING & HELPERS -----------------
async def track_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if req:
        u_id = req.user_chat_id
        c_id = str(req.chat.id)
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO join_requests (user_id, chat_id) VALUES (?, ?)", (u_id, c_id))
        conn.commit()
        conn.close()

async def get_unjoined_channels(user_id: int, bot):
    channels = get_all_channels()
    if not channels:
        return []

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT chat_id FROM join_requests WHERE user_id = ?", (user_id,))
    requested_chats = {str(row[0]) for row in c.fetchall()}
    conn.close()

    unjoined = []
    for ch in channels:
        target_id = ch["id"]
        str_id = str(target_id)
        raw_str = ch["raw_id"]

        if str_id in requested_chats or raw_str in requested_chats:
            continue

        try:
            member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status in ["member", "administrator", "creator", "restricted"]:
                continue
            else:
                unjoined.append(ch)
        except Exception:
            if str_id in requested_chats or raw_str in requested_chats:
                continue
            unjoined.append(ch)
            
    return unjoined

def is_device_verified(user_id: int) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT device_id FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

async def send_welcome_dashboard(bot, user_id: int):
    pts = get_required_points()
    welcome_text = (
        "✨ *WELCOME TO MEESHO AUTO SYSTEM* ✨\n\n"
        "• *Instant Auto Dispatch:* Active 24/7\n"
        "• *Free JSON Retrieval:* Seamless delivery\n"
        f"• *Redeem Requirement:* `{pts} Verified Referrals`\n"
        f"• *Live Proofs Channel:* Synchronized ({PROOF_CHANNEL})\n\n"
        "Select an option from the menu below:"
    )
    await send_premium(
        bot,
        user_id,
        welcome_text,
        reply_markup=get_main_keyboard(),
        message_effect_id=MESSAGE_CONFETTI_EFFECT_ID,
        disable_web_page_preview=True
    )

# ----------------- DIRECT WEBAPP VERIFICATION HANDLER -----------------
async def internal_verify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    
    if text.startswith("/verify_"):
        parts = text.split("_")
        if len(parts) >= 4:
            user_id = int(parts[1])
            device_id = parts[2]
            ip_address = parts[3].replace("-", ".")

            try:
                await update.message.delete()
            except Exception:
                pass

            conn = get_db()
            c = conn.cursor()

            # Anti-fraud check
            c.execute(
                "SELECT user_id FROM users WHERE (device_id = ? OR (ip_address = ? AND ip_address IS NOT NULL)) AND user_id != ?", 
                (device_id, ip_address, user_id)
            )
            fraud = c.fetchone()
            if fraud:
                conn.close()
                await send_premium(context.bot, user_id, "🛑 *SECURITY ALERT*\n\nThis device or IP is already registered with another account!")
                return

            c.execute("SELECT referrer_id, device_id FROM users WHERE user_id = ?", (user_id,))
            u = c.fetchone()
            ref_id = None
            new_balance = 0

            if u:
                if not u[1]:
                    ref_id = u[0]
                    c.execute("UPDATE users SET device_id = ?, ip_address = ? WHERE user_id = ?", (device_id, ip_address, user_id))
                    if ref_id:
                        c.execute("UPDATE users SET credits = credits + 1 WHERE user_id = ?", (ref_id,))
                        c.execute("SELECT credits FROM users WHERE user_id = ?", (ref_id,))
                        bal_row = c.fetchone()
                        new_balance = bal_row[0] if bal_row else 1
                    conn.commit()
            else:
                c.execute("INSERT INTO users (user_id, referrer_id, credits, claimed_count, device_id, ip_address, last_start_time) VALUES (?, NULL, 0, 0, ?, ?, NULL)", (user_id, device_id, ip_address))
                conn.commit()
            conn.close()

            await send_premium(context.bot, user_id, f"✅ *DEVICE & IP VERIFIED!*\n\nYour account is now activated. IP: `{ip_address}`")
            await send_welcome_dashboard(context.bot, user_id)

            if ref_id:
                try:
                    masked = str(user_id)[:4] + "****" + str(user_id)[-2:]
                    alert = (
                        "🎉 *REFERRAL REWARD RECEIVED!*\n\n"
                        f"👤 *New Verified User:* `{masked}`\n"
                        f"💰 *Earned:* `+1 Point`\n"
                        f"📊 *Current Balance:* `{new_balance} Points`\n\n"
                        "🚀 *Keep inviting friends to unlock Meesho Free JSON!*"
                    )
                    await send_premium(context.bot, ref_id, alert)
                except Exception:
                    pass

# ----------------- WEBAPP DATA RECEIVER -----------------
async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.web_app_data:
        return
    
    sender_id = update.effective_user.id
    raw_json = update.message.web_app_data.data

    try:
        data = json.loads(raw_json)
    except Exception:
        return

    if data.get("action") == "device_ip_verified":
        device_id = data.get("device_id")
        user_ip = data.get("ip")

        conn = get_db()
        c = conn.cursor()

        c.execute(
            "SELECT user_id FROM users WHERE (device_id = ? OR (ip_address = ? AND ip_address IS NOT NULL)) AND user_id != ?", 
            (device_id, user_ip, sender_id)
        )
        existing_fraud = c.fetchone()

        if existing_fraud:
            conn.close()
            await reply_premium(update.message, "🛑 *SECURITY ALERT*\n\nThis device or IP address is already registered with another account!")
            return

        c.execute("SELECT referrer_id, device_id FROM users WHERE user_id = ?", (sender_id,))
        u = c.fetchone()

        referrer_id = None
        new_balance = 0

        if u and not u[1]:
            referrer_id = u[0]
            c.execute("UPDATE users SET device_id = ?, ip_address = ? WHERE user_id = ?", (device_id, user_ip, sender_id))
            if referrer_id:
                c.execute("UPDATE users SET credits = credits + 1 WHERE user_id = ?", (referrer_id,))
                c.execute("SELECT credits FROM users WHERE user_id = ?", (referrer_id,))
                bal_row = c.fetchone()
                new_balance = bal_row[0] if bal_row else 1
            conn.commit()
        conn.close()

        await reply_premium(update.message, f"✅ *DEVICE & IP VERIFIED!*\n\nYour account is now activated. IP: `{user_ip}`")
        await send_welcome_dashboard(context.bot, sender_id)

        if referrer_id:
            try:
                masked_new_user = str(sender_id)[:4] + "****" + str(sender_id)[-2:]
                alert_text = (
                    "🎉 *REFERRAL REWARD RECEIVED!*\n\n"
                    f"👤 *New Verified User:* `{masked_new_user}`\n"
                    f"💰 *Earned:* `+1 Point`\n"
                    f"📊 *Current Balance:* `{new_balance} Points`\n\n"
                    "🚀 *Keep inviting friends to unlock Meesho Free JSON!*"
                )
                await send_premium(context.bot, referrer_id, alert_text)
            except Exception as e:
                logging.error(f"Error alerting referrer: {e}")

# ----------------- COMMAND & CALLBACK HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    args = context.args
    bot_info = await context.bot.get_me()

    # Deep-link Direct Redirect handler (/start v_DEVICEID)
    if args and args[0].startswith("v_"):
        device_id = args[0].replace("v_", "")
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT user_id FROM users WHERE device_id = ? AND user_id != ?", (device_id, user_id))
        duplicate = c.fetchone()
        if duplicate:
            conn.close()
            await reply_premium(update.message, "🛑 *SECURITY ALERT*\n\nThis device is already linked with another account!")
            return

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
            c.execute("INSERT INTO users (user_id, referrer_id, credits, claimed_count, device_id, ip_address, last_start_time) VALUES (?, NULL, 0, 0, ?, NULL, NULL)", (user_id, device_id))
            conn.commit()
        conn.close()

        await reply_premium(update.message, "✅ *DEVICE VERIFIED SUCCESSFULLY!*\nYour account is now activated.")
        await send_welcome_dashboard(context.bot, user_id)

        if ref_id:
            try:
                masked = str(user_id)[:4] + "****" + str(user_id)[-2:]
                alert_text = (
                    "🎉 *REFERRAL REWARD RECEIVED!*\n\n"
                    f"👤 *New Verified User:* `{masked}`\n"
                    f"💰 *Earned:* `+1 Point`\n"
                    f"📊 *Current Balance:* `{new_balance} Points`\n\n"
                    "🚀 *Keep inviting friends to unlock Meesho Free JSON!*"
                )
                await send_premium(context.bot, ref_id, alert_text)
            except Exception as e:
                logging.error(f"Error alerting referrer: {e}")
        return

    # Normal registration flow
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        referrer = None
        if args and args[0].isdigit():
            ref_candidate = int(args[0])
            if ref_candidate != user_id:
                referrer = ref_candidate
        c.execute("INSERT INTO users (user_id, referrer_id, credits, claimed_count, device_id, ip_address, last_start_time) VALUES (?, ?, 0, 0, NULL, NULL, NULL)", (user_id, referrer))
        conn.commit()
    conn.close()

    unjoined = await get_unjoined_channels(user_id, context.bot)
    if unjoined:
        missing_names = "\n".join([f"• *{ch['name']}*" for ch in unjoined])
        text = (
            "🛑 *CHANNEL MEMBERSHIP REQUIRED!*\n\n"
            f"⚠️ *Join our official channels to continue:*\n{missing_names}\n\n"
            "👉 *Tap buttons below, join, then click CHECK JOINED.*"
        )
        await reply_premium(update.message, text, reply_markup=get_join_keyboard(), disable_web_page_preview=True)
        return

    if not is_device_verified(user_id):
        text = (
            "🔒 *ACCOUNT VERIFICATION REQUIRED*\n\n"
            "⚠️ *Please complete 1-tap device & IP verification:*"
        )
        await reply_premium(update.message, text, reply_markup=get_verify_keyboard(bot_info.username))
        return

    await send_welcome_dashboard(context.bot, user_id)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_user.id != ADMIN_ID:
        return
    pts = get_required_points()
    await reply_premium(
        update.message,
        f"⚙️ *ADMIN CONTROL PANEL*\n\n"
        f"📦 *Product:* `Meesho Free JSON`\n"
        f"🎯 *Points Needed:* `{pts} Points`\n\n"
        f"Select an action below:",
        reply_markup=get_admin_keyboard()
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    pts = get_required_points()
    bot_info = await context.bot.get_me()

    if data == "check_join":
        unjoined = await get_unjoined_channels(user_id, context.bot)
        if not unjoined:
            await query.answer("✅ Verified Successfully!", show_alert=False)
            if not is_device_verified(user_id):
                text = "🔒 *FINAL STEP: VERIFY YOUR ACCOUNT*\n\n*Tap below for verification:*"
                await edit_premium(query.message, text, reply_markup=get_verify_keyboard(bot_info.username))
            else:
                await send_welcome_dashboard(context.bot, user_id)
        else:
            names = ", ".join([ch["name"] for ch in unjoined])
            await query.answer(f"⚠️ Action Required!\nPlease join/send request to:\n{names}", show_alert=True)
            missing_names = "\n".join([f"• *{ch['name']}*" for ch in unjoined])
            text = (
                "🛑 *CHANNEL MEMBERSHIP REQUIRED!*\n\n"
                f"⚠️ *Join our official channels:*\n{missing_names}\n\n"
                "👉 *Tap buttons below and click CHECK JOINED.*"
            )
            try:
                await edit_premium(query.message, text, reply_markup=get_join_keyboard(), disable_web_page_preview=True)
            except Exception:
                pass
        return

    await query.answer()

    if data == "ref_link":
        link = f"https://t.me/{bot_info.username}?start={user_id}"
        ref_text = (
            f"🔗 *YOUR EXCLUSIVE REFERRAL LINK:*\n`{link}`\n\n"
            f"🎁 *REWARD SCHEME:*\n"
            f"• *1 Verified Referral* = `+1 Point`\n"
            f"• *{pts} Points* = `1 Meesho Free JSON File`\n\n"
            f"🚀 *Share this link in Telegram channels and groups!*"
        )
        await reply_premium(query.message, ref_text, disable_web_page_preview=True)

    elif data == "my_stats":
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
            FROM users
            WHERE referrer_id IS NOT NULL AND device_id IS NOT NULL
            GROUP BY referrer_id
            ORDER BY total_refs DESC
            LIMIT 3
        """)
        top_users = c.fetchall()
        conn.close()

        leaderboard_str = ""
        rank_emojis = ["🥇", "🥈", "🥉"]
        if top_users:
            for idx, (top_id, count) in enumerate(top_users):
                medal = rank_emojis[idx] if idx < len(rank_emojis) else f"{idx+1}."
                leaderboard_str += f"{medal} *User:* `{top_id}` ➔ *{count} Refs*\n"
        else:
            leaderboard_str = "No referrals yet!\n"

        stats_text = (
            f"📊 *ACCOUNT OVERVIEW:*\n\n"
            f"💰 *Available Points:* `{credits}`\n"
            f"👥 *Verified Referrals:* `{my_refs}`\n"
            f"🎁 *Total Files Claimed:* `{claimed}`\n\n"
            f"🎯 *REDEEM SCHEME:*\n"
            f"• `{pts} Points` ➔ *1 Meesho Free JSON*\n\n"
            f"🏆 *TOP REFERRERS:*\n"
            f"{leaderboard_str}"
        )
        await reply_premium(query.message, stats_text)

    elif data == "my_referrals":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND device_id IS NOT NULL", (user_id,))
        count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND device_id IS NULL", (user_id,))
        pending = c.fetchone()[0]
        conn.close()

        refs_text = (
            f"👥 *YOUR REFERRAL NETWORK:*\n\n"
            f"✅ *Verified Referrals:* `{count} Users` (+{count} Points earned)\n"
            f"⏳ *Pending Verification:* `{pending} Users`\n\n"
            f"💡 *Points are credited once users complete device check.*"
        )
        await reply_premium(query.message, refs_text)

    elif data == "withdraw_menu":
        withdraw_text = (
            "🎁 *WITHDRAW MEESHO FREE JSON*\n\n"
            f"• Cost: `{pts} Points`\n"
            f"• Instant .txt file dispatch\n\n"
            "Press Claim to proceed:"
        )
        kb = InlineKeyboardMarkup([
            [premium_button(f"📥 Claim Meesho JSON ({pts} Pts)", "confirm_claim_file", "success", "claim")],
            [premium_button("🔙 Back to Main", "back_to_main")]
        ])
        await edit_premium(query.message, withdraw_text, reply_markup=kb)

    elif data == "back_to_main":
        await edit_premium(
            query.message,
            "✨ *MAIN DASHBOARD*\n\nSelect an option from below:",
            reply_markup=get_main_keyboard(),
            disable_web_page_preview=True
        )

    elif data == "confirm_claim_file":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        user_credits = row[0] if row else 0

        if user_credits < pts:
            conn.close()
            await query.answer(f"❌ Insufficient Points! You have {user_credits}, required {pts}.", show_alert=True)
            return

        c.execute("SELECT id, content FROM meesho_files WHERE is_claimed = 0 LIMIT 1")
        file_item = c.fetchone()

        if not file_item:
            conn.close()
            await query.answer("⚠️ Out of Stock! Adding soon.", show_alert=True)
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *STOCK OVER*\nUser `{user_id}` attempted to withdraw Meesho JSON.", parse_mode="Markdown")
            except Exception:
                pass
            await reply_premium(
                query.message, 
                f"📦 *CURRENTLY OUT OF STOCK!*\n\nMeesho Free JSON files are exhausted right now.\nKeep an eye on the proofs channel for restock alerts!",
                reply_markup=InlineKeyboardMarkup([
                    [premium_button("📢 Live Proofs Channel", url=PROOF_CHANNEL_URL)],
                    [premium_button("🔙 Back to Dashboard", "back_to_main")]
                ]),
                disable_web_page_preview=True
            )
            return

        f_id, f_content = file_item
        c.execute("UPDATE meesho_files SET is_claimed = 1 WHERE id = ?", (f_id,))
        c.execute("UPDATE users SET credits = credits - ?, claimed_count = claimed_count + 1 WHERE user_id = ?", (pts, user_id))
        c.execute("INSERT INTO file_claims (user_id, file_id) VALUES (?, ?)", (user_id, f_id))
        conn.commit()
        conn.close()

        file_data = io.BytesIO(f_content.encode("utf-8"))
        file_data.name = f"meesho_free_json_{user_id}_{f_id}.txt"

        caption = (
            f"🎉 *CLAIM SUCCESSFUL!*\n\n"
            f"📦 *Product:* `Meesho Free JSON`\n"
            f"💰 *Deducted:* `{pts} Points`\n\n"
            f"📢 *Check Proof Here:* {PROOF_CHANNEL}"
        )
        
        await context.bot.send_document(
            chat_id=user_id,
            document=file_data,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [premium_button("📢 Check Out Proofs Here", url=PROOF_CHANNEL_URL)],
                [premium_button("🔙 Main Menu", "back_to_main")]
            ])
        )

        try:
            masked_uid = str(user_id)[:4] + "****" + str(user_id)[-2:]
            proof_msg = (
                f"🎉 *NEW DISPATCH PROOF!*\n"
                f"👤 *User:* `{masked_uid}`\n"
                f"📦 *Item:* `Meesho Free JSON File`\n"
                f"✅ *Status:* Delivered 24/7\n"
                f"🤖 *Bot:* @{bot_info.username}"
            )
            await send_premium(context.bot, PROOF_CHANNEL, proof_msg, disable_web_page_preview=True)
        except Exception:
            pass

    elif data == "admin_stock":
        if user_id != ADMIN_ID:
            return
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM meesho_files WHERE is_claimed = 0")
        stock = c.fetchone()[0]
        conn.close()
        await reply_premium(query.message, f"📦 *STOCK STATUS*\n\n• Available Meesho JSON Files: `{stock}`")

    elif data == "admin_users":
        if user_id != ADMIN_ID:
            return
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE device_id IS NOT NULL")
        verified_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM file_claims")
        total_claims = c.fetchone()[0]
        conn.close()
        await reply_premium(query.message, f"👥 *USER STATS*\n\n• Total Users: `{total_users}`\n• Verified: `{verified_users}`\n• Files Claimed: `{total_claims}`")

    elif data == "admin_bulk_files":
        if user_id != ADMIN_ID:
            return
        context.user_data["admin_action"] = "bulk_add_files"
        instructions = (
            "➕ *BULK ADD MEESHO JSON FILES*\n\n"
            "Paste multiple JSON contents separated by `---` line:\n\n"
            "`{\"token\": \"abc1\"}`\n"
            "`---`\n"
            "`{\"token\": \"abc2\"}`\n\n"
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
        channels = get_all_channels()
        info_lines = "\n".join([f"• *{ch['type'].title()}:* {ch['name']} (`{ch['id']}`)" for ch in channels]) if channels else "No channels configured."
        await edit_premium(
            query.message,
            f"📢 *CHANNEL MANAGEMENT*\n\nTotal: `{len(channels)}`\n\n{info_lines}\n\nAdd/Delete below:",
            reply_markup=get_admin_channel_keyboard(),
            disable_web_page_preview=True
        )

    elif data in ["admin_add_public", "admin_add_private", "admin_add_request"]:
        if user_id != ADMIN_ID:
            return
        ch_type = data.replace("admin_add_", "")
        context.user_data["admin_action"] = f"add_channel_{ch_type}"
        await reply_premium(
            query.message,
            f"⚙️ *ADD CHANNEL*\nFormat: `Name | Chat ID | URL`\nExample: `Main | -100123456789 | https://t.me/+xyz`"
        )

    elif data.startswith("admin_del_"):
        if user_id != ADMIN_ID:
            return
        db_id = int(data.replace("admin_del_", ""))
        delete_channel_by_id(db_id)
        await query.answer("✅ Channel Deleted!", show_alert=True)
        channels = get_all_channels()
        info_lines = "\n".join([f"• *{ch['type'].title()}:* {ch['name']} (`{ch['id']}`)" for ch in channels]) if channels else "No channels configured."
        await edit_premium(
            query.message,
            f"📢 *CHANNEL MANAGEMENT*\n\nTotal: `{len(channels)}`\n\n{info_lines}\n\nAdd/Delete below:",
            reply_markup=get_admin_channel_keyboard(),
            disable_web_page_preview=True
        )

    elif data == "admin_back_to_panel":
        if user_id != ADMIN_ID:
            return
        await edit_premium(
            query.message,
            f"⚙️ *ADMIN CONTROL PANEL*\n\n• Meesho JSON Points: `{pts} Points`",
            reply_markup=get_admin_keyboard()
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
        await edit_premium(query.message, f"⚙️ *ADMIN PANEL (Refreshed)*\n• Points: `{pts}p`", reply_markup=get_admin_keyboard())

# ----------------- ADMIN INPUT HANDLER -----------------
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id == ADMIN_ID and "admin_action" in context.user_data:
        action = context.user_data.pop("admin_action")
        
        if action == "bulk_add_files":
            raw_entries = text.split("---")
            entries = [e.strip() for e in raw_entries if e.strip()]
            conn = get_db()
            c = conn.cursor()
            added = 0
            for item in entries:
                c.execute("INSERT INTO meesho_files (content) VALUES (?)", (item,))
                added += 1
            conn.commit()
            conn.close()
            await reply_premium(update.message, f"✅ Successfully added `{added}` individual Meesho JSON files!", reply_markup=get_admin_keyboard())

        elif action == "edit_points":
            if not text.isdigit() or int(text) <= 0:
                await reply_premium(update.message, "❌ Invalid point value.")
                return
            val = int(text)
            update_required_points(val)
            await reply_premium(update.message, f"✅ Updated to `{val} Points` required.", reply_markup=get_admin_keyboard())

        elif action.startswith("add_channel_"):
            ch_type = action.replace("add_channel_", "")
            parts = [p.strip() for p in text.split("|")]
            if len(parts) != 3:
                await reply_premium(update.message, "❌ Use: `Name | Chat ID | URL`", reply_markup=get_admin_channel_keyboard())
                return
            add_channel_config(ch_type, parts[0], parts[1], parts[2])
            await reply_premium(update.message, "✅ Channel Added Successfully!", reply_markup=get_admin_keyboard())

        elif action in ["admin_add_user_points", "admin_deduct_user_points"]:
            try:
                parts = text.strip().split()
                target_id = int(parts[0])
                amount = int(parts[1])
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT credits FROM users WHERE user_id = ?", (target_id,))
                row = c.fetchone()
                if not row:
                    conn.close()
                    await reply_premium(update.message, f"❌ User `{target_id}` not found.")
                    return
                old_p = int(row[0] or 0)
                new_p = old_p + amount if action == "admin_add_user_points" else max(0, old_p - amount)
                c.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_p, target_id))
                conn.commit()
                conn.close()
                await reply_premium(update.message, f"✅ User `{target_id}` updated. New Balance: `{new_p}`")
            except Exception:
                await reply_premium(update.message, "❌ Use format: `USER_ID AMOUNT`")

        elif action == "broadcast":
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()
            sent = 0
            for (uid,) in users:
                try:
                    await send_premium(context.bot, uid, f"📢 *ANNOUNCEMENT:*\n\n{text}", disable_web_page_preview=True)
                    sent += 1
                except Exception:
                    pass
            await reply_premium(update.message, f"✅ Broadcast sent to `{sent}` users.", reply_markup=get_admin_keyboard())

# ----------------- MAIN RUNNER -----------------
if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(60.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(60.0)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(ChatJoinRequestHandler(track_join_request))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Direct internal command trigger
    application.add_handler(MessageHandler(filters.Regex(r"^/verify_"), internal_verify_handler))
    
    # Native Telegram WebApp Data Handler
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    # Admin text message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    logging.info("Bot is active and running...")
    application.run_polling(drop_pending_updates=True)
