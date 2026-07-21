import random
import asyncio
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands

# Pomocná funkce pro odstranění diakritiky (aby bot reagoval i na text bez háčků/čárek)
def normalize_text(text: str) -> str:
    text = text.lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

class RoleModal(discord.ui.Modal, title='Vytvořit menu rolí'):
    title_input = discord.ui.TextInput(label='Nadpis Embedu', placeholder='VÝBĚR ROLÍ')
    desc_input = discord.ui.TextInput(label='Popis', style=discord.TextStyle.paragraph, placeholder='Vyber si své role...')
    roles_input = discord.ui.TextInput(label='ID rolí (oddělené čárkou)', placeholder='1234567890, 0987654321')

    async def on_submit(self, interaction: discord.Interaction):
        role_ids = [int(i.strip()) for i in self.roles_input.value.split(',')]
        roles = [interaction.guild.get_role(rid) for rid in role_ids if interaction.guild.get_role(rid)]
        
        embed = discord.Embed(title=self.title_input.value, description=self.desc_input.value, color=discord.Color.blue())
        view = CombinedRoleView(roles)
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("Menu bylo odesláno!", ephemeral=True)

class CombinedRoleView(discord.ui.View):
    def __init__(self, roles=None):
        super().__init__(timeout=None)
        if roles:
            for role in roles[:5]:
                self.add_item(RoleButton(role))
            if len(roles) > 5:
                self.add_item(RoleSelect(roles[5:]))

class RoleButton(discord.ui.Button):
    def __init__(self, role):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"btn_{role.id}")
        self.role_id = role.id
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Odebral jsem: {role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Přidal jsem: {role.name}", ephemeral=True)

class RoleSelect(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles]
        super().__init__(placeholder="Další role...", options=options, custom_id="select_roles")
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Odebral jsem: {role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Přidal jsem: {role.name}", ephemeral=True)

# Databáze 50+ otázek
QUESTIONS = {
    "easy": [
        {"q": "Jaké je hlavní město České republiky? 🇨🇿", "a": ["praha"], "xp": 10},
        {"q": "Kolik nohou má pavouk? 🕷️", "a": ["8", "osm"], "xp": 10},
        {"q": "Jaká je největší planeta naší sluneční soustavy? 🪐", "a": ["jupiter"], "xp": 10},
        {"q": "Které zvíře je známé jako 'král džungle'? 🦁", "a": ["lev"], "xp": 10},
        {"q": "Kolik hodin má jeden den? ⏰", "a": ["24", "dvacet ctyri"], "xp": 10},
        {"q": "Jakou barvu získáš smícháním modré a žluté? 🎨", "a": ["zelena", "zelenou"], "xp": 10},
        {"q": "Který oceán je největší na Zemi? 🌊", "a": ["tichy", "tichy ocean", "pacifik"], "xp": 10},
        {"q": "Jak se jmenuje mládě psa? 🐶", "a": ["stene"], "xp": 10},
        {"q": "Kolik dní má přestupný rok? 📅", "a": ["366"], "xp": 10},
        {"q": "Ve které zemi leží pyramidy v Gíze? 🇪🇬", "a": ["egypt"], "xp": 10},
        {"q": "Jaký plyn dýcháme, abychom přežili? 🌬️", "a": ["kyslik"], "xp": 10},
        {"q": "Rychlá matematika: Kolik je **15 + 27**? 🧮", "a": ["42"], "xp": 10},
        {"q": "Slovo pozpátku: Napiš slovo **BOT** pozpátku! 🔄", "a": ["tob"], "xp": 10},
        {"q": "Jaká je chemická značka pro vodu? 💧", "a": ["h2o"], "xp": 10},
        {"q": "Které roční období následuje po zimě? 🌸", "a": ["jaro"], "xp": 10},
        {"q": "Kdo je hlavní postava v pohádce o Šípkové Růžence? 👑", "a": ["ruzenka", "sipkova ruzenka"], "xp": 10},
        {"q": "Kolik minut má jedna hodina? ⏱️", "a": ["60", "sedesat"], "xp": 10},
        {"q": "Které zvíře dává mléko a dělá 'Bůů'? 🐄", "a": ["krava"], "xp": 10}
    ],
    "medium": [
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 25},
        {"q": "Jaké je hlavní město Slovenska? 🇸🇰", "a": ["bratislava"], "xp": 25},
        {"q": "Který je nejdelší orgán v lidském těle? 🧠", "a": ["tenke strevo", "strevo", "kuze"], "xp": 25},
        {"q": "Jaké je hlavní město Francie? 🇫🇷", "a": ["pariz"], "xp": 25},
        {"q": "Který pták je známý tím, že neumí létat a žije na Antarktidě? 🐧", "a": ["tucnak"], "xp": 25},
        {"q": "Rychlá matematika: Kolik je **12 x 8**? 🧮", "a": ["96"], "xp": 25},
        {"q": "Jaké je nejsevernější hlavní město na světě? ❄️", "a": ["reykjavik"], "xp": 25},
        {"q": "Který kov je za pokojové teploty kapalný? 🧪", "a": ["rtut"], "xp": 25},
        {"q": "Jak se jmenuje nejvyšší hora Evropy (Mont Blanc nebo Elbrus)? 🏔️", "a": ["elbrus", "mont blanc"], "xp": 25},
        {"q": "Kolik zubů má dospělý člověk (včetně zubů moudrosti)? 🦷", "a": ["32"], "xp": 25},
        {"q": "Ve kterém státě leží město Sydney? 🇦🇺", "a": ["australie"], "xp": 25},
        {"q": "Slovo pozpátku: Napiš **PLANETA** pozpátku! 🔄", "a": ["atenalp"], "xp": 25},
        {"q": "Která je nejdelší řeka světa? 🌊", "a": ["nil", "amazonka"], "xp": 25},
        {"q": "Kolik strun má standardní kytara? 🎸", "a": ["6", "sest"], "xp": 25},
        {"q": "Který plyn tvoří většinu atmosféry Země? 🌌", "a": ["dusik"], "xp": 25},
        {"q": "Jak se jmenuje proces, při kterém rostliny vyrábějí kyslík? 🌿", "a": ["fotosynteza"], "xp": 25},
        {"q": "Které město je známé jako 'Věčné město'? 🏛️", "a": ["rim"], "xp": 25},
        {"q": "Rychlá matematika: Kolik je **144 / 12**? 🧮", "a": ["12"], "xp": 25},
        {"q": "Který savec dokáže létat? 🦇", "a": ["netopyr"], "xp": 25}
    ],
    "hard": [
        {"q": "Jaké je hlavní město Austrálie? (Pozor, Sydney to není!) 🇦🇺", "a": ["canberra"], "xp": 50},
        {"q": "Který chemický prvek má značku **Au**? 🥇", "a": ["zlato"], "xp": 50},
        {"q": "Jak se jmenuje nejhlubší místo na Zemi? 🌊", "a": ["mariansky prikop", "marianska prikop"], "xp": 50},
        {"q": "Rychlá matematika: Kolik je **15 x 15**? 🧮", "a": ["225"], "xp": 50},
        {"q": "Jaké je hlavní město Kanady? 🇨🇦", "a": ["ottawa"], "xp": 50},
        {"q": "Jak se jmenuje největší poušť na světě (mimo polární)? 🏜️", "a": ["sahara"], "xp": 50},
        {"q": "Slovo pozpátku: Napiš **HYPERPROSTOR** pozpátku! 🔄", "a": ["rostorprepyh"], "xp": 50},
        {"q": "Která kost v lidském těle je nejdelší a nejsilnější? 🦴", "a": ["ost stehenni", "stehenni kost", "stehenni"], "xp": 50},
        {"q": "Jaké je hlavní město Brazílie? 🇧🇷", "a": ["brasilia"], "xp": 50},
        {"q": "Která planeta má nejvíce měsíců ve Sluneční soustavě? 🪐", "a": ["saturn"], "xp": 50},
        {"q": "Rychlá matematika: Kolik je **(45 + 55) x 3**? 🧮", "a": ["300"], "xp": 50},
        {"q": "Který stát má největší rozlohu na světě? 🗺️", "a": ["rusko"], "xp": 50},
        {"q": "Jak se nazývá nejtvrdší přírodní minerál? 💎", "a": ["diamant"], "xp": 50}
    ]
}

async def setup(bot):
    @bot.tree.command(name="create-role-menu", description="Vytvoří interaktivní menu rolí")
    async def create_role_menu(interaction: discord.Interaction):
        await interaction.response.send_modal(RoleModal())

    @bot.tree.command(name="revive", description="Spustí Chat Revive event s možností výběru obtížnosti")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="🟢 Easy (10 XP)", value="easy"),
        app_commands.Choice(name="🟡 Medium (25 XP)", value="medium"),
        app_commands.Choice(name="🔴 Hard (50 XP)", value="hard")
    ])
    async def revive(interaction: discord.Interaction, difficulty: app_commands.Choice[str]):
        diff_key = difficulty.value
        question_data = random.choice(QUESTIONS[diff_key])
        
        chat_revive_role_id = 1475934465623588904
        
        colors = {
            "easy": discord.Color.green(),
            "medium": discord.Color.gold(),
            "hard": discord.Color.red()
        }
        
        embed = discord.Embed(
            title=f"⚡ CHAT REVIVE EVENT [{difficulty.name}] ⚡",
            description=f"**Otázka:** {question_data['q']}\n\n*První správná odpověď vyhrává **{question_data['xp']} XP**!*",
            color=colors.get(diff_key, discord.Color.blue())
        )
        embed.set_footer(text="Čas na odpověď: 5 minut")
        
        await interaction.response.send_message(content=f"<@&{chat_revive_role_id}>", embed=embed)
        
        def check(m):
            if m.channel != interaction.channel or m.author.bot:
                return False
            normalized_msg = normalize_text(m.content)
            return any(normalized_msg == normalize_text(ans) for ans in question_data['a'])

        try:
            # Čeká až 300 sekund (5 minut)
            winner_msg = await bot.wait_for('message', check=check, timeout=300.0)
            
            win_embed = discord.Embed(
                title="🎉 MÁME VÍTĚZE! 🎉",
                description=f"Uživatel {winner_msg.author.mention} odpověděl správně jako první!\n\n**Odpověď:** {winner_msg.content}\n**Odměna:** +{question_data['xp']} XP",
                color=discord.Color.brand_green()
            )
            await interaction.channel.send(embed=win_embed)
            
        except asyncio.TimeoutError:
            correct_answers = ", ".join(question_data['a'])
            fail_embed = discord.Embed(
                title="⏰ ČAS VYPRŠEL!",
                description=f"Nikdo nestihl odpovědět včas.\n**Správná odpověď byla:** {correct_answers}",
                color=discord.Color.dark_gray()
            )
            await interaction.channel.send(embed=fail_embed)