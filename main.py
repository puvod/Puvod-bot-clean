import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Importujeme naše vlastní moduly
from web import keep_alive
from database import init_db

# 1. Načtení tokenu z .env souboru
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 2. Nastavení oprávnění (Intents) pro bota
# Pro plnou funkčnost (např. sledování zpráv, připojení členů) zapínáme all()
intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        # Nastavíme prefix (např. pro textové příkazy, i když budeme primárně používat lomítka)
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Spustí se předtím, než se bot oficiálně přihlásí k Discordu."""
        # Inicializace databáze (vytvoří soubor a tabulky, pokud neexistují)
        init_db()
        print("🗄️ Databáze byla úspěšně inicializována.")

        # Automatické načtení všech souborů ze složky cogs/
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"📦 Cog '{filename}' byl úspěšně načten.")

        # Synchronizace lomítkových příkazů (Slash Commands) globálně
        # POZNÁMKA: Discordu může trvat pár minut, než se příkazy zaregistrují všude
        await self.tree.sync()
        print("🔄 Lomítkové příkazy byly synchronizovány.")

    async def on_ready(self):
        """Spustí se, jakmile je bot online a připojený."""
        print(f"🤖 Bot {self.user.name} je ONLINE a připraven k akci!")
        # Nastavení statusu bota (např. Sleduje uživatele)
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="oba servery"))

# 3. Asynchronní spouštěč bota s ochranou proti Rate Limitům
async def start_bot_safely(bot_instance):
    while True:
        try:
            print("🚀 Pokouším se přihlásit k Discord API...")
            await bot_instance.start(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("⚠️ Detekován Rate Limit (429) od Discordu! IP adresa na Renderu je zablokovaná.")
                print("⏳ Web běží dál. Zkouším se znovu připojit za 5 minut...")
                await asyncio.sleep(300) # Počká 5 minut a zkusí to znova
            else:
                print(f"❌ Nastala neočekávaná chyba při připojování: {e}")
                print("🔄 Zkouším se znovu připojit za 30 sekund...")
                await asyncio.sleep(30)
        except Exception as e:
            print(f"❌ Kritické selhání sítě nebo knihovny: {e}")
            print("🔄 Zkouším restartovat připojení za 30 sekund...")
            await asyncio.sleep(30)

async def main():
    # Vytvoříme instanci bota
    bot = MyBot()
    # Spustíme bezpečnou smyčku pro připojení
    await start_bot_safely(bot)

# Spuštění celého kolosu
if __name__ == "__main__":
    # Nejprve nastartujeme webový server na pozadí, aby držel bota naživu
    keep_alive()
    print("🌐 Webový server FastAPI běží na pozadí.")

    # Spustíme asynchronní hlavní smyčku
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot byl ručně vypnut.")