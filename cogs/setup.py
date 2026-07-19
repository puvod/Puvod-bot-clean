import discord
from discord.ext import commands
from discord import app_commands
from database import update_setting, get_setting

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_logs", description="Nastaví kanál, kam bude bot posílat logy serveru.")
    @app_commands.describe(channel="Vyber textový kanál pro logování")
    async def setup_logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Příkaz /setup_logs pro uložení kanálu pro logy"""
        update_setting(interaction.guild_id, "logs_channel_id", channel.id)
        await interaction.response.send_message(
            f"✅ Kanál pro logy byl úspěšně nastaven na {channel.mention} pro tento server!", 
            ephemeral=True
        )

    # --- TADY JE TEN NOVÝ PŘÍKAZ ---
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_vitej", description="Nastaví kanál, kam bude bot posílat uvítací zprávy.")
    @app_commands.describe(channel="Vyber textový kanál pro vítání nových členů")
    async def setup_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Příkaz /setup_vitej pro uložení uvítacího kanálu do databáze"""
        # Uložíme ID pod sloupec welcome_channel_id
        update_setting(interaction.guild_id, "welcome_channel_id", channel.id)
        await interaction.response.send_message(
            f"👋 Uvítací kanál byl úspěšně nastaven na {channel.mention} pro tento server!", 
            ephemeral=True
        )

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="show_config", description="Ukáže aktuální nastavení bota pro tento server.")
    async def show_config(self, interaction: discord.Interaction):
        """Příkaz /show_config, který vytáhne data z DB a ukáže je uživateli"""
        logs_id = get_setting(interaction.guild_id, "logs_channel_id")
        welcome_id = get_setting(interaction.guild_id, "welcome_channel_id")

        logs_mention = f"<#{logs_id}>" if logs_id else "❌ Nenastaveno"
        welcome_mention = f"<#{welcome_id}>" if welcome_id else "❌ Nenastaveno"

        embed = discord.Embed(title="⚙️ Nastavení bota pro tento server", color=discord.Color.blue())
        embed.add_field(name="Kanál pro logy", value=logs_mention, inline=False)
        embed.add_field(name="Uvítací kanál", value=welcome_mention, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Setup(bot))