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

# -------------------------------------------------------------------
# STARÉ TRÍDY PRO DYNAMICKÁ MENU (Potřebné pro main.py a persistent views)
# -------------------------------------------------------------------

class RoleModal(discord.ui.Modal, title='Vytvořit menu rolí'):
    title_input = discord.ui.TextInput(label='Nadpis Embedu', placeholder='VÝBÉR ROLÍ')
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

# -------------------------------------------------------------------
# NOVÝ SYSTÉM PRO BRAWL STARS RANKY
# -------------------------------------------------------------------

BRAWL_RANKS = {
    1464661112565006459: "Gold",
    1463231879414157446: "Diamond",
    1463232501949399164: "Mythic",
    1463232272164585474: "Legendary",
    1463232392281198776: "Masters",
    1463232574313988168: "PRO"
}

class RankSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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

        roles_to_remove = [
            guild.get_role(rid) for rid in BRAWL_RANKS.keys() 
            if rid != selected_role_id and guild.get_role(rid) in member.roles
        ]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)

        if selected_role in member.roles:
            await member.remove_roles(selected_role)
            await interaction.response.send_message(f"Odebral jsem ti rank: **{selected_role.name}**", ephemeral=True)
        else:
            await member.add_roles(selected_role)
            await interaction.response.send_message(f"Nastavil jsem ti rank: **{selected_role.name}** 🏆", ephemeral=True)

# -------------------------------------------------------------------
# DATABÁZE OTÁZEK PRO CHAT REVIVE
# -------------------------------------------------------------------

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
        {"q": "Jaká barva vznikne smícháním červené a bílé? 🎨", "a": ["ruzova"], "xp": 100},
        {"q": "Jak se jmenuje naše galaxie? 🌌", "a": ["mlecna draha", "mlecna"], "xp": 100},
        {"q": "Kolik je **7 x 6**? 🧮", "a": ["42"], "xp": 100},
        {"q": "Které zvíře je známé tím, že staví hráze z dřeva? 🦫", "a": ["bobr"], "xp": 100},
        {"q": "Jak se jmenuje sněhulák z pohádky Ledové království (Frozen)? ☃️", "a": ["olaf"], "xp": 100},
        {"q": "Kolik stran má trojúhelník? 🔺", "a": ["3", "tri"], "xp": 100},
        {"q": "Jaké je nejrychlejší suchozemské zvíře? 🐆", "a": ["gepard"], "xp": 100},
        {"q": "Jaká je státní hymna České republiky? 🎶", "a": ["kde domov muj", "kde domov moj"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **CHAT** pozpátku! 🔄", "a": ["tahc"], "xp": 100},
        {"q": "Který měsíc v roce je nejkratší? 📅", "a": ["unor"], "xp": 100},
        {"q": "Jaké ovoce je považováno za symbol společnosti Apple? 🍏", "a": ["jablko", "apple"], "xp": 100},
        {"q": "Která barva je na horním okraji klasické české vlajky? 🇨🇿", "a": ["bila"], "xp": 100},
        {"q": "Kolik prstů má člověk celkem na obou rukách? 🖐️", "a": ["10", "deset"], "xp": 100},
        {"q": "Jak se jmenuje zvíře, které nosí svůj domov na zádech? 🐚", "a": ["snek", "zelva"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **100 - 33**? 🧮", "a": ["67"], "xp": 100},
        {"q": "Z jaké látky včely vyrábějí sladký med? 🐝", "a": ["nektar"], "xp": 100},
        {"q": "Ve kterém století proběhla Bitva na Bílé hoře (1620)? ⚔️", "a": ["17", "17.", "sedmnactem"], "xp": 100},
        {"q": "Jaké dvě supervelmoci proti sobě stály během Studené války? ⚔️", "a": ["usa a sssr", "usa sssr", "usa a sovetsky svaz", "spojene staty a sovetsky svaz"], "xp": 100},
        {"q": "Jak se jmenoval rakouský arcivévoda, jehož atentát v Sarajevě rozpoutal 1. světovou válku? 👑", "a": ["frantisek ferdinand", "frantisek ferdinand d este", "ferdinand"], "xp": 100},
        {"q": "Kdo napsal slavnou divadelní hru Romeo a Julie? 🎭", "a": ["william shakespeare", "shakespeare"], "xp": 100},
        {"q": "Jak se jmenuje nejvyšší hora světa (nad mořem)? 🏔️", "a": ["mount everest", "everest"], "xp": 100},
        {"q": "Kolik komor má lidské srdce? 🫀", "a": ["4", "ctyri"], "xp": 100}
        {"q": "Jaká je nejznámější kryptoměna na světě? ₿", "a": ["bitcoin", "btc"], "xp": 100},
        {"q": "Které zvíře je známé tím, že mění barvy podle prostředí? 🦎", "a": ["chameleon"], "xp": 100},
        {"q": "Jak se jmenuje planeta, na které žijeme? 🌍", "a": ["zeme"], "xp": 100},
        {"q": "Kolik minut má půlhodina? ⏱️", "a": ["30", "tricet"], "xp": 100},
        {"q": "Jaké je nejznámější pečivo k párku v rohlíku nebo guláši? 🥖", "a": ["rohlik", "chleb", "chleba"], "xp": 100},
        {"q": "Jaké je hlavní město Itálie? 🇮🇹", "a": ["rim"], "xp": 100},
        {"q": "Jak se jmenuje zmrzlá voda? 🧊", "a": ["led"], "xp": 100},
        {"q": "Kolik ročních období máme za rok? 🍂", "a": ["4", "ctyri"], "xp": 100},
        {"q": "Který pták je symbolem mírnosti a nosí olivovou ratolest? 🕊️", "a": ["holubice", "holub"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **50 - 18**? 🧮", "a": ["32"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **PES** pozpátku! 🔄", "a": ["sep"], "xp": 100},
        {"q": "Jak se jmenuje žlutá část vajíčka? 🍳", "a": ["zloutek"], "xp": 100},
        {"q": "Kolik rohatých čertů obvykle doprovází Mikuláše? 👹", "a": ["cert"], "xp": 100},
        {"q": "Který měsíc v roce začíná školní rok? 🎒", "a": ["zari", "9"], "xp": 100},
        {"q": "Jaké zvíře dělá 'Mňau'? 🐱", "a": ["kocka"], "xp": 100},
        {"q": "Které ovoce je známé tím, že je žluté a zahnuté? 🍌", "a": ["banan"], "xp": 100},
        {"q": "Jak se jmenuje náš nejznámější hrad v Praze? 🏰", "a": ["prazsky hrad", "hradcany"], "xp": 100},
        {"q": "Kolik hodin má půl dne? ⏰", "a": ["12", "dvanact"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **9 x 9**? 🧮", "a": ["81"], "xp": 100},
        {"q": "Jaké barvy je sníh? ❄️", "a": ["bila", "bily"], "xp": 100},
        {"q": "Které zvíře má dlouhé uši a nosí podle pohádek velikonoční vajíčka? 🐰", "a": ["zajic", "kralik"], "xp": 100},
        {"q": "Jak se jmenuje nástroj, kterým zatloukáme hřebíky? 🔨", "a": ["kladivo"], "xp": 100},
        {"q": "Která hvězda je nejblíže k Zemi a svítí přes den? ☀️", "a": ["slunce"], "xp": 100},
        {"q": "Kolik nohou má člověk? 🦶", "a": ["2", "dve"], "xp": 100},
        {"q": "Jaké palivo tankujeme do většiny běžných aut (na 'B')? ⛽", "a": ["benzin"], "xp": 100},
        {"q": "Které zvíře má nejdelší krk na světě? 🦒", "a": ["zirafa"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **KÓD** pozpátku! 🔄", "a": ["dok"], "xp": 100},
        {"q": "Jak se jmenuje pohádková bytost s jedním rohem na čele? 🦄", "a": ["jednorozec"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **100 / 4**? 🧮", "a": ["25"], "xp": 100},
    ],
    "medium": [
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 250},
        {"q": "Jaké je hlavní město Slovenska? 🇸🇰", "a": ["bratislava"], "xp": 250},
        {"q": "Který je nejdelší orgán v lidském těle? 🧠", "a": ["tenke strevo", "strevo", "kuze"], "xp": 250},
        {"q": "Jaké je hlavní město Francie? 🇫🇷", "a": ["pariz"], "xp": 250},
        {"q": "Který pták neumí létat a žije na Antarktidě? 🐧", "a": ["tucnak"], "xp": 250},
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
        {"q": "Jaké je hlavní město Německa? 🇩🇪", "a": ["berlin"], "xp": 250},
        {"q": "Jaká je nejrozšířenější krevní skupina na světě? 🩸", "a": ["0", "0+", "o"], "xp": 250},
        {"q": "Kto napsal drama R.U.R., kde se poprvé objevilo slovo 'Robot'? 🤖", "a": ["karel capek", "capek"], "xp": 250},
        {"q": "Jaké město je hlavním městem Polska? 🇵🇱", "a": ["varsava"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **13 x 7**? 🧮", "a": ["91"], "xp": 250},
        {"q": "Která planetka byla dříve považována za 9. planetu Sluneční soustavy? 🌌", "a": ["pluto"], "xp": 250},
        {"q": "Kdo namaloval slavný obraz Mona Lisa? 🎨", "a": ["leonardo da vinci", "da vinci", "leonardo"], "xp": 250},
        {"q": "Který oceán omývá západní pobřeží USA? 🌊", "a": ["tichy", "tichy ocean", "pacifik"], "xp": 250},
        {"q": "Kolik hráčů tvoří jeden tým na hřišti při fotbalovém zápase? ⚽", "a": ["11", "jedenact"], "xp": 250},
        {"q": "Jaká je nejvyšší budova světa (v Dubaji)? 🏙️", "a": ["burj khalifa"], "xp": 250},
        {"q": "Ve kterém roce začala 1. světová válka? 📜", "a": ["1914"], "xp": 250},
        {"q": "Jaký je chemický symbol pro železo? 🧪", "a": ["fe"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **SERVER** pozpátku! 🔄", "a": ["revres"], "xp": 250},
        {"q": "Které moře odděluje Evropu od Afriky? 🌊", "a": ["stredozemni", "stredozemni more"], "xp": 250},
        {"q": "Jak se jmenuje největší ostrov světa? 🏝️", "a": ["gronsko"], "xp": 250},
        {"q": "Kolik hodin trvá jeden rok (365 x 24)? ⏰", "a": ["8760"], "xp": 250},
        {"q": "Ve kterém roce proběhla Bitva na Bílé hoře? ⚔️", "a": ["1620"], "xp": 250},
        {"q": "Která zeď byla hlavním symbolem rozdělení světa během Studené války? 🧱", "a": ["berlinska", "berlinska zed"], "xp": 250},
        {"q": "Jak se jmenoval český král ('zimní král') v době Bitvy na Bílé hoře? 👑", "a": ["fridrich falcky", "fridrich"], "xp": 250},
        {"q": "Ve kterém roce byla svržena atomová puma na Hirošimu? 💣", "a": ["1945"], "xp": 250},
        {"q": "Ve kterém roce vzniklo samostatné Československo po 1. světové válce? 🇨🇿", "a": ["1918"], "xp": 250},
        {"q": "Kdo byl prvním člověkem, který vstoupil na povrch Měsíce (1969)? 🌕", "a": ["neil armstrong", "armstrong"], "xp": 250},
        {"q": "Která krevní skupina je považována za univerzálního dárce? 🩸", "a": ["0-", "0 negativni", "0 minus", "0"], "xp": 250},
        {"q": "Který orgán je největším vnitřním orgánem lidského těla? 🫁", "a": ["jatra"], "xp": 250},
        {"q": "Kdo namaloval slavnou nástěnnou malbu 'Poslední večeře'? 🎨", "a": ["leonardo da vinci", "da vinci", "leonardo"], "xp": 250},
        {"q": "Který slavný nizozemský malíř si v záchvatu odřízl ucho? 🎨", "a": ["vincent van gogh", "van gogh", "gogh"], "xp": 250}
        {"q": "Který prvek má v periodické tabulce značku **O**? 🧪", "a": ["kyslik"], "xp": 250},
        {"q": "Ve kterém městě sídlí Evropská unie (hlavní sídlo)? 🇪🇺", "a": ["brusels", "brusel"], "xp": 250},
        {"q": "Jak se jmenuje největší mořský savec na světě? 🐋", "a": ["plejtvak obrovsky", "plejtvak", "valery"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **16 x 4**? 🧮", "a": ["64"], "xp": 250},
        {"q": "Který slavný skladatel byl hluchý a složil 9. symfonii (Ódu na radost)? 🎼", "a": ["beethoven", "ludwig van beethoven"], "xp": 250},
        {"q": "Jaké je hlavní město Španělska? 🇪🇸", "a": ["madrid"], "xp": 250},
        {"q": "Který orgán v těle pumpuje krev? 🫀", "a": ["srdce"], "xp": 250},
        {"q": "Ve kterém roce proběhla Sametová revoluce v Československu? 🕊️", "a": ["1989"], "xp": 250},
        {"q": "Jak se jmenuje nejznámější česká řeka protékající Prahou? 🌊", "a": ["vltava"], "xp": 250},
        {"q": "Jak se jmenuje věda o životě a živých organismech? 🧬", "a": ["biologie"], "xp": 250},
        {"q": "Která planeta je nejblíže k Slunci? 🪐", "a": ["merkur"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **PYTHON** pozpátku! 🔄", "a": ["nohtyp"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **225 / 5**? 🧮", "a": ["45"], "xp": 250},
        {"q": "Který český spisovatel napsal Babičku? 📖", "a": ["bozena nemcova", "nemcova"], "xp": 250},
        {"q": "Jaká je měna v Japonsku? 💴", "a": ["jen", "yen"], "xp": 250},
        {"q": "Která kostra chránící mozek se nachází v hlavě? 💀", "a": ["lebka"], "xp": 250},
        {"q": "Jak se jmenuje nejvyšší hora České republiky? 🏔️", "a": ["snezka"], "xp": 250},
        {"q": "Ve kterém státě se nachází šikmá věž v Pise? 🇮🇹", "a": ["italie"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **11 x 11**? 🧮", "a": ["121"], "xp": 250},
        {"q": "Který plyn vdechujeme a rostliny jej přeměňují na kyslík? 🌿", "a": ["oxid uhlicity", "co2"], "xp": 250},
        {"q": "Která země darovala USA Sochu Svobody? 🗽", "a": ["francie"], "xp": 250},
        {"q": "Jak se jmenuje největší pevninský savec na Zemi? 🐘", "a": ["slon", "slon africky"], "xp": 250},
        {"q": "Jaká je oficiální měna ve Velké Británii? 💷", "a": ["libra", "libra sterlinku"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **GAMING** pozpátku! 🔄", "a": ["gnimag"], "xp": 250},
        {"q": "Ve kterém měsíci se slaví Štědrý den? 🎄", "a": ["prosinec", "12"], "xp": 250},
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
        {"q": "Který panovník v roce 1348 založil univerzitu v Praze? 👑", "a": ["karel iv", "karel 4", "karel iv."], "xp": 500},
        {"q": "Jak se jmenuje nejvyšší činná sopka v Evropě? 🌋", "a": ["etna"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **17 x 17**? 🧮", "a": ["289"], "xp": 500},
        {"q": "Jaká je chemická značka pro sodík? 🧪", "a": ["na"], "xp": 500},
        {"q": "Jaké je hlavní město Nového Zélandu? 🇳🇿", "a": ["wellington"], "xp": 500},
        {"q": "Ve kterém roce padla Berlínská zeď? 🧱", "a": ["1989"], "xp": 500},
        {"q": "Která řeka protéká Londýnem? 🌊", "a": ["temze"], "xp": 500},
        {"q": "Která země je známá jako 'Země vycházejícího slunce'? 🇯🇵", "a": ["japonsko"], "xp": 500},
        {"q": "Kolik kostí má dospělé lidské tělo? 🦴", "a": ["206"], "xp": 500},
        {"q": "Jak se jmenuje největší vnitrozemské moře / jezero na světě? 🌊", "a": ["kaspicke more", "kaspicke"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **DISCORD** pozpátku! 🔄", "a": ["drocsid"], "xp": 500},
        {"q": "Které pohoří tvoří hranici mezi Evropou a Asií? 🏔️", "a": ["ural"], "xp": 500},
        {"q": "Jaké je hlavní město Švédska? 🇸🇪", "a": ["stockholm"], "xp": 500},
        {"q": "Který objevitel v roce 1492 dorazil do Ameriky? ⛵", "a": ["kristof kolumb", "kolumbus", "kristof kolumbus"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **1024 / 16**? 🧮", "a": ["64"], "xp": 500},
        {"q": "Jak se jmenovala válečná krize v roce 1962, kdy byl svět blízko jaderné válce? 🚀", "a": ["kubanska", "kubanska krize"], "xp": 500},
        {"q": "Jak se jmenovala dohoda z roku 1938, ve které velmoci podstoupily české pohraničí? 📜", "a": ["mnichovska dohoda", "mnichovska smlouva", "mnichovska"], "xp": 500},
        {"q": "V jakém měsíci roku 1918 byla podepsána kapitulace ukončující 1. světovou válku? 📅", "a": ["listopad", "11"], "xp": 500},
        {"q": "Jak se jmenoval spojenecký vojenský výsadek v Normandii v roce 1944 (Den D)? 🎖️", "a": ["operace overlord", "overlord"], "xp": 500},
        {"q": "Jak se jmenuje největší plošná/objemová sopka na Zemi (na Havaji)? 🌋", "a": ["mauna loa"], "xp": 500},
        {"q": "Který renesanční sochař vytvořil slavnou mramorovou sochu Davida? 🗿", "a": ["michelangelo", "michelangelo buonarroti"], "xp": 500},
        {"q": "Který orgán v lidském těle slouží k filtraci krve a tvorbě moči? 🫘", "a": ["ledviny", "ledvina"], "xp": 500},
        {"q": "Jak se jmenovala kosmická loď, se kterou Neil Armstrong přistál na Měsíci? 🚀", "a": ["apollo 11", "apollo"], "xp": 500}
        {"q": "Jaké je hlavní město Egypta? 🇪🇬", "a": ["kahira"], "xp": 500},
        {"q": "Který chemický prvek má značku **C**? 🧪", "a": ["uhlik"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **18 x 18**? 🧮", "a": ["324"], "xp": 500},
        {"q": "Jak se jmenuje náš první československý prezident? 🏛️", "a": ["tomas garrigue masaryk", "masaryk", "tgm"], "xp": 500},
        {"q": "Která řeka je nejdelší v Evropě? 🌊", "a": ["volha"], "xp": 500},
        {"q": "Jaké je hlavní město Číny? 🇨🇳", "a": ["peking", "beijing"], "xp": 500},
        {"q": "Který vědec objevil penicilin (první antibiotikum)? 🧫", "a": ["alexander fleming", "fleming"], "xp": 500},
        {"q": "Jaká je chemická značka pro měď? 🧪", "a": ["cu"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **ALGORITMUS** pozpátku! 🔄", "a": ["sumtirogla"], "xp": 500},
        {"q": "Ve kterém roce byla založena organizace OSN? 🌐", "a": ["1945"], "xp": 500},
        {"q": "Jaké je hlavní město Portugalska? 🇵🇹", "a": ["lisabon"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **512 / 8**? 🧮", "a": ["64"], "xp": 500},
        {"q": "Který hudební genij složil operu Kouzelná flétna? 🎼", "a": ["mozart", "wolfgang amadeus mozart"], "xp": 500},
        {"q": "Jak se nazývá proces přeměny kapaliny na plyn? 💨", "a": ["odparovani", "vyparovani"], "xp": 500},
        {"q": "Jaké je hlavní město Norska? 🇳🇴", "a": ["oslo"], "xp": 500},
        {"q": "Která planeta je známá svými výraznými prstenci? 🪐", "a": ["saturn"], "xp": 500},
        {"q": "Kdo je autorem slavného románu 1984? 📖", "a": ["george orwell", "orwell"], "xp": 500},
        {"q": "Jak se jmenuje největší mořský záliv na světě? 🌊", "a": ["mexicky zaliv", "benghalsky zaliv"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **19 x 19**? 🧮", "a": ["361"], "xp": 500},
        {"q": "Jaká je chemická značka pro uhlík? 🧪", "a": ["c"], "xp": 500},
        {"q": "Který český panovník byl přezdíván 'Otec vlasti'? 👑", "a": ["karel iv", "karel 4"], "xp": 500},
        {"q": "Jak se nazývá odborný název pro lidskou čelist (horní/dolní)? 🦴", "a": ["celist"], "xp": 500},
        {"q": "Jaké je hlavní město Maďarska? 🇭🇺", "a": ["budapest"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **DATABASE** pozpátku! 🔄", "a": ["esabatad"], "xp": 500},
        {"q": "Která vrstva atmosféry nás chráni před UV zářením? ☀️", "a": ["ozonova", "ozonova vrstva"], "xp": 500},
        {"q": "Které město v ČR je známé výrobou piva Pilsner Urquell? 🍺", "a": ["plzen"], "xp": 500},
        {"q": "Ve kterém roce vyhořelo Národní divadlo v Praze? 🎭", "a": ["1881"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **(25 x 4) + 150**? 🧮", "a": ["250"], "xp": 500},
        {"q": "Jaká je chemická značka pro kalcium (vápník)? 🧪", "a": ["ca"], "xp": 500},
        {"q": "Jaké je hlavní město Argentina? 🇦🇷", "a": ["buenos aires"], "xp": 500},
        {"q": "Jak se jmenuje nejznámější starověký řecký filosof (učitel Platóna)? 🏛️", "a": ["sokrates"], "xp": 500},
        {"q": "Která poušť se nachází v Mongolsku a Číně? 🏜️", "a": ["gobi"], "xp": 500},
        {"q": "Jak se jmenuje největší tepna v lidském těle? 🩸", "a": ["aorta"], "xp": 500},
    ],
    "ultrahard": [
        {"q": "Jaké je hlavní město Švýcarska? (Chyták: Oficiálně hlavní město nemá, ale faktickým sídlem je...)", "a": ["bern"], "xp": 1000},
        {"q": "Jaké je chemické označení/značka pro stříbro? 🧪", "a": ["ag"], "xp": 1000},
        {"q": "Ve kterém roce se potopil Titanic po srážce s ledovcem? 🚢", "a": ["1912"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **169**? 🧮", "a": ["13"], "xp": 1000},
        {"q": "Jaké je hlavní město Turecka? (Chyták: Istanbul to není!) 🇹🇷", "a": ["ankara"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **KONTRAREVOLUCE** pozpátku! 🔄", "a": ["eculoverartnok"], "xp": 1000},
        {"q": "Která je nejlidnatější vnitrozemská zem na světě (nemá přístup k moři)? 🌍", "a": ["etiopie"], "xp": 1000},
        {"q": "Který fyzik formuloval obecnou teorii relativity? 🧠", "a": ["albert einstein", "einstein"], "xp": 1000},
        {"q": "Jaké je hlavní město Maroka? 🇲🇦", "a": ["rabat"], "xp": 1000},
        {"q": "Kolik bitů tvoří jeden Byte (bajt)? 💻", "a": ["8", "osm"], "xp": 1000},
        {"q": "Jaké je hlavní město Vietnamu? 🇻🇳", "a": ["hanoj"], "xp": 1000},
        {"q": "Který chemický prvek má nejvyšší bod tání ze všech kovů? 💡", "a": ["volfram", "tungsten"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **2 na 10. mocninu (2^10)**? 🧮", "a": ["1024"], "xp": 1000},
        {"q": "Jaké je hlavní město Kazachstánu? 🇰🇿", "a": ["astana"], "xp": 1000},
        {"q": "Ve kterém roce byla podepsána Deklarace nezávislosti USA? 📜", "a": ["1776"], "xp": 1000},
        {"q": "Jak se jmenuje nejvzdálenější planeta od Slunce v naší soustavě? 🪐", "a": ["neptun"], "xp": 1000},
        {"q": "Které je největší jezero v České republice (podle rozlohy)? 🌊", "a": ["cerne jezero", "cerne"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **SYNCHROTRON** pozpátku! 🔄", "a": ["nortorhcnys"], "xp": 1000},
        {"q": "Jaká je nejlidnatější země Afrického kontinentu? 🇳🇬", "a": ["nigerie"], "xp": 1000},
        {"q": "Jak se jmenuje jediný známý savec, který klade vejce? 🦆", "a": ["ptakopysk"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **3^5 (3 na pátou)**? 🧮", "a": ["243"], "xp": 1000},
        {"q": "Jaké je hlavní město Islandu? 🇮🇸", "a": ["reykjavik"], "xp": 1000},
        {"q": "Jaká je základní jednotka elektrického proudu v soustavě SI? ⚡", "a": ["amper", "a"], "xp": 1000},
        {"q": "Který český šlechtic se po Bílé hoře stal vrchním velitelem císařských vojsk? ⚔️", "a": ["albrecht z valdstejna", "valdstejn"], "xp": 1000},
        {"q": "Jak se jmenoval sovětský vůdce během 2. světové války a počátku Studené války? 🏛️", "a": ["stalin", "josif stalin"], "xp": 1000},
        {"q": "Jak se nazývá vojenský pakt západních zemí založený v roce 1949? 🛡️", "a": ["nato", "severoatlanticka aliance"], "xp": 1000},
        {"q": "Jak se jmenovala krvavá bitva z roku 1916 u francouzského města v 1. světové válce? 🇫🇷", "a": ["verdun", "bitva u verdunu"], "xp": 1000},
        {"q": "Jak se jmenuje úplně nejvyšší sopka na Zemi (měřeno od základny na mořském dně)? 🌋", "a": ["mauna kea"], "xp": 1000},
        {"q": "Který český barokní malíř je známý svými temnými portréty a působil na dvoře v Praze? 🎨", "a": ["karel skreta", "skreta", "petr brandl", "brandl"], "xp": 1000},
        {"q": "Jaká je nejmenší kost v lidském těle (nachází se v uchu)? 🦴", "a": ["trminek"], "xp": 1000}
        {"q": "Jaké je hlavní město Jihoafrické republiky (výkonné sídlo)? 🇿🇦", "a": ["pretoria"], "xp": 1000},
        {"q": "Který prvek má v periodické tabulce značku **Hg**? 🧪", "a": ["rtut"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **625**? 🧮", "a": ["25"], "xp": 1000},
        {"q": "Jaké je hlavní město Íránu? 🇮🇷", "a": ["teheran"], "xp": 1000},
        {"q": "Která je nejhlubší sladkovodní jezero na světě (v Rusku)? 🌊", "a": ["bajkal"], "xp": 1000},
        {"q": "Jak se jmenuje nejmenší samostatný stát v Africe? 🌍", "a": ["gambie"], "xp": 1000},
        {"q": "Který fyzik objevil zákon všeobecné gravitace (jablko ze stromu)? 🍎", "a": ["isaac newton", "newton"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **KRYPTOGRAFIE** pozpátku! 🔄", "a": ["eifargotpyrk"], "xp": 1000},
        {"q": "Ve kterém roce proběhl první černý čtvrtek na newyorské burze (krize)? 📉", "a": ["1929"], "xp": 1000},
        {"q": "Jaké je hlavní město Finska? 🇫🇮", "a": ["helsinky", "helsinki"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **2 na 8. mocninu (2^8)**? 🧮", "a": ["256"], "xp": 1000},
        {"q": "Jaká je chemická značka pro draslík? 🧪", "a": ["k"], "xp": 1000},
        {"q": "Která země je největším producentem kávy na světě? ☕", "a": ["brazilie"], "xp": 1000},
        {"q": "Jak se nazývá nejtvrdší kosterní tkáň v těle (na zubech)? 🦷", "a": ["sklovina", "zubni sklovina"], "xp": 1000},
        {"q": "Jaké je hlavní město Thajska? 🇹🇭", "a": ["bangkok"], "xp": 1000},
        {"q": "Který renesanční astronom prohlásil, že Země obíhá kolem Slunce? 🌌", "a": ["mikulas kopernik", "kopernik", "galileo galilei"], "xp": 1000},
        {"q": "Který prvek má nejnižší hustotu ze všech plynů? 🎈", "a": ["vodik"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **13 x 13**? 🧮", "a": ["169"], "xp": 1000},
        {"q": "Jaké je hlavní město Indonésie? 🇮🇩", "a": ["djakartah", "jakarta"], "xp": 1000},
        {"q": "Ve kterém roce byl upálen Jan Hus v Kostnici? 📜", "a": ["1415"], "xp": 1000},
        {"q": "Jaká je nejvyšší hora Severní Ameriky (Denali)? 🏔️", "a": ["denali", "mount mckinley", "mckinley"], "xp": 1000},
        {"q": "Který chemický prvek má značku **Pb**? 🧪", "a": ["olovo"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **NEUROCHIRURGIE** pozpátku! 🔄", "a": ["eigrurohcruen"], "xp": 1000},
        {"q": "Jaké je hlavní město Filipín? 🇵🇭", "a": ["manila"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **400**? 🧮", "a": ["20"], "xp": 1000},
        {"q": "Která je nejdelší řeka v Severní Americe? 🌊", "a": ["missouri", "mississippi"], "xp": 1000},
        {"q": "Které město bylo zničeno výbuchem sopky Vesuv v roce 79 n. l.? 🌋", "a": ["pompeje"], "xp": 1000},
        {"q": "Jaká je základní jednotka síly v soustavě SI? ⚖️", "a": ["newton", "n"], "xp": 1000},
        {"q": "Jaké je hlavní město Kolumbie? 🇨🇴", "a": ["bogota"], "xp": 1000},
        {"q": "Která planeta má největší sopku ve Sluneční soustavě (Olympus Mons)? 🌋", "a": ["mars"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **15 x 12**? 🧮", "a": ["180"], "xp": 1000},
        {"q": "Jaký je nejstarší dosud fungující univerzita na světě (v Boloni)? 🏛️", "a": ["bolonska", "univerzita v boloni"], "xp": 1000},
        {"q": "Jaké je hlavní město Dánska? 🇩🇰", "a": ["kodan"], "xp": 1000},
        {"q": "Který prvek má chemickou značku **Fe**? 🧪", "a": ["zelezo"], "xp": 1000},
        {"q": "Ve kterém roce začala Velká francouzská revoluce? 📜", "a": ["1789"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **INFRASTRUKTURA** pozpátku! 🔄", "a": ["arutkurtsarfni"], "xp": 1000},
        {"q": "Jaké je hlavní město Saúdské Arábie? 🇸🇦", "a": ["rijad"], "xp": 1000},
        {"q": "Která část oka reaguje na světlo a dává oku barvu? 👁️", "a": ["duhovka"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **196**? 🧮", "a": ["14"], "xp": 1000},
        {"q": "Jaké je hlavní město Peru? 🇵🇪", "a": ["lima"], "xp": 1000},
    ]
}

# -------------------------------------------------------------------
# COG A PŘÍKAZY
# -------------------------------------------------------------------

class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Textový příkaz !role / !roles pro vytvoření Brawl Stars výběru
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

    @bot.tree.command(name="create-role-menu", description="Vytvoří interaktivní menu rolí")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create_role_menu(interaction: discord.Interaction):
        await interaction.response.send_modal(RoleModal())

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