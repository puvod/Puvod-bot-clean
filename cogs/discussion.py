import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
from database import get_setting

# Seznam diskuzních a názorových témat
DISCUSSION_TOPICS = [
    "🎮 **60 FPS na Ultra detaily vs. 240 FPS na Low detaily** – co je pro vás prioritou a proč?",
    "🎵 Kdybys mohl do konce života poslouchat jen **3 písničky**, které by to byly?",
    "🖥️ **Klávesnice & Myš vs. Controller** – na čem se vám hraje lépe a v čem vidíte největší výhody?",
    "🎧 Poslech hudby: **Kvalitní studiová sluchátka vs. repráky na plné pecky**?",
    "🍕 **Havajská pizza (s ananasem)** – geniální kombinace, nebo zločin proti gastronomii?",
    "🎬 **Filmy/Seriály s dabingem vs. v původním znění s titulky** – jak koukáte nejraději?",
    "📱 **iOS vs. Android** – co aktuálně používáte a co vás drží u vašeho systému?",
    "☕ **Káva vs. Energetické nápoje (Gamer drinks)** – co vás drží při životě během nočního hraní?",
    "🌍 Kdybys měl možnost **okamžitě se přestěhovat kamkoliv na světě**, jaká země/město by to bylo?",
    "🕹️ **Příběhové singleplayer hry vs. Čistě kompetitivní multiplayerky** – u čeho strávíte víc času?"
]

class DiscussionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Spustíme automatickou smyčku po načtení cogu
        self.discussion_loop.start()

    def cog_unload(self):
        self.discussion_loop.cancel()

    # Automatická smyčka – nastavena např. na každých 24 hodin (můžeš upravit podle potřeby)
    @tasks.loop(hours=24)
    async def discussion_loop(self):
        # Počkáme, až bude bot plně připojen
        await self.bot.wait_until_ready()

        # Projdeme všechny servery, kde bot je, a najdeme nastavený kanál (využijeme např. obecný chat)
        for guild in self.bot.guilds:
            # Můžeš použít ID konkrétního kanálu nebo vytáhnout z databáze
            # Pokud máš kanál nastavený v DB pod klíčem 'welcome_channel_id' nebo 'chat_channel_id', načteme ho:
            channel_id = get_setting(guild.id, "welcome_channel_id")  # případně nahraď svým ID kanálu
            
            if channel_id:
                channel = guild.get_channel(channel_id)
                if channel:
                    topic = random.choice(DISCUSSION_TOPICS)
                    embed = discord.Embed(
                        title="💬 TÉMA PRO DNEŠNÍ DISKUZI",
                        description=f"{topic}\n\n*Nahoďte své názory a argumenty do chatu!*",
                        color=discord.Color.og_blurple()
                    )
                    await channel.send(embed=embed)

    # Příkaz pro ruční vyvolání tématu (pro testování nebo když chceš téma hodit hned)
    @app_commands.command(name="topic", description="Pošle náhodné diskuzní téma do chatu")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_topic(self, interaction: discord.Interaction):
        topic = random.choice(DISCUSSION_TOPICS)
        embed = discord.Embed(
            title="💬 TÉMA K DISKUZI",
            description=f"{topic}\n\n*Jaký je váš názor?*",
            color=discord.Color.og_blurple()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Téma bylo úspěšně odesláno!", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DiscussionCog(bot))