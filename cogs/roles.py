import random
import asyncio
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands

# Pomocná funkce pro odstranění diakritiky
def normalize_text(text: str) -> str:
    text = text.lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# ID Brawl Stars Ranků
BRAWL_RANKS = {
    1464661112565006459: "Gold",
    1463231879414157446: "Diamond",
    1463232501949399164: "Mythic",
    1463232272164585474: "Legendary",
    1463232392281198776: "Masters",
    1463232574313988168: "PRO"
}

# View pro výběr Brawl Stars ranků (pro běžné hráče)
class RankSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # persistentní tlačítka / menu

    @discord.ui.select(
        placeholder="Vyber si svůj Brawl Stars Rank...",
        custom_id="brawl_stars_rank_select",
        options=[
            discord.SelectOption(label="Gold Rank", value="1464661112565006459", emoji="🟡"),
            discord.SelectOption(label="Diamond Rank", value="1463231879414157446", emoji="💎"),
            discord.SelectOption(label="Mythic Rank", value="1463232501949399164", emoji="🔴"),
            discord.SelectOption(label="Legendary Rank", value="1463232272164585474", emoji="🟡"),
            discord.SelectOption(label="Masters Rank", value="1463232392281198776", emoji="🟣"),
            discord.SelectOption(label="PRO Rank", value="1463232574313988168", emoji="⚡")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_role_id = int(select.values[0])
        guild = interaction.guild
        member = interaction.user
        
        selected_role = guild.get_role(selected_role_id)
        if not selected_role:
            await interaction.response.send_message("Tato role nebyla na serveru nalezena!", ephemeral=True)
            return

        # Najdeme všechny ostatní rank role, které uživatel má, a odebereme je (aby měl vždy max 1 rank)
        roles_to_remove = [
            guild.get_role(rid) for rid in BRAWL_RANKS.keys() 
            if rid != selected_role_id and guild.get_role(rid) in member.roles
        ]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)

        # Pokud už tuto roli měl, odebereme ji (přepínač), jinak ji přidáme
        if selected_role in member.roles:
            await member.remove_roles(selected_role)
            await interaction.response.send_message(f"Odebral jsem ti rank: **{selected_role.name}**", ephemeral=True)
        else:
            await member.add_roles(selected_role)
            await interaction.response.send_message(f"Nastavil jsem ti rank: **{selected_role.name}** 🏆", ephemeral=True)

# Databáze otázek pro Revive
QUESTIONS = {
    "easy": [
        {"q": "Jaké je hlavní město České republiky? 🇨🇿", "a": ["praha"], "xp": 100},
        {"q": "Kolik nohou má pavouk? 🕷️", "a": ["8", "osm"], "xp": 100},
        {"q": "Jaká je největší planeta naší sluneční soustavy? 🪐", "a": ["jupiter"], "xp": 100},
        {"q": "Které zvíře je známé jako 'král džungle'? 🦁", "a": ["lev"], "xp": 100},
        {"q": "Kolik hodin má jeden den? ⏰", "a": ["24", "dvacet ctyri"], "xp": 100},
        {"q": "Jakou barvu získáš smícháním modré a žluté? 🎨", "a": ["zelena", "zelenou"], "xp": 100},
        {"q": "Který oceán je největší na Zemi? 🌊", "a": ["tichy", "tichy ocean", "pacifik"], "xp": 100},
        {"q": "Jak se jmenuje mládě psa? 🐶", "a": ["stene"], "xp": 100},
        {"q": "Kolik dní má přestupný rok? 📅", "a": ["366"], "xp": 100},
        {"q": "Ve které zemi leží pyramidy v Gíze? 🇪🇬", "a": ["egypt"], "xp": 100},
        {"q": "Jaký plyn dýcháme, abychom přežili? 🌬️", "a": ["kyslik"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **15 + 27**? 🧮", "a": ["42"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **BOT** pozpátku! 🔄", "a": ["tob"], "xp": 100},
        {"q": "Jaká je chemická značka pro vodu? 💧", "a": ["h2o"], "xp": 100},
        {"q": "Které roční období následuje po zimě? 🌸", "a": ["jaro"], "xp": 100},
        {"q": "Kdo je hlavní postava v pohádce o Šípkové Růžence? 👑", "a": ["ruzenka", "sipkova ruzenka"], "xp": 100},
        {"q": "Kolik minut má jedna hodina? ⏱️", "a": ["60", "sedesat"], "xp": 100},
        {"q": "Které zvíře dává mléko a dělá 'Bůů'? 🐄", "a": ["krava"], "xp": 100},
        {"q": "Kolik světadílů je na Zemi? 🌍", "a": ["7", "sedm"], "xp": 100},
        {"q": "Jaká barva vznikne smícháním červené a bílé? 🎨", "a": ["ruzova"], "xp": 100}
    ],
    "medium": [
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 250},
        {"q": "Jaké je hlavní město Slovenska? 🇸🇰", "a": ["bratislava"], "xp": 250},
        {"q": "Který je nejdelší orgán v lidském těle? 🧠", "a": ["tenke strevo", "strevo", "kuze"], "xp": 250},
        {"q": "Jaké je hlavní město Francie? 🇫🇷", "a": ["pariz"], "xp": 250},
        {"q": "Který pták je známý tím, že neumí létat a žije na Antarktidě? 🐧", "a": ["tucnak"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **12 x 8**? 🧮", "a": ["96"], "xp": 250},
        {"q": "Jaké je nejsevernější hlavní město na světě? ❄️", "a": ["reykjavik"], "xp": 250},
        {"q": "Který kov je za pokojové teploty kapalný? 🧪", "a": ["rtut"], "xp": 250},
        {"q": "Jak se jmenuje nejvyšší hora Evropy? 🏔️", "a": ["elbrus", "mont blanc"], "xp": 250},
        {"q": "Kolik zubů má dospělý člověk (včetně zubů moudrosti)? 🦷", "a": ["32"], "xp": 250},
        {"q": "Ve kterém státě leží město Sydney? 🇦🇺", "a": ["australie"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **PLANETA** pozpátku! 🔄", "a": ["atenalp"], "xp": 250},
        {"q": "Která je nejdelší řeka světa? 🌊", "a": ["nil", "amazonka"], "xp": 250},
        {"q": "Kolik strun má standardní kytara? 🎸", "a": ["6", "sest"], "xp": 250},
        {"q": "Který plyn tvoří většinu atmosféry Země? 🌌", "a": ["dusik"], "xp": 250},
        {"q": "Jak se jmenuje proces, při kterém rostliny vyrábějí kyslík? 🌿", "a": ["fotosynteza"], "xp": 250},
        {"q": "Které město je známé jako 'Věčné město'? 🏛️", "a": ["rim"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **144 / 12**? 🧮", "a": ["12"], "xp": 250},
        {"q": "Který savec dokáže létat? 🦇", "a": ["netopyr"], "xp": 250},
        {"q": "Jaké je hlavní město Německa? 🇩🇪", "a": ["berlin"], "xp": 250}
    ],
    "hard": [
        {"q": "Jaké je hlavní město Austrálie? (Pozor, Sydney to není!) 🇦🇺", "a": ["canberra"], "xp": 500},
        {"q": "Který chemický prvek má značku **Au**? 🥇", "a": ["zlato"], "xp": 500},
        {"q": "Jak se jmenuje nejhlubší místo na Zemi? 🌊", "a": ["mariansky prikop", "marianska prikop"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **15 x 15**? 🧮", "a": ["225"], "xp": 500},
        {"q": "Jaké je hlavní město Kanady? 🇨🇦", "a": ["ottawa"], "xp": 500},
        {"q": "Jak se jmenuje největší poušť na světě (mimo polární)? 🏜️", "a": ["sahara"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **HYPERPROSTOR** pozpátku! 🔄", "a": ["rostorprepyh"], "xp": 500},
        {"q": "Která kost v lidském těle je nejdelší a nejsilnější? 🦴", "a": ["kost stehenni", "stehenni kost", "stehenni"], "xp": 500},
        {"q": "Jaké je hlavní město Brazílie? 🇧🇷", "a": ["brasilia"], "xp": 500},
        {"q": "Která planeta má nejvíce měsíců ve Sluneční soustavě? 🪐", "a": ["saturn"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **(45 + 55) x 3**? 🧮", "a": ["300"], "xp": 500},
        {"q": "Který stát má největší rozlohu na světě? 🗺️", "a": ["rusko"], "xp": 500},
        {"q": "Jak se nazývá nejtvrdší přírodní minerál? 💎", "a": ["diamant"], "xp": 500},
        {"q": "Jaká je nejmenší nezávislá země na světě? 🇻🇦", "a": ["vatikan"], "xp": 500},
        {"q": "Který panovník v roce 1348 založil univerzitu v Praze? 👑", "a": ["karel iv", "karel 4", "karel iv."], "xp": 500}
    ],
    "ultrahard": [
        {"q": "Jaké je hlavní město Švýcarska? (Chyták: Oficiálně hlavní město nemá, ale faktickým sídlem je...)", "a": ["bern"], "xp": 1000},
        {"q": "Jaké je chemické označení/značka pro stříbro? 🧪", "a": ["ag"], "xp": 1000},
        {"q": "Ve kterém roce potopil Titanic po srážce s ledovcem? 🚢", "a": ["1912"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **169**? 🧮", "a": ["13"], "xp": 1000},
        {"q": "Jaké je hlavní město Turecka? (Chyták: Istanbul to není!) 🇹🇷", "a": ["ankara"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **KONTRAREVOLUCE** pozpátku! 🔄", "a": ["eculoverartnok"], "xp": 1000},
        {"q": "Která je nejlidnatější vnitrozemská zem na světě (nemá přístup k moři)? 🌍", "a": ["etiopie"], "xp": 1000},
        {"q": "Který fyzik formuloval obecnou teorii relativity? 🧠", "a": ["albert einstein", "einstein"], "xp": 1000},
        {"q": "Jaké je hlavní město Maroka? 🇲🇦", "a": ["rabat"], "xp": 1000},
        {"q": "Kolik bitů tvoří jeden Byte (bajt)? 💻", "a": ["8", "osm"], "xp": 1000}
    ]
}

class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Příkaz !role nebo !roles – přístupný pro VŠECHNY hráče
    @commands.command(name="role", aliases=["roles"])
    async def role_cmd(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🌵 BRAWL STARS RANKY 🌵",
            description="Vyber si svůj aktuální rank v Brawl Stars z nabídky níže!",
            color=discord.Color.og_blurple()
        )
        embed.set_footer(text="Vybráním nového ranku se tvůj předchozí rank automaticky přepíše.")
        view = RankSelectView()
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(RolesCog(bot))

    @bot.tree.command(name="role", description="Vyber si svůj Brawl Stars rank")
    async def role_slash(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🌵 BRAWL STARS RANKY 🌵",
            description="Vyber si svůj aktuální rank v Brawl Stars z nabídky níže!",
            color=discord.Color.og_blurple()
        )
        embed.set_footer(text="Vybráním nového ranku se tvůj předchozí rank automaticky přepíše.")
        view = RankSelectView()
        await interaction.response.send_message(embed=embed, view=view)

    @bot.tree.command(name="revive", description="Spustí Chat Revive event s možností výběru obtížnosti")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="🟢 Easy (100 XP)", value="easy"),
        app_commands.Choice(name="🟡 Medium (250 XP)", value="medium"),
        app_commands.Choice(name="🔴 Hard (500 XP)", value="hard"),
        app_commands.Choice(name="🟣 Ultra Hard (1000 XP)", value="ultrahard")
    ])
    async def revive(interaction: discord.Interaction, difficulty: app_commands.Choice[str]):
        diff_key = difficulty.value
        question_data = random.choice(QUESTIONS[diff_key])
        
        chat_revive_role_id = 1475934465623588904
        
        colors = {
            "easy": discord.Color.green(),
            "medium": discord.Color.gold(),
            "hard": discord.Color.red(),
            "ultrahard": discord.Color.purple()
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