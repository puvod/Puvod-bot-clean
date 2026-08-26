import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime

# Importujeme funkce z databáze (včetně odměňování pro Brawl Stars)
from database import (
    update_setting, get_setting, increment_user_count, 
    get_top_users_daily, get_top_users_lifetime, reset_daily_stats,
    get_all_guilds_with_counting, set_counting_number, add_tokens_and_gems
)

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
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        try:
            await update_setting(interaction.guild_id, "counting_channel_id", channel.id)
            reset_val = 1 if reset_po_chybe else 0
            await update_setting(interaction.guild_id, "reset_on_fail", reset_val)
            await set_counting_number(interaction.guild_id, výchozí_číslo)
            
            stav_resetu = "Zapnutý" if reset_po_chybe else "Vypnutý"
            
            await interaction.followup.send(
                f"🔢 Kanál pro počítání byl nastaven na {channel.mention}.\n"
                f"Aktuální stav byl nastaven na **{výchozí_číslo}**. Další správné číslo je **{výchozí_číslo + 1}**!\n"
                f"⚙️ Reset po chybě: **{stav_resetu}**\n"
                f"🪙 Odměna: Za každé správné číslo získává hráč **1 Token** do Brawl systému!\n"
                f"🔓 Povoleno: Jeden uživatel může psát více čísel po sobě."
            )
        except Exception as e:
            print(f"❌ Chyba při setup_channel: {e}")
            await interaction.followup.send("❌ Nepodařilo se uložit nastavení do databáze.")

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set_number", description="Ručně přenastaví aktuální číslo v databázi.")
    @app_commands.describe(číslo="Zadej nové aktuální číslo")
    async def set_number(self, interaction: discord.Interaction, číslo: int):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=False)
        except discord.NotFound:
            return

        try:
            await set_counting_number(interaction.guild_id, číslo)
            await interaction.followup.send(
                f"🔧 Číslo bylo administrátorem ručně změněno na **{číslo}**.\n"
                f"Další číslo, které musí někdo napsat, je **{číslo + 1}**!"
            )
        except Exception as e:
            print(f"❌ Chyba při set_number: {e}")
            await interaction.followup.send("❌ Nepodařilo se připojit k databázi.")

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_time", description="Nastaví čas (formát HH:MM), kdy bot každý den pošle topku.")
    @app_commands.describe(time="Zadej čas ve formátu např. 20:00 nebo 15:30")
    async def setup_time(self, interaction: discord.Interaction, time: str):
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            return await interaction.response.send_message("❌ Neplatný formát času. Zadej čas přesně jako např. `18:30`.", ephemeral=True)
            
        try:
            await update_setting(interaction.guild_id, "counting_time", time)
            await interaction.response.send_message(f"⏰ Automatická topka bude odesílána každý den v `{time}`.", ephemeral=True)
        except Exception as e:
            print(f"❌ Chyba při setup_time: {e}")
            await interaction.response.send_message("❌ Chyba při ukládání do databáze.", ephemeral=True)

    # --- VEŘEJNÝ PŘÍKAZ PRO VŠECHNY ---

    @app_commands.command(name="leaderboard", description="Ukáže žebříček nejlepších počtářů.")
    @app_commands.choices(typ=[
        app_commands.Choice(name="Dnešní den", value="daily"),
        app_commands.Choice(name="Celkově (Lifetime)", value="lifetime")
    ])
    async def leaderboard(self, interaction: discord.Interaction, typ: str = "daily"):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except discord.NotFound:
            return

        guild_id = interaction.guild_id
        
        try:
            current_number = await get_setting(guild_id, "current_number") or 0
            
            if typ == "daily":
                top_users = await get_top_users_daily(guild_id, limit=10)
                title = f"📊 Dnešní Žebříček – {interaction.guild.name}"
            else:
                top_users = await get_top_users_lifetime(guild_id, limit=10)
                title = f"🏆 Celkový Žebříček – {interaction.guild.name}"

            embed = discord.Embed(title=title, color=discord.Color.gold())
            embed.add_field(name="🔢 Aktuální číslo", value=str(current_number), inline=True)

            leaderboard_text = ""
            if not top_users:
                leaderboard_text = "*Zatím nikdo nezačal počítat.*"
            else:
                for i, (user_id, total) in enumerate(top_users, start=1):
                    unit = "dnes" if typ == "daily" else "celkem"
                    leaderboard_text += f"**{i}.** <@{user_id}> – `{total}` čísel ({unit})\n"

            embed.add_field(name="Nejlepší počtáři", value=leaderboard_text, inline=False)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"❌ Chyba v leaderboardu: {e}")
            await interaction.followup.send("❌ Nastala chyba při načítání žebříčku z databáze.")

    # --- LOGIKA HRY (ZACHYTÁVÁNÍ ZPRÁV) ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        try:
            counting_channel_id = await get_setting(message.guild.id, "counting_channel_id")
        except Exception:
            return

        if not counting_channel_id or str(message.channel.id) != str(counting_channel_id):
            return

        try:
            content = message.content.strip().split()[0]
            user_number = int(content)
        except (ValueError, IndexError):
            return

        try:
            current_number = await get_setting(message.guild.id, "current_number") or 0
            reset_on_fail_setting = await get_setting(message.guild.id, "reset_on_fail")
            reset_on_fail = True if reset_on_fail_setting is None or int(reset_on_fail_setting) == 1 else False
            
            expected_number = int(current_number) + 1

            # KONTROLA CHYBY: Špatné číslo
            if user_number != expected_number:
                await message.add_reaction("❌")
                if reset_on_fail:
                    await update_setting(message.guild.id, "current_number", 0)
                    await update_setting(message.guild.id, "last_user_id", None)
                    await update_setting(message.guild.id, "current_streak", 0)
                    await message.channel.send(f"💥 {message.author.mention} napsal špatné číslo (čekalo se `{expected_number}`). Začínáme od **1**.")
                return

            # SPRÁVNĚ: Číslo sedí
            await update_setting(message.guild.id, "current_number", expected_number)
            await update_setting(message.guild.id, "last_user_id", str(message.author.id))
            
            try:
                streak = await get_setting(message.guild.id, "current_streak") or 0
                await update_setting(message.guild.id, "current_streak", int(streak) + 1)
            except Exception:
                pass
                
            # Přičte +1 do denní i celkové topky
            await increment_user_count(message.guild.id, message.author.id)
            
            # ODMĚNA: Přidá 1 token do Brawl Stars ekonomiky
            await add_tokens_and_gems(message.guild.id, message.author.id, tokens=1, gems=0)
            
            # --- PŘIDÁNÍ CUSTOM EMOJI ---
            verify_emoji = discord.utils.get(message.guild.emojis, name="verify")
            if verify_emoji:
                await message.add_reaction(verify_emoji)
            else:
                await message.add_reaction("✅")

        except Exception as e:
            print(f"❌ Chyba v on_message počítání: {e}")

    # --- SMYČKA PRO ODESÍLÁNÍ TOPKY A RESET ---

    @tasks.loop(minutes=1.0)
    async def check_topka_time(self):
        now = datetime.datetime.now().strftime("%H:%M")
        
        try:
            guilds = await get_all_guilds_with_counting()
        except Exception:
            return
            
        for g_id, ch_id, c_time in guilds:
            if c_time == now:
                guild = self.bot.get_guild(int(g_id))
                if not guild:
                    continue
                channel = guild.get_channel(int(ch_id))
                if not channel:
                    continue
                
                try:
                    # Načteme pouze denní statistiky
                    top_users = await get_top_users_daily(int(g_id), limit=5)
                    
                    embed = discord.Embed(
                        title="📊 Denní TOPKA v počítání!",
                        description="Je čas na pravidelné vyhodnocení! Zde jsou naši nejlepší počtáři za uplynulý den.",
                        color=discord.Color.purple()
                    )
                    
                    leaderboard_text = ""
                    for i, (user_id, total) in enumerate(top_users, start=1):
                        leaderboard_text += f"**{i}.** <@{user_id}> – `{total}` nasázených čísel\n"
                    
                    embed.add_field(name="Nejaktivnější počtáři", value=leaderboard_text or "Dneska nikdo nepočítal 💤", inline=False)
                    await channel.send(embed=embed)
                    
                    # VYNULOVÁNÍ DENNÍCH STATISTIK PRO TENTO SERVER
                    await reset_daily_stats(int(g_id))
                    print(f"🔄 Denní statistiky pro server {guild.name} byly vynulovány.")
                except Exception as e:
                    print(f"❌ Chyba při odesílání topky a resetu: {e}")

    @check_topka_time.before_loop
    async def before_check_topka_time(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Counting(bot))