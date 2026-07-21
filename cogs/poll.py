import discord
from discord import app_commands
from discord.ext import commands

class PollView(discord.ui.View):
    def __init__(self, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
        super().__init__(timeout=None) # Persistent view
        self.question = question
        self.options = [opt for opt in [option1, option2, option3, option4] if opt]
        self.votes = {i: set() for i in range(len(self.options))}

        # Dynamicky přidáme tlačítka podle počtu možností
        styles = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.danger, discord.ButtonStyle.secondary]
        for i, option in enumerate(self.options):
            button = discord.ui.Button(
                label=option[:80], # Discord limit na délku labelu
                style=styles[i % len(styles)],
                custom_id=f"poll_opt_{i}"
            )
            # Nastavíme callback s předaným indexem tlačítka
            button.callback = self.make_callback(i)
            self.add_item(button)

    def make_callback(self, option_index: int):
        async def button_callback(interaction: discord.Interaction):
            user_id = interaction.user.id

            # Zkontrolujeme, zda už uživatel nehlasoval někde jinde v této anketě
            for idx, user_set in self.votes.items():
                if user_id in user_set:
                    user_set.remove(user_id)

            # Přidáme nový hlas
            self.votes[option_index].add(user_id)

            # Aktualizujeme embed s novými výsledky
            new_embed = self.create_embed(interaction.user)
            await interaction.response.edit_message(embed=new_embed, view=self)

        return button_callback

    def create_embed(self, author: discord.User = None):
        total_votes = sum(len(users) for users in self.votes.values())
        
        description = f"**{self.question}**\n\n"

        for i, option in enumerate(self.options):
            vote_count = len(self.votes[i])
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
            
            # Vytvoření vizuálního ukazatele (progress bar)
            bar_length = 10
            filled = int(round(bar_length * percentage / 100))
            bar = "█" * filled + "░" * (bar_length - filled)
            
            description += f"**{option}**\n`[{bar}]` **{vote_count}** hlasů ({percentage:.1f}%)\n\n"

        description += f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\nCelkem hlasovalo: **{total_votes}** uživatelů"

        embed = discord.Embed(
            title="📊 HLASOVÁNÍ / ANKETA",
            description=description,
            color=discord.Color.blurple()
        )
        return embed


async def setup(bot):
    @bot.tree.command(name="anketa", description="Vytvoří interaktivní anketu s tlačítky")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        otazka="Otázka nebo téma hlasování",
        moznost1="První možnost",
        moznost2="Druhá možnost",
        moznost3="Třetí možnost (volitelné)",
        moznost4="Čtvrtá možnost (volitelné)"
    )
    async def create_poll(
        interaction: discord.Interaction, 
        otazka: str, 
        moznost1: str, 
        moznost2: str, 
        moznost3: str = None, 
        moznost4: str = None
    ):
        view = PollView(otazka, moznost1, moznost2, moznost3, moznost4)
        embed = view.create_embed()
        
        await interaction.response.send_message("Anketa byla úspěšně vytvořena!", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)