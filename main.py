import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from web import keep_alive
from database import db
from cogs.roles import RankSelectView

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Persistentní tlačítka
        self.add_view(RankSelectView())
        print("🔘 Persistentní tlačítka byla zaregistrována.")

        # Načtení všech cogů
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"📦 Cog '{filename}' byl úspěšně načten.")

        # Synchronizace Slash příkazů
        await self.tree.sync()
        print("🔄 Lomítkové příkazy byly synchronizovány.")

    async def on_ready(self):
        print(f"🤖 Bot {self.user.name} je ONLINE a připraven k akci!")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="oba servery"))

bot = MyBot()

# Zachycení chyb ze Slash příkazů bez padání na mrtvých interakcích
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    cmd_name = interaction.command.name if interaction.command else "unknown"
    print(f"❌ Chyba při vykonávání příkazu /{cmd_name}: {error}")
    
    message = "⚠️ Při zpracování příkazu došlo k chybě v databázi nebo aplikaci."
    
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.errors.NotFound:
        # Interakce vypršela nebo byla smazána klientem — ignorujeme bez pádů v konzoli
        pass

async def start_bot_safely():
    while True:
        try:
            print("🚀 Pokouším se přihlásit k Discord API...")
            await bot.start(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("⚠️ Detekován Rate Limit (429)! Zkouším se znovu připojit za 5 minut...")
                await asyncio.sleep(300)
            else:
                print(f"❌ Nastala chyby při připojování: {e}")
                await asyncio.sleep(30)
        except Exception as e:
            print(f"❌ Kritické selhání: {e}")
            await asyncio.sleep(30)

async def main():
    # Připojení k databázi proběhne JEN JEDNOU před spuštěním bota
    await db.connect()
    print("🗄️ Databáze byla úspěšně připojena.")
    
    await start_bot_safely()

if __name__ == "__main__":
    keep_alive()
    print("🌐 Webový server FastAPI běží na pozadí.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot byl ručně vypnut.")