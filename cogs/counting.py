import discord
from discord.ext import commands, tasks
from discord import app_commands
from database import update_setting, get_setting, increment_user_count, get_top_users, get_all_guilds_with_counting, set_counting_number
import datetime

class Counting(commands.GroupCog, name="counting"):
    def __init__(self, bot):
        self.bot = bot
        self.check_topka_time.start() # Spuštění smyčky na pozadí

    def cog_unload(self):
        self.check_topka_time.cancel()

    # --- PŘÍKAZY PRO ADMINISTRÁTORY ---

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_channel", description="Nastaví kanál pro počítání čísel.")
    @app_commands.describe(
        channel="Vyber textový kanál", 
        výchozí_číslo="Zadej číslo, které už v kanálu reálně je (např. 8300)",
        reset_po_chybe="Pokud zvolíš False, bot při chybě neresetuje počítadlo na 0, pouze dá křížek."
    )
    async def setup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, výchozí_číslo: int = 0, reset_po_chybe: bool = True):
        # Pojistka proti 3s timeoutu Discordu
        await interaction.response.defer(ephemeral=True)

        # Uložení do PostgreSQL
        update_setting(interaction.guild_id, "counting_channel_id", channel.id)
        
        # Převedeme bool na 1/0 a uložíme do PostgreSQL
        reset_val = 1 if reset_po_chybe else 0
        update_setting(interaction.guild_id, "reset_on_fail", reset_val)
        
        # Nastavíme číslo podle toho, co administrátor zadal
        set_counting_number(interaction.guild_id, výchozí_číslo)
        
        stav_resetu = "Zapnutý" if reset_po_chybe else "Vypnutý"
        
        # Jelikož jsme použili defer(), odpovídáme pomocí followup.send
        await interaction.followup.send(
            f"🔢 Kanál pro počítání byl nastaven na {channel.mention}.\n"
            f"Aktuální stav byl nastaven na **{výchozí_číslo}**. Další správné číslo je **{výchozí_číslo + 1}**!\n"
            f"⚙️ Reset po chybě: **{stav_resetu}**\n"
            f"🔓 Povoleno: Jeden uživatel může psát více čísel po sobě."
        )

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set_number", description="Ručně přenastaví aktuální číslo v databázi.")
    @app_commands.describe(číslo="Zadej nové aktuální číslo")
    async def set_number(self, interaction: discord.Interaction, číslo: int):
        set_counting_number(interaction.guild_id, číslo)
        await interaction.response.send_message(
            f"🔧 Číslo bylo administrátorem ručně změněno na **{číslo}**.\n"
            f"Další číslo, které musí někdo napsat, je **{číslo + 1}**!", 
            ephemeral=False
        )

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_time", description="Nastaví čas (formát HH:MM), kdy bot každý den pošle topku.")
    @app_commands.describe(time="Zadej čas ve formátu např. 20:00 nebo 15:30")
    async def setup_time(self, interaction: discord.Interaction, time: str):
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            return await interaction.response.send_message("❌ Neplatný formát času. Zadej čas přesně jako např. `18:30`.", ephemeral=True)
            
        update_setting(interaction.guild_id, "counting_time", time)
        await interaction.response.send_message(f"⏰ Automatická topka bude odesílána každý den v `{time}`.", ephemeral=True)

    # --- VEŘEJNÝ PŘÍKAZ PRO VŠECHNY ---

    @app_commands.command(name="leaderboard", description="Ukáže žebříček nejlepších počtářů.")
    async def leaderboard(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        current_number = get_setting(guild_id, "current_number") or 0
        top_users = get_top_users(guild_id, limit=10)

        embed = discord.Embed(
            title=f"📊 Počítací Statistiky – {interaction.guild.name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🔢 Aktuální číslo", value=str(current_number), inline=True)

        leaderboard_text = ""
        if not top_users:
            leaderboard_text = "*Zatím nikdo nezačal počítat.*"
        else:
            for i, (user_id, total) in enumerate(top_users, start=1):
                leaderboard_text += f"**{i}.** <@{user_id}> – `{total}` čísel\n"

        embed.add_field(name="🏆 TOP 10 Uživatelů (Celkově)", value=leaderboard_text, inline=False)
        await interaction.response.send_message(embed=embed)

    # --- LOGIKA HRY (ZACHYTÁVÁNÍ ZPRÁV) ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        counting_channel_id = get_setting(message.guild.id, "counting_channel_id")
        if not counting_channel_id or message.channel.id != counting_channel_id:
            return

        try:
            content = message.content.strip().split()[0]
            user_number = int(content)
        except (ValueError, IndexError):
            return

        current_number = get_setting(message.guild.id, "current_number") or 0
        
        # Zjištění stavu resetu z PostgreSQL
        reset_on_fail_setting = get_setting(message.guild.id, "reset_on_fail")
        reset_on_fail = True if reset_on_fail_setting is None or reset_on_fail_setting == 1 else False
        
        expected_number = current_number + 1

        # KONTROLA CHYBY: Špatné číslo
        if user_number != expected_number:
            await message.add_reaction("❌")
            if reset_on_fail:
                update_setting(message.guild.id, "current_number", 0)
                update_setting(message.guild.id, "last_user_id", None)
                update_setting(message.guild.id, "current_streak", 0)
                await message.channel.send(f"💥 {message.author.mention} napsal špatné číslo (čekalo se `{expected_number}`). Začínáme od **1**.")
            return

        # SPRÁVNĚ: Číslo sedí
        update_setting(message.guild.id, "current_number", expected_number)
        update_setting(message.guild.id, "last_user_id", str(message.author.id))
        
        try:
            streak = get_setting(message.guild.id, "current_streak") or 0
            update_setting(message.guild.id, "current_streak", streak + 1)
        except:
            pass
            
        increment_user_count(message.guild.id, message.author.id)
        await message.add_reaction("✅")

    # --- SMYČKA PRO ODESÍLÁNÍ TOPKY ---

    @tasks.loop(minutes=1.0)
    async def check_topka_time(self):
        now = datetime.datetime.now().strftime("%H:%M")
        guilds = get_all_guilds_with_counting()
        
        for g_id, ch_id, c_time in guilds:
            if c_time == now:
                guild = self.bot.get_guild(int(g_id))
                if not guild:
                    continue
                channel = guild.get_channel(ch_id)
                if not channel:
                    continue
                
                top_users = get_top_users(int(g_id), limit=5)
                
                embed = discord.Embed(
                    title="📊 Denní TOPKA v počítání!",
                    description="Je čas na pravidelné vyhodnocení! Zde jsou naši nejlepší počtáři.",
                    color=discord.Color.purple()
                )
                
                leaderboard_text = ""
                for i, (user_id, total) in enumerate(top_users, start=1):
                    leaderboard_text += f"**{i}.** <@{user_id}> – `{total}` nasázených čísel\n"
                
                embed.add_field(name="Nejaktivnější počtáři", value=leaderboard_text or "Dneska nikdo nepočítal 💤", inline=False)
                await channel.send(embed=embed)

    @check_topka_time.before_loop
    async def before_check_topka_time(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Counting(bot))