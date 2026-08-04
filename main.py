import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Importujeme naše vlastní moduly
from web import keep_alive
from database import init_db
from cogs.roles import RankSelectView  # Import pro Brawl Stars Ranky

# 1. Načtení tokenu z .env souboru
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 2. Nastavení oprávnění (Intents)
intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Spustí se předtím, než se bot oficiálně přihlásí k Discordu."""
        # Inicializace databáze
        init_db()
        print("🗄️ Databáze byla úspěšně inicializována.")

        # Registrace Persistent View pro Brawl Stars Ranky
        self.add_view(RankSelectView())
        print("🔘 Persistentní tlačítka byla zaregistrována.")

        # Automatické načtení všech souborů ze složky cogs/
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"📦 Cog '{filename}' byl úspěšně načten.")

        # Synchronizace lomítkových příkazů
        await self.tree.sync()
        print("🔄 Lomítkové příkazy byly synchronizovány.")

    async def on_ready(self):
        """Spustí se, jakmile je bot online."""
        print(f"🤖 Bot {self.user.name} je ONLINE a připraven k akci!")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="oba servery"))

# 3. Asynchronní spouštěč bota
async def start_bot_safely(bot_instance):
    while True:
        try:
            print("🚀 Pokouším se přihlásit k Discord API...")
            await bot_instance.start(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("⚠️ Detekován Rate Limit (429)! Zkouším se znovu připojit za 5 minut...")
                await asyncio.sleep(300)
            else:
                print(f"❌ Nastala chyba při připojování: {e}")
                await asyncio.sleep(30)
        except Exception as e:
            print(f"❌ Kritické selhání: {e}")
            await asyncio.sleep(30)

async def main():
    bot = MyBot()
    await start_bot_safely(bot)

if __name__ == "__main__":
    keep_alive()
    print("🌐 Webový server FastAPI běží na pozadí.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot byl ručně vypnut.")