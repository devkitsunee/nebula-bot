import discord
from discord.ext import commands, tasks
import sqlite3
import time
import os

from keep_alive import keep_alive
keep_alive()

# ================= TOKEN =================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN not found in environment variables")

# ================= CONFIG =================
PREFIX = "+"
# =========================================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ================= DATABASE =================
db = sqlite3.connect("data.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    last_msg INTEGER DEFAULT 0,
    daily INTEGER DEFAULT 0,
    weekly INTEGER DEFAULT 0,
    monthly INTEGER DEFAULT 0,
    in_vc INTEGER DEFAULT 0
)
""")
db.commit()

# ================= HELPERS =================
def ensure_user(uid):
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, points) VALUES (?, 0)",
        (uid,)
    )
    db.commit()

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game("© Nebula AI"))
    vc_reward_loop.start()

# ================= MESSAGE → POINTS =================
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    ensure_user(message.author.id)

    cur.execute(
        "SELECT last_msg FROM users WHERE user_id=?",
        (message.author.id,)
    )
    last = cur.fetchone()[0]
    now = int(time.time())

    if now - last >= 5:
        cur.execute(
            "UPDATE users SET points = points + 10, last_msg = ? WHERE user_id = ?",
            (now, message.author.id)
        )
        db.commit()

    await bot.process_commands(message)

# ================= VC TRACKING =================
@bot.event
async def on_voice_state_update(member, before, after):
    ensure_user(member.id)

    if after.channel and not after.self_mute and not after.self_deaf:
        cur.execute("UPDATE users SET in_vc = 1 WHERE user_id = ?", (member.id,))
    else:
        cur.execute("UPDATE users SET in_vc = 0 WHERE user_id = ?", (member.id,))
    db.commit()

@tasks.loop(seconds=60)
async def vc_reward_loop():
    cur.execute("SELECT user_id FROM users WHERE in_vc = 1")
    users = cur.fetchall()

    for (uid,) in users:
        cur.execute(
            "UPDATE users SET points = points + 100 WHERE user_id = ?",
            (uid,)
        )

    if users:
        db.commit()

# ================= HELP =================
@bot.command()
async def help(ctx):
    await ctx.send(
        "**━━━━━━━━━━━━━━━━━━━━━━**\n"
        "**📘 COMMANDS**\n"
        "**━━━━━━━━━━━━━━━━━━━━━━**\n\n"
        "> **+bal** | check balance ...\n"
        "> **+give @user <amount>** | send money ...\n"
        "> **+daily** | **+weekly** | **+monthly** ...\n"
        "> **+lb** | leaderboard ...\n"
        "> **+s <type> <text>** | bot status ...\n\n"
        "-# **Nebula AI**"
    )

# ================= BAL =================
@bot.command()
async def bal(ctx):
    ensure_user(ctx.author.id)
    cur.execute(
        "SELECT points FROM users WHERE user_id=?",
        (ctx.author.id,)
    )
    pts = cur.fetchone()[0]
    await ctx.send(
        f"💰 **{ctx.author.display_name}**\n"
        f"Balance: **{pts:,}**"
    )

# ================= GIVE =================
@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    ensure_user(ctx.author.id)
    ensure_user(member.id)

    if amount <= 0:
        return await ctx.send("❌ Invalid amount.")

    cur.execute(
        "SELECT points FROM users WHERE user_id=?",
        (ctx.author.id,)
    )
    bal = cur.fetchone()[0]

    if bal < amount:
        return await ctx.send("❌ Not enough points.")

    cur.execute(
        "UPDATE users SET points = points - ? WHERE user_id=?",
        (amount, ctx.author.id)
    )
    cur.execute(
        "UPDATE users SET points = points + ? WHERE user_id=?",
        (amount, member.id)
    )
    db.commit()

    await ctx.send(
        f"💸 **{ctx.author.display_name}** → **{member.display_name}**\n"
        f"**{amount:,} points**"
    )

# ================= CLAIMS =================
def can_claim(last, cd):
    return int(time.time()) - last >= cd

@bot.command()
async def daily(ctx):
    ensure_user(ctx.author.id)
    cur.execute("SELECT daily FROM users WHERE user_id=?", (ctx.author.id,))
    last = cur.fetchone()[0]

    if not can_claim(last, 86400):
        return await ctx.send("⏳ Already claimed.")

    cur.execute(
        "UPDATE users SET points = points + 2000, daily=? WHERE user_id=?",
        (int(time.time()), ctx.author.id)
    )
    db.commit()
    await ctx.send("💰 **+2,000 points**")

@bot.command()
async def weekly(ctx):
    ensure_user(ctx.author.id)
    cur.execute("SELECT weekly FROM users WHERE user_id=?", (ctx.author.id,))
    last = cur.fetchone()[0]

    if not can_claim(last, 604800):
        return await ctx.send("⏳ Already claimed.")

    cur.execute(
        "UPDATE users SET points = points + 10000, weekly=? WHERE user_id=?",
        (int(time.time()), ctx.author.id)
    )
    db.commit()
    await ctx.send("💎 **+10,000 points**")

@bot.command()
async def monthly(ctx):
    ensure_user(ctx.author.id)
    cur.execute("SELECT monthly FROM users WHERE user_id=?", (ctx.author.id,))
    last = cur.fetchone()[0]

    if not can_claim(last, 2592000):
        return await ctx.send("⏳ Already claimed.")

    cur.execute(
        "UPDATE users SET points = points + 50000, monthly=? WHERE user_id=?",
        (int(time.time()), ctx.author.id)
    )
    db.commit()
    await ctx.send("🌟 **+50,000 points**")

# ================= STATUS =================
@bot.command()
async def s(ctx, mode: str, *, text: str):
    mode = mode.lower()

    if mode == "playing":
        await bot.change_presence(activity=discord.Game(text))
    elif mode == "listening":
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.listening, name=text
        ))
    elif mode == "watching":
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name=text
        ))
    elif mode == "streaming":
        parts = text.split()
        if len(parts) < 2:
            return await ctx.send("❌ Usage: +s streaming <text> <link>")
        await bot.change_presence(activity=discord.Streaming(
            name=" ".join(parts[:-1]),
            url=parts[-1]
        ))
    else:
        return await ctx.send("❌ Invalid status type.")

    await ctx.send("✅ **Status updated**")

# ================= LEADERBOARD =================
@bot.command()
async def lb(ctx):
    cur.execute(
        "SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10"
    )
    rows = cur.fetchall()

    medals = ["🥇", "🥈", "🥉"]
    text = "**🏆 LEADERBOARD**\n━━━━━━━━━━━━━━━━━━\n"

    for i, (uid, pts) in enumerate(rows):
        rank = medals[i] if i < 3 else f"{i+1}️⃣"
        text += f"{rank} <@{uid}> — **{pts:,}**\n"

    await ctx.send(
        text,
        allowed_mentions=discord.AllowedMentions.none()
    )

# ================= RUN =================
bot.run(TOKEN)
