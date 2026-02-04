import os
import json
import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
OWNER_ID = 1237720626152607794  # your Discord user ID

SAVE_CHANNEL_NAME = "loom-save"
SAVE_MESSAGE_HEADER = "LOOM_SAVE_JSON::"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def is_owner(user: discord.abc.User) -> bool:
    return user.id == OWNER_ID


def default_state() -> dict:
    return {
        "title": "The Loom Below",
        "chapter": 1,
        "scene": 1,
        "memory": [],
        "stats": {"affinity": 0, "thread": 0, "resolve": 0}
    }


async def get_or_create_save_channel(guild: discord.Guild) -> discord.TextChannel:
    # Find existing channel
    for ch in guild.text_channels:
        if ch.name == SAVE_CHANNEL_NAME:
            return ch

    # Create a private save channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True,
        ),
    }

    owner_member = guild.get_member(OWNER_ID)
    if owner_member:
        overwrites[owner_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    channel = await guild.create_text_channel(SAVE_CHANNEL_NAME, overwrites=overwrites)
    return channel


async def find_save_message(channel: discord.TextChannel) -> discord.Message | None:
    async for msg in channel.history(limit=50):
        if msg.content.startswith(SAVE_MESSAGE_HEADER):
            return msg
    return None


async def load_state_from_discord(guild: discord.Guild) -> dict:
    channel = await get_or_create_save_channel(guild)
    msg = await find_save_message(channel)

    if not msg:
        state = default_state()
        payload = SAVE_MESSAGE_HEADER + json.dumps(state, ensure_ascii=False)
        await channel.send(payload)
        return state

    raw = msg.content[len(SAVE_MESSAGE_HEADER):].strip()
    try:
        return json.loads(raw)
    except Exception:
        # If corrupted, reset
        state = default_state()
        payload = SAVE_MESSAGE_HEADER + json.dumps(state, ensure_ascii=False)
        await msg.edit(content=payload)
        return state


async def save_state_to_discord(guild: discord.Guild, state: dict):
    channel = await get_or_create_save_channel(guild)
    msg = await find_save_message(channel)

    payload = SAVE_MESSAGE_HEADER + json.dumps(state, ensure_ascii=False)

    if msg:
        await msg.edit(content=payload)
    else:
        await channel.send(payload)


def dm_response(state: dict, player_choice: str) -> str:
    # Record player message
    state["memory"].append({"role": "player", "content": player_choice})

    # Simple keyword-based stat changes
    lc = player_choice.lower()
    if any(w in lc for w in ["help", "save", "protect", "spare"]):
        state["stats"]["affinity"] += 1
        state["stats"]["resolve"] += 1
    if any(w in lc for w in ["attack", "strike", "kill", "threaten"]):
        state["stats"]["thread"] += 1
    if any(w in lc for w in ["listen", "wait", "observe", "investigate"]):
        state["stats"]["resolve"] += 1

    # Advance scene/chapter
    state["scene"] += 1
    if state["scene"] > 4:
        state["chapter"] += 1
        state["scene"] = 1

    chapter = state["chapter"]
    scene = state["scene"]
    a = state["stats"]["affinity"]
    t = state["stats"]["thread"]
    r = state["stats"]["resolve"]

    response = (
        f"🧵 **The Loom Below — Chapter {chapter}, Scene {scene}**\n\n"
        f"Your choice pulls on the dungeon like a hidden stitch.\n\n"
        f"**Weave Stats:** Affinity `{a}` | Thread `{t}` | Resolve `{r}`\n\n"
        f"**The Dungeon Master:**\n"
        f"The corridor exhales cold air. A symbol on the stone flickers, responding to intent.\n\n"
        f"**Choose what you do next:**\n"
        f"1) *Press forward into the corridor*\n"
        f"2) *Study the symbol for meaning*\n"
        f"3) *Speak a pact into the dark*\n"
        f"4) *Retreat and steady yourself*\n\n"
        f"Use `/choice <text>` to respond."
    )

    # Record DM response
    state["memory"].append({"role": "dm", "content": response})
    return response


@tree.command(name="start", description="Start (or restart) your private story. (Owner-only)")
async def start(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this bot.",
            ephemeral=True
        )

    state = default_state()
    intro = (
        "🧵 **The Loom Below — Prologue**\n\n"
        "You descend into a dungeon that feeds on decisions.\n"
        "Every sentence becomes a knot.\n\n"
        "**Your first move:**\n"
        "1) *Speak your name into the dark*\n"
        "2) *Remain silent and listen*\n"
        "3) *Mark the entrance with a sign*\n\n"
        "Use `/choice <text>`."
    )

    state["memory"].append({"role": "dm", "content": intro})
    await save_state_to_discord(interaction.guild, state)

    await interaction.response.send_message(intro)


@tree.command(name="choice", description="Make a choice in the story. (Owner-only)")
@app_commands.describe(text="What you do / say next")
async def choice(interaction: discord.Interaction, text: str):
    if not is_owner(interaction.user):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this bot.",
            ephemeral=True
        )

    state = await load_state_from_discord(interaction.guild)
    response = dm_response(state, text)
    await save_state_to_discord(interaction.guild, state)

    await interaction.response.send_message(response)


@tree.command(name="status", description="Show current story status. (Owner-only)")
async def status(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this bot.",
            ephemeral=True
        )

    state = await load_state_from_discord(interaction.guild)
    s = state["stats"]

    await interaction.response.send_message(
        f"🧵 **Status**\n"
        f"Title: **{state['title']}**\n"
        f"Chapter: `{state['chapter']}` | Scene: `{state['scene']}`\n"
        f"Affinity: `{s['affinity']}` | Thread `{s['thread']}` | Resolve `{s['resolve']}`\n"
        f"History entries: `{len(state['memory'])}`"
    )


@tree.command(name="export_history", description="Export your history as a JSON file. (Owner-only)")
async def export_history(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this bot.",
            ephemeral=True
        )

    state = await load_state_from_discord(interaction.guild)
    data = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")

    await interaction.response.send_message(
        "📦 Here is your export:",
        file=discord.File(fp=discord.BytesIO(data), filename="loom_export.json")
    )


@tree.command(name="import_history", description="Import history from a JSON file. (Owner-only)")
async def import_history(interaction: discord.Interaction, file: discord.Attachment):
    if not is_owner(interaction.user):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this bot.",
            ephemeral=True
        )

    if not file.filename.lower().endswith(".json"):
        return await interaction.response.send_message(
            "❌ Please upload a .json file.",
            ephemeral=True
        )

    raw = await file.read()
    try:
        imported = json.loads(raw.decode("utf-8"))
    except Exception:
        return await interaction.response.send_message(
            "❌ That file is not valid JSON.",
            ephemeral=True
        )

    required = ["title", "chapter", "scene", "memory", "stats"]
    if not all(k in imported for k in required):
        return await interaction.response.send_message(
            "❌ Save file missing required fields: title, chapter, scene, memory, stats.",
            ephemeral=True
        )

    await save_state_to_discord(interaction.guild, imported)
    await interaction.response.send_message(
        f"✅ Imported save!\n"
        f"Title: **{imported['title']}** | Chapter `{imported['chapter']}` Scene `{imported['scene']}`\n"
        f"Entries: `{len(imported['memory'])}`"
    )


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Sync failed:", e)


if not TOKEN:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable!")

client.run(TOKEN)
