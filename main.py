import discord
from discord import app_commands
from discord.ext import commands
import datetime
import requests
import re
import json
import os
import random
import asyncio

# --- CONFIGURATION & ACTIVITY PERSISTENCE ---
CONFIG_FILE = "bot_config.json"

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"log_channel_id": None, "activity": {}}

# --- BLACKJACK UI ---
class BlackjackView(discord.ui.View):
    def __init__(self, user, player_hand, dealer_hand, deck):
        super().__init__(timeout=60)
        self.user = user
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.deck = deck

    def get_score(self, hand):
        score, aces = 0, 0
        for card in hand:
            val = card.split()[0]
            if val in ['J', 'Q', 'K']: score += 10
            elif val == 'A': score += 11; aces += 1
            else: score += int(val)
        while score > 21 and aces: score -= 10; aces -= 1
        return score

    def create_embed(self, finished=False):
        p_s, d_s = self.get_score(self.player_hand), self.get_score(self.dealer_hand)
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.blue())
        embed.add_field(name="Your Hand", value=f"{', '.join(self.player_hand)}\nScore: **{p_s}**")
        if finished:
            embed.add_field(name="Dealer's Hand", value=f"{', '.join(self.dealer_hand)}\nScore: **{d_s}**")
            if p_s > 21: embed.description = "❌ **Bust! You lose.**"
            elif d_s > 21 or p_s > d_s: embed.description = "✅ **You win!**"
            elif p_s < d_s: embed.description = "❌ **Dealer wins.**"
            else: embed.description = "🤝 **Tie.**"
        else:
            embed.add_field(name="Dealer's Hand", value=f"{self.dealer_hand[0]}, ❓")
        return embed

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user: return
        self.player_hand.append(self.deck.pop())
        if self.get_score(self.player_hand) >= 21: await self.stand.callback(interaction)
        else: await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user: return
        while self.get_score(self.dealer_hand) < 17: self.dealer_hand.append(self.deck.pop())
        await interaction.response.edit_message(embed=self.create_embed(finished=True), view=None)

# --- BOT CLASS ---
class JimBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.config = load_config()

    async def setup_hook(self):
        print("Syncing slash commands...")
        await self.tree.sync()
        print("Slash commands synced!")

bot = JimBot()

# --- EVENTS ---

@bot.event
async def on_ready():
    print(f"--- BOT IS ONLINE ---")
    print(f"Logged in as: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot: return
    uid = str(message.author.id)
    activity = bot.config.get("activity", {})
    activity[uid] = activity.get(uid, 0) + 1
    bot.config["activity"] = activity
    save_config(bot.config)
    await bot.process_commands(message)

@bot.event
async def on_thread_create(thread):
    chan_id = bot.config.get("log_channel_id")
    if chan_id:
        log_channel = bot.get_channel(chan_id)
        if log_channel:
            await log_channel.send(embed=discord.Embed(title="📝 New Forum Post", description=f"[{thread.name}]({thread.jump_url})"))

# --- COMMANDS ---

@bot.tree.command(name="gambling_machine", description="Animated Slot Machine")
async def gambling_machine(interaction: discord.Interaction):
    emojis = ["🍎", "🍇", "💎", "7️⃣", "🍒", "🍋"]
    
    # Send the initial "Spinning" message
    embed = discord.Embed(title="🎰 Spinning...", description="**[ 🔄 | 🔄 | 🔄 ]**", color=discord.Color.light_grey())
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    # Animation loop (swapping emojis)
    for _ in range(3):
        fake_emoji = random.choices(emojis, k=3)
        anim_embed = discord.Embed(title="🎰 Spinning...", description=f"**[ {' | '.join(fake_emoji)} ]**", color=discord.Color.light_grey())
        await msg.edit(embed=anim_embed)
        await asyncio.sleep(0.6) # Delay between "spins"

    # Final Result
    final_emoji = random.choices(emojis, k=3)
    win = final_emoji[0] == final_emoji[1] == final_emoji[2]
    
    final_embed = discord.Embed(
        title="🎰 Result", 
        description=f"**[ {' | '.join(final_emoji)} ]**", 
        color=0xFFD700 if win else 0xFF0000
    )
    if win: final_embed.add_field(name="WINNER", value="✨ JACKPOT! ✨")
    
    await msg.edit(embed=final_embed)

@bot.tree.command(name="activity", description="View activity leaderboard")
async def activity(interaction: discord.Interaction):
    activity_data = bot.config.get("activity", {})
    if not activity_data: return await interaction.response.send_message("No activity yet!")
    sorted_activity = sorted(activity_data.items(), key=lambda item: item[1], reverse=True)
    top_5 = "".join([f"<@{uid}>: {count} msgs\n" for uid, count in sorted_activity[:5]])
    bottom_5 = "".join([f"<@{uid}>: {count} msgs\n" for uid, count in sorted_activity[-5:]])
    embed = discord.Embed(title="📊 Activity", color=discord.Color.purple())
    embed.add_field(name="🔥 Top", value=top_5 or "N/A", inline=False)
    embed.add_field(name="💤 Bottom", value=bottom_5 or "N/A", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="blackjack", description="Play Blackjack")
async def blackjack(interaction: discord.Interaction):
    deck = [f"{v} {s}" for v in ['2','3','4','5','6','7','8','9','10','J','Q','K','A'] for s in ['♠️','♥️','♦️','♣️']]
    random.shuffle(deck)
    view = BlackjackView(interaction.user, [deck.pop(), deck.pop()], [deck.pop(), deck.pop()], deck)
    await interaction.response.send_message(embed=view.create_embed(), view=view)

@bot.tree.command(name="roblox", description="Lookup Roblox user")
async def roblox(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    r = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [username]}).json()
    if not r.get("data"): return await interaction.followup.send("❌ Not found.")
    u_id = r["data"][0]["id"]
    det = requests.get(f"https://users.roblox.com/v1/users/{u_id}").json()
    av = requests.get(f"https://thumbnails.roblox.com/v1/users/avatar?userIds={u_id}&size=720x720&format=Png").json()
    embed = discord.Embed(title=f"Roblox: {det['name']}", color=0x00FF00 if not det.get("isBanned") else 0xFF0000)
    embed.set_image(url=av["data"][0]["imageUrl"])
    embed.add_field(name="Status", value="BANNED" if det.get("isBanned") else "Active")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="mute", description="Timeout member")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int):
    await member.timeout(datetime.timedelta(minutes=minutes))
    await interaction.response.send_message(f"🔇 Muted {member.mention}", ephemeral=True)

@bot.tree.command(name="unmute", description="Remove timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 Unmuted {member.mention}", ephemeral=True)

@bot.tree.command(name="bypass", description="Bypass short links")
async def bypass(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    try:
        res = requests.get(f"https://api.bypass.vip/bypass?url={link}").json()
        await interaction.followup.send(f"🔓 Destination: {res.get('destination')}", ephemeral=True)
    except: await interaction.followup.send("❌ Error.", ephemeral=True)

@bot.tree.command(name="setforumlogs", description="Set log channel")
@app_commands.checks.has_permissions(administrator=True)
async def setforumlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.config["log_channel_id"] = channel.id
    save_config(bot.config)
    await interaction.response.send_message(f"✅ Set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="explosion", description="Nuke a member")
async def explosion(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title="⚠️ NUKE", description=f"{member.mention} targeted!", color=0xFF4500)
    embed.set_image(url="https://media.tenor.com/71K0Y966C-EAAAAC/operation-teapot-nuke.gif")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="say", description="Bot speaks (hidden trigger)")
async def say(interaction: discord.Interaction, message: str, reply_to: str = None):
    await interaction.response.send_message("✅", ephemeral=True)
    target_msg = None
    if reply_to:
        try:
            mid = int(re.search(r'\d+$', reply_to).group())
            target_msg = await interaction.channel.fetch_message(mid)
        except: pass
    if target_msg: await target_msg.reply(message)
    else: await interaction.channel.send(message)

bot.run('MTQ2NzQyODU3MzYyNjM3MjA5OA.GLkFhp.5h694-YRmFTAm1-mga3kdudl09dFcAM7NCOTGY')
