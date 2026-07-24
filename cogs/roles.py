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
# STARÉ TŘÍDY PRO DYNAMICKÁ MENU (Potřebné pro main.py a persistent views)
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
        {"q": "Kolik hodin má jeden den? ⏰", "a": ["24", "dvacet ctyri", "dvacet čtyři"], "xp": 100},
        {"q": "Jakou barvu získáš smícháním modré a žluté? 🎨", "a": ["zelena", "zelenou"], "xp": 100},
        {"q": "Který oceán je největší na Zemi? 🌊", "a": ["tichy", "tichy ocean", "tichý oceán", "pacifik"], "xp": 100},
        {"q": "Jak se jmenuje mládě psa? 🐶", "a": ["stene", "štěně"], "xp": 100},
        {"q": "Kolik dní má přestupný rok? 📅", "a": ["366"], "xp": 100},
        {"q": "Ve které zemi leží pyramidy v Gíze? 🇪🇬", "a": ["egypt"], "xp": 100},
        {"q": "Jaký plyn dýcháme, abychom přežili? 🌬️", "a": ["kyslik", "kyslík"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **15 + 27**? 🧮", "a": ["42"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **BOT** pozpátku! 🔄", "a": ["tob"], "xp": 100},
        {"q": "Jaká je chemická značka pro vodu? 💧", "a": ["h2o"], "xp": 100},
        {"q": "Které roční období následuje po zimě? 🌸", "a": ["jaro"], "xp": 100},
        {"q": "Kdo je hlavní postava v pohádce o Šípkové Růžence? 👑", "a": ["ruzenka", "růženka", "sipkova ruzenka", "šípková růženka"], "xp": 100},
        {"q": "Kolik minut má jedna hodina? ⏱️", "a": ["60", "sedesat", "šedesát"], "xp": 100},
        {"q": "Které zvíře dává mléko a dělá 'Bůů'? 🐄", "a": ["krava", "kráva"], "xp": 100},
        {"q": "Kolik světadílů je na Zemi? 🌍", "a": ["7", "sedm"], "xp": 100},
        {"q": "Jaká barva vznikne smícháním červené a bílé? 🎨", "a": ["ruzova", "růžová"], "xp": 100},
        {"q": "Jak se jmenuje naše galaxie? 🌌", "a": ["mlecna draha", "mléčná dráha", "mlecna", "mléčná"], "xp": 100},
        {"q": "Kolik je **7 x 6**? 🧮", "a": ["42"], "xp": 100},
        {"q": "Které zvíře je známé tím, že staví hráze ze dřeva? 🦫", "a": ["bobr"], "xp": 100},
        {"q": "Jak se jmenuje sněhulák z pohádky Ledové království (Frozen)? ☃️", "a": ["olaf"], "xp": 100},
        {"q": "Kolik stran má trojúhelník? 🔺", "a": ["3", "tri", "tři"], "xp": 100},
        {"q": "Jaké je nejrychlejší suchozemské zvíře? 🐆", "a": ["gepard"], "xp": 100},
        {"q": "Jaká je státní hymna České republiky? 🎶", "a": ["kde domov muj", "kde domov můj"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **CHAT** pozpátku! 🔄", "a": ["tahc"], "xp": 100},
        {"q": "Který měsíc v roce je nejkratší? 📅", "a": ["unor", "únor"], "xp": 100},
        {"q": "Jaké ovoce je považováno za symbol společnosti Apple? 🍏", "a": ["jablko", "apple"], "xp": 100},
        {"q": "Která barva je na horním pruhu české vlajky? 🇨🇿", "a": ["bila", "bílá"], "xp": 100},
        {"q": "Kolik prstů má človek celkem na obou rukách? 🖐️", "a": ["10", "deset"], "xp": 100},
        {"q": "Jak se jmenuje zvíře, které nosí svůj ulitu/domov na zádech? 🐚", "a": ["snek", "šnek", "zelva", "želva"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **100 - 33**? 🧮", "a": ["67"], "xp": 100},
        {"q": "Z jaké látky z květů včely vyrábějí med? 🐝", "a": ["nektar"], "xp": 100},
        {"q": "Ve kterém století proběhla Bitva na Bílé hoře (1620)? ⚔️", "a": ["17", "17.", "sedmnactem", "sedmnáctém"], "xp": 100},
        {"q": "Jaké dvě supervelmoci proti sobě stály během Studené války? ⚔️", "a": ["usa a sssr", "usa sssr", "usa a sovetsky svaz", "spojene staty a sovetsky svaz"], "xp": 100},
        {"q": "Jak se jmenoval rakouský arcivévoda, jehož atentát v Sarajevě rozpoutal 1. světovou válku? 👑", "a": ["frantisek ferdinand", "františek ferdinand", "frantisek ferdinand d este", "ferdinand"], "xp": 100},
        {"q": "Kdo napsal slavnou divadelní hru Romeo a Julie? 🎭", "a": ["william shakespeare", "shakespeare"], "xp": 100},
        {"q": "Jak se jmenuje nejvyšší hora světa (nad mořem)? 🏔️", "a": ["mount everest", "everest"], "xp": 100},
        {"q": "Kolik komor má lidské srdce? 🫀", "a": ["4", "ctyri", "čtyři"], "xp": 100},
        {"q": "Jaká je nejznámější kryptoměna na světě? ₿", "a": ["bitcoin", "btc"], "xp": 100},
        {"q": "Které zvíře je známé tím, že mění barvy podle prostředí? 🦎", "a": ["chameleon"], "xp": 100},
        {"q": "Jak se jmenuje planeta, na které žijeme? 🌍", "a": ["zeme", "země"], "xp": 100},
        {"q": "Kolik minut má půlhodina? ⏱️", "a": ["30", "tricet", "třicet"], "xp": 100},
        {"q": "Jaké je nejznámější české pečivo k párku v rohlíku nebo guláši? 🥖", "a": ["rohlik", "rohlík", "chleb", "chléb", "chleba"], "xp": 100},
        {"q": "Jaké je hlavní město Itálie? 🇮🇹", "a": ["rim", "řím"], "xp": 100},
        {"q": "Jak se jmenuje zmrzlá voda? 🧊", "a": ["led"], "xp": 100},
        {"q": "Kolik ročních období máme za rok? 🍂", "a": ["4", "ctyri", "čtyři"], "xp": 100},
        {"q": "Který pták je symbolem mírnosti a nosí olivovou ratolest? 🕊️", "a": ["holubice", "holub"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **50 - 18**? 🧮", "a": ["32"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **PES** pozpátku! 🔄", "a": ["sep"], "xp": 100},
        {"q": "Jak se jmenuje žlutá část vajíčka? 🍳", "a": ["zloutek", "žloutek"], "xp": 100},
        {"q": "Který měsíc v roce začíná školní rok? 🎒", "a": ["zari", "září", "9"], "xp": 100},
        {"q": "Jaké zvíře dělá 'Mňau'? 🐱", "a": ["kocka", "kočka"], "xp": 100},
        {"q": "Které ovoce je známé tím, že je žluté a zahnuté? 🍌", "a": ["banan", "banán"], "xp": 100},
        {"q": "Jak se jmenuje náš nejznámější hrad v Praze? 🏰", "a": ["prazsky hrad", "pražský hrad", "hradcany", "hradčany"], "xp": 100},
        {"q": "Kolik hodin má půl dne? ⏰", "a": ["12", "dvanact", "dvanáct"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **9 x 9**? 🧮", "a": ["81"], "xp": 100},
        {"q": "Jaké barvy je sníh? ❄️", "a": ["bila", "bílá", "bily", "bílý"], "xp": 100},
        {"q": "Které zvíře má dlouhé uši a nosí podle pohádek velikonoční vajíčka? 🐰", "a": ["zajic", "zajíc", "kralik", "králík"], "xp": 100},
        {"q": "Jak se jmenuje nástroj, kterým zatloukáme hřebíky? 🔨", "a": ["kladivo"], "xp": 100},
        {"q": "Která hvězda je nejblíže k Zemi a svítí přes den? ☀️", "a": ["slunce"], "xp": 100},
        {"q": "Kolik nohou má človek? 🦶", "a": ["2", "dve", "dvě"], "xp": 100},
        {"q": "Jaké palivo tankujeme do většiny běžných benzínových aut? ⛽", "a": ["benzin", "benzín"], "xp": 100},
        {"q": "Které zvíře má nejdelší krk na světě? 🦒", "a": ["zirafa", "žirafa"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš slovo **KÓD** pozpátku! 🔄", "a": ["dok"], "xp": 100},
        {"q": "Jak se jmenuje pohádková bytost s jedním rohem na čele? 🦄", "a": ["jednorozec", "jednorožec"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **100 / 4**? 🧮", "a": ["25"], "xp": 100}
    ],
    "medium": [
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 250},
        {"q": "Jaké je hlavní město Slovenska? 🇸🇰", "a": ["bratislava"], "xp": 250},
        {"q": "Který je nejdelší orgán v lidském těle? 🧠", "a": ["tenke strevo", "tenké střevo", "strevo", "střevo"], "xp": 250},
        {"q": "Jaké je hlavní město Francie? 🇫🇷", "a": ["pariz", "paříž"], "xp": 250},
        {"q": "Který pták neumí létat a žije na Antarktidě? 🐧", "a": ["tucnak", "tučňák"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **12 x 8**? 🧮", "a": ["96"], "xp": 250},
        {"q": "Jaké je nejsevernější hlavní město na světě? ❄️", "a": ["reykjavik", "reykjavík"], "xp": 250},
        {"q": "Který kov je za pokojové teploty kapalný? 🧪", "a": ["rtut", "rtuť"], "xp": 250},
        {"q": "Jak se jmenuje nejvyšší hora Evropy (pokud nepočítáme Kavkazy)? 🏔️", "a": ["mont blanc", "elbrus"], "xp": 250},
        {"q": "Kolik zubů má dospělý člověk (včetně zubů moudrosti)? 🦷", "a": ["32"], "xp": 250},
        {"q": "Ve kterém státě leží město Sydney? 🇦🇺", "a": ["australie", "austrálie"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **PLANETA** pozpátku! 🔄", "a": ["atenalp"], "xp": 250},
        {"q": "Která je nejdelší řeka světa? 🌊", "a": ["nil", "amazonka"], "xp": 250},
        {"q": "Kolik strun má standardní kytara? 🎸", "a": ["6", "sest", "šest"], "xp": 250},
        {"q": "Který plyn tvoří většinu atmosféry Země? 🌌", "a": ["dusik", "dusík"], "xp": 250},
        {"q": "Jak se jmenuje proces, při kterém rostliny vyrábějí kyslík? 🌿", "a": ["fotosynteza", "fotosyntéza"], "xp": 250},
        {"q": "Které město je známé jako 'Věčné město'? 🏛️", "a": ["rim", "řím"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **144 / 12**? 🧮", "a": ["12"], "xp": 250},
        {"q": "Který savec jako jediný dokáže aktivně létat? 🦇", "a": ["netopyr", "netopýr"], "xp": 250},
        {"q": "Jaké je hlavní město Německa? 🇩🇪", "a": ["berlin", "berlín"], "xp": 250},
        {"q": "Jaká je nejrozšířenější krevní skupina na světě? 🩸", "a": ["0", "0+", "o"], "xp": 250},
        {"q": "Kdo napsal drama R.U.R., kde se poprvé objevilo slovo 'Robot'? 🤖", "a": ["karel capek", "karel čapek", "capek", "čapek"], "xp": 250},
        {"q": "Jaké město je hlavním městem Polska? 🇵🇱", "a": ["varsava", "varšava"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **13 x 7**? 🧮", "a": ["91"], "xp": 250},
        {"q": "Která těleso bylo v roce 2006 vyřazeno ze seznamu planet Sluneční soustavy? 🌌", "a": ["pluto"], "xp": 250},
        {"q": "Kdo namaloval slavný obraz Mona Lisa? 🎨", "a": ["leonardo da vinci", "da vinci", "leonardo"], "xp": 250},
        {"q": "Který oceán omývá západní pobřeží USA? 🌊", "a": ["tichy", "tichý", "tichy ocean", "tichý oceán", "pacifik"], "xp": 250},
        {"q": "Kolik hráčů jednoho týmu je na hřišti při fotbalovém zápase? ⚽", "a": ["11", "jedenact", "jedenáct"], "xp": 250},
        {"q": "Jaká je nejvyšší budova světa (v Dubaji)? 🏙️", "a": ["burj khalifa"], "xp": 250},
        {"q": "Ve kterém roce začala 1. světová válka? 📜", "a": ["1914"], "xp": 250},
        {"q": "Jaký je chemický symbol pro železo? 🧪", "a": ["fe"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **SERVER** pozpátku! 🔄", "a": ["revres"], "xp": 250},
        {"q": "Které moře odděluje Evropu od Afriky? 🌊", "a": ["stredozemni", "středozemní", "stredozemni more", "středozemní moře"], "xp": 250},
        {"q": "Jak se jmenuje největší ostrov světa? 🏝️", "a": ["gronsko", "grónsko"], "xp": 250},
        {"q": "Ve kterém roce byla svržena atomová puma na Hirošimu? 💣", "a": ["1945"], "xp": 250},
        {"q": "Ve kterém roce vzniklo samostatné Československo po 1. světové válce? 🇨🇿", "a": ["1918"], "xp": 250},
        {"q": "Kdo byl prvním člověkem, který vstoupil na povrch Měsíce (1969)? 🌕", "a": ["neil armstrong", "armstrong"], "xp": 250},
        {"q": "Která krevní skupina je považována za univerzálního dárce? 🩸", "a": ["0-", "0 negativni", "0 negativní", "0 minus", "0"], "xp": 250},
        {"q": "Který orgán je největším vnitřním orgánem lidského těla? 🫁", "a": ["jatra", "játra"], "xp": 250},
        {"q": "Který slavný nizozemský malíř si v záchvatu odřízl ucho? 🎨", "a": ["vincent van gogh", "van gogh", "gogh"], "xp": 250},
        {"q": "Který prvek má v periodické tabulce značku **O**? 🧪", "a": ["kyslik", "kyslík"], "xp": 250},
        {"q": "Ve kterém městě sídlí Evropská komise a EU? 🇪🇺", "a": ["brusel", "brussels"], "xp": 250},
        {"q": "Jak se jmenuje největší živočich / savec na světě? 🐋", "a": ["plejtvak obrovsky", "plejtvák obrovský", "plejtvak", "plejtvák"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **16 x 4**? 🧮", "a": ["64"], "xp": 250},
        {"q": "Který slavný skladatel složil 9. symfonii i po úplné ztrátě sluchu? 🎼", "a": ["beethoven", "ludwig van beethoven"], "xp": 250},
        {"q": "Jaké je hlavní město Španělska? 🇪🇸", "a": ["madrid"], "xp": 250},
        {"q": "Ve kterém roce proběhla Sametová revoluce v Československu? 🕊️", "a": ["1989"], "xp": 250},
        {"q": "Jak se jmenuje nejznámější česká řeka protékající Prahou? 🌊", "a": ["vltava"], "xp": 250},
        {"q": "Jaká je měna v Japonsku? 💴", "a": ["jen", "yen"], "xp": 250},
        {"q": "Jak se nazývá kostěný obal mozku? 💀", "a": ["lebka"], "xp": 250},
        {"q": "Jak se jmenuje nejvyšší hora České republiky? 🏔️", "a": ["snezka", "sněžka"], "xp": 250},
        {"q": "Ve kterém státě se nachází šikmá věž v Pise? 🇮🇹", "a": ["italie", "itálie"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **11 x 11**? 🧮", "a": ["121"], "xp": 250},
        {"q": "Která země darovala USA Sochu Svobody? 🗽", "a": ["francie"], "xp": 250},
        {"q": "Jaká je oficiální měna ve Velké Británii? 💷", "a": ["libra", "libra sterlinku", "libra šterlinků"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **GAMING** pozpátku! 🔄", "a": ["gnimag"], "xp": 250}
    ],
    "hard": [
        {"q": "Jaké je hlavní město Austrálie? (Pozor, Sydney to není!) 🇦🇺", "a": ["canberra"], "xp": 500},
        {"q": "Který chemický prvek má značku **Au**? 🥇", "a": ["zlato"], "xp": 500},
        {"q": "Jak se jmenuje nejhlubší místo na Zemi? 🌊", "a": ["mariansky prikop", "mariánský příkop", "marianska prikop"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **15 x 15**? 🧮", "a": ["225"], "xp": 500},
        {"q": "Jaké je hlavní město Kanady? 🇨🇦", "a": ["ottawa"], "xp": 500},
        {"q": "Jak se jmenuje největší horká poušť na světě? 🏜️", "a": ["sahara"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **HYPERPROSTOR** pozpátku! 🔄", "a": ["rostorprepyh"], "xp": 500},
        {"q": "Která kost v lidském těle je nejdelší a nejsilnější? 🦴", "a": ["kost stehenni", "kost stehenní", "stehenni kost", "stehenní kost", "stehenni", "stehenní"], "xp": 500},
        {"q": "Jaké je hlavní město Brazílie? 🇧🇷", "a": ["brasilia", "brasília"], "xp": 500},
        {"q": "Která planeta má nejvíce potvrzených měsíců ve Sluneční soustavě? 🪐", "a": ["saturn"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **(45 + 55) x 3**? 🧮", "a": ["300"], "xp": 500},
        {"q": "Který stát má největší rozlohu na světě? 🗺️", "a": ["rusko"], "xp": 500},
        {"q": "Jak se nazývá nejtvrdší přírodní minerál? 💎", "a": ["diamant"], "xp": 500},
        {"q": "Jaká je nejmenší nezávislá země na světě? 🇻🇦", "a": ["vatikan", "vatikán"], "xp": 500},
        {"q": "Který panovník v roce 1348 založil univerzitu v Praze? 👑", "a": ["karel iv", "karel 4", "karel iv."], "xp": 500},
        {"q": "Jak se jmenuje nejvyšší činná sopka v Evropě? 🌋", "a": ["etna"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **17 x 17**? 🧮", "a": ["289"], "xp": 500},
        {"q": "Jaká je chemická značka pro sodík? 🧪", "a": ["na"], "xp": 500},
        {"q": "Jaké je hlavní město Nového Zélandu? 🇳🇿", "a": ["wellington"], "xp": 500},
        {"q": "Ve kterém roce padla Berlínská zeď? 🧱", "a": ["1989"], "xp": 500},
        {"q": "Která řeka protéká Londýnem? 🌊", "a": ["temze", "temže"], "xp": 500},
        {"q": "Která země je známá jako 'Země vycházejícího slunce'? 🇯🇵", "a": ["japonsko"], "xp": 500},
        {"q": "Kolik kostí má dospělé lidské tělo? 🦴", "a": ["206"], "xp": 500},
        {"q": "Jak se jmenuje největší vnitrozemská vodní plocha / jezero na světě? 🌊", "a": ["kaspicke more", "kaspické moře", "kaspik"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **DISCORD** pozpátku! 🔄", "a": ["drocsid"], "xp": 500},
        {"q": "Které pohoří tvoří tradicní hranici mezi Evropou a Asií? 🏔️", "a": ["ural"], "xp": 500},
        {"q": "Jaké je hlavní město Švédska? 🇸🇪", "a": ["stockholm"], "xp": 500},
        {"q": "Který objevitel v roce 1492 doplul do Ameriky? ⛵", "a": ["kristof kolumb", "krištof kolumbus", "kolumbus", "kristof kolumbus"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **1024 / 16**? 🧮", "a": ["64"], "xp": 500},
        {"q": "Jak se jmenovala karibská krize z roku 1962 ohledně raket na Kubě? 🚀", "a": ["kubanska", "kubánská", "kubanska krize", "kubánská krize"], "xp": 500},
        {"q": "Jak se jmenovala dohoda z roku 1938, ve které velmoci podstoupily české pohraničí Nemecku? 📜", "a": ["mnichovska dohoda", "mnichovská dohoda", "mnichovska", "mnichovská"], "xp": 500},
        {"q": "Jak se jmenoval spojenecký vojenský výsadek v Normandii v roce 1944 (Den D)? 🎖️", "a": ["operace overlord", "overlord"], "xp": 500},
        {"q": "Který renesanční sochař vytvořil mramorovou sochu Davida? 🗿", "a": ["michelangelo", "michelangelo buonarroti"], "xp": 500},
        {"q": "Který orgán v lidském těle slouží k filtraci krve a tvorbě moči? 🫘", "a": ["ledviny", "ledvina"], "xp": 500},
        {"q": "Jak se jmenovala kosmická loď, se kterou misí Neil Armstrong přistál na Měsíci? 🚀", "a": ["apollo 11", "apollo"], "xp": 500},
        {"q": "Jaké je hlavní město Egypta? 🇪🇬", "a": ["kahira", "káhira"], "xp": 500},
        {"q": "Který chemický prvek má značku **C**? 🧪", "a": ["uhlik", "uhlík"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **18 x 18**? 🧮", "a": ["324"], "xp": 500},
        {"q": "Jak se jmenuje náš první československý prezident? 🏛️", "a": ["tomas garrigue masaryk", "tomáš garrigue masaryk", "masaryk", "tgm"], "xp": 500},
        {"q": "Která řeka je nejdelší v Evropě? 🌊", "a": ["volha"], "xp": 500},
        {"q": "Jaké je hlavní město Číny? 🇨🇳", "a": ["peking", "beijing"], "xp": 500},
        {"q": "Který vědec objevil penicilin? 🧫", "a": ["alexander fleming", "fleming"], "xp": 500},
        {"q": "Jaká je chemická značka pro měď? 🧪", "a": ["cu"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **ALGORITMUS** pozpátku! 🔄", "a": ["sumtirogla"], "xp": 500},
        {"q": "Ve kterém roce byla založena organizace OSN? 🌐", "a": ["1945"], "xp": 500},
        {"q": "Jaké je hlavní město Portugalska? 🇵🇹", "a": ["lisabon"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **512 / 8**? 🧮", "a": ["64"], "xp": 500},
        {"q": "Který hudební genij složil operu Kouzelná flétna? 🎼", "a": ["mozart", "wolfgang amadeus mozart"], "xp": 500},
        {"q": "Jak se nazývá přechod skupenství z kapaliny na plyn za jakékoliv teploty? 💨", "a": ["odparovani", "odpařování", "vyparovani", "vypařování"], "xp": 500},
        {"q": "Jaké je hlavní město Norska? 🇳🇴", "a": ["oslo"], "xp": 500},
        {"q": "Kdo je autorem slavného antiutopického románu 1984? 📖", "a": ["george orwell", "orwell"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **19 x 19**? 🧮", "a": ["361"], "xp": 500},
        {"q": "Jaké je hlavní město Maďarska? 🇭🇺", "a": ["budapest", "budapešť"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **DATABASE** pozpátku! 🔄", "a": ["esabatad"], "xp": 500},
        {"q": "Která vrstva atmosféry nás chrání před škodlivým UV zářením? ☀️", "a": ["ozonova", "ozónová", "ozonova vrstva", "ozónová vrstva"], "xp": 500},
        {"q": "Ve kterém roce poprvé vyhořelo Národní divadlo v Praze? 🎭", "a": ["1881"], "xp": 500},
        {"q": "Rychlá matematika: Kolik je **(25 x 4) + 150**? 🧮", "a": ["250"], "xp": 500},
        {"q": "Jaká je chemická značka pro vápník (kalcium)? 🧪", "a": ["ca"], "xp": 500},
        {"q": "Jaké je hlavní město Argentiny? 🇦🇷", "a": ["buenos aires"], "xp": 500},
        {"q": "Jak se jmenoval slavný starověký řecký filosof, učitel Platóna? 🏛️", "a": ["sokrates", "sókratés"], "xp": 500},
        {"q": "Jak se jmenuje hlavní tepna lidského těla vycházející ze srdce? 🩸", "a": ["aorta"], "xp": 500}
    ],
    "ultrahard": [
        {"q": "Jaké je de facto hlavní (sídlem vlády) město Švýcarska? (Pozor, de jure oficiální nemá!) 🇨🇭", "a": ["bern"], "xp": 1000},
        {"q": "Která země je nejlidnatějším vnitrozemským státem na světě (nemá přístup k moři)? 🌍", "a": ["etiopie"], "xp": 1000},
        {"q": "Jaká je přesná rychlost světla ve vakuu v km/s? (Zaokrouhleno na celá čísla) ⚡", "a": ["299792", "299 792"], "xp": 1000},
        {"q": "Jak se jmenovala tajná operace atentátu na Reinharda Heydricha v roce 1942? 🎖️", "a": ["anthropoid", "operace anthropoid"], "xp": 1000},
        {"q": "Který fyzik jako první v roce 1932 objevil neutron? ⚛️", "a": ["james chadwick", "chadwick"], "xp": 1000},
        {"q": "Jaká je chemická značka pro draslík (Kalium)? 🧪", "a": ["k"], "xp": 1000},
        {"q": "Jaká je chemická značka pro wolfram? 🧪", "a": ["w"], "xp": 1000},
        {"q": "Jaká je chemická značka pro rtuť (Hydrargyrum)? 🧪", "a": ["hg"], "xp": 1000},
        {"q": "Jaká je chemická značka pro olovo (Plumbum)? 🧪", "a": ["pb"], "xp": 1000},
        {"q": "Jaká je chemická značka pro stříbro (Argentum)? 🧪", "a": ["ag"], "xp": 1000},
        {"q": "Ve kterém roce začala Stoletá válka mezi Anglií a Francií? ⚔️", "a": ["1337"], "xp": 1000},
        {"q": "Jak se jmenuje nejhlubší bod Mariánského příkopu? 🌊", "a": ["challengeruv prohluben", "challengerova prohluben", "challenger deep", "challenger"], "xp": 1000},
        {"q": "Který filosof a matematik formuloval větu 'Cogito, ergo sum'? 🧠", "a": ["rene descartes", "rené descartes", "descartes"], "xp": 1000},
        {"q": "Jak se jmenuje nejmenší kost v lidském těle (ve středním uchu)? 🦴", "a": ["strminek", "třmínek", "strmínek"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **17 x 19**? 🧮", "a": ["323"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **1024**? 🧮", "a": ["32"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je **2 na osmou (2^8)**? 🧮", "a": ["256"], "xp": 1000},
        {"q": "Rychlá matematika: Kolik je odmocnina ze **169**? 🧮", "a": ["13"], "xp": 1000},
        {"q": "Jaké je zákonodárné hlavní město Jihoafrické republiky (JAR)? 🇿🇦", "a": ["kapske mesto", "kapské město", "cape town"], "xp": 1000},
        {"q": "Které město bylo hlavním městem Kazachstánu před Astanou (do r. 1997)? 🇰🇿", "a": ["almaty", "alma-ata", "alma ata"], "xp": 1000},
        {"q": "Který král Anglie založil anglikánskou církev a měl celkem 6 manželek? 👑", "a": ["jindrich viii", "jindřich viii", "jindrich 8", "jindřich 8", "henry viii"], "xp": 1000},
        {"q": "Jak se jmenuje největší aktivní sopka na světě podle objemu/rozlohy (na Havaji)? 🌋", "a": ["mauna loa"], "xp": 1000},
        {"q": "Jak se nazývá úžina oddělující Španělsko a Maroko (vstup do Středozemního moře)? 🌊", "a": ["gibraltarska uzina", "gibraltarská úžina", "gibraltar"], "xp": 1000},
        {"q": "Jaké je hlavní město Maroka? 🇲🇦", "a": ["rabat"], "xp": 1000},
        {"q": "Jaké je hlavní město Mongolsko? 🇲🇳", "a": ["ulanbatar", "ulánbátar", "ulan batar"], "xp": 1000},
        {"q": "Jaké je hlavní město Turecka? (Pozor, Istanbul to není!) 🇹🇷", "a": ["ankara"], "xp": 1000},
        {"q": "Jaké je hlavní město Vietnamu? 🇻🇳", "a": ["hanoj", "hanoi"], "xp": 1000},
        {"q": "Jaké je hlavní město Keni? 🇰🇪", "a": ["nairobi"], "xp": 1000},
        {"q": "Jaké je hlavní město Lichtenštejunska? 🇱🇮", "a": ["vaduz"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **NEJNEOBHOSPODAŘOVATELNĚJŠÍMI** pozpátku! 🔄", "a": ["imijsotelavodapsohboennejen"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **RESTRUKTURALIZACE** pozpátku! 🔄", "a": ["ecazilarutkurtser"], "xp": 1000},
        {"q": "Jak se jmenuje slavná Shakespeareova hra, kde vystupuje princezna Dánska a zazní část 'Být, či nebýt'? 🎭", "a": ["hamlet"], "xp": 1000},
        {"q": "Který britský evoluční biolog napsal v roce 1976 přelomovou knihu 'Sebedestruktivní / Sobecký gen' (The Selfish Gene)? 🧬", "a": ["richard dawkins", "dawkins"], "xp": 1000},
        {"q": "Jak se jmenuje postava z Shakespearova Kupce benátského, která požadovala liber masa jako splátku dluhu? 🎭", "a": ["shylock"], "xp": 1000},
        {"q": "Který francouzský osvícenský filozof a spisovatel napsal satirický román Candide? 📖", "a": ["voltaire"], "xp": 1000},
        {"q": "Který rakouský fyzik zformuloval myšlenkový experiment s kočkou v krabici, která je zároveň živá i mrtvá? 🐱", "a": ["erwin schrodinger", "erwin schrödinger", "schrodinger", "schrödinger"], "xp": 1000},
        {"q": "Který antický dramatik napsal tragédii Oidipus rex (Král Oidipus)? 🎭", "a": ["sofokles", "sofoklés"], "xp": 1000},
        {"q": "Ve kterém přesném roce proběhla Bitva na Bílé hoře? ⚔️", "a": ["1620"], "xp": 1000},
        {"q": "Který císař Svaté říše římské vládl během Bitvy na Bílé hoře a potlačil české stavovské povstání? 👑", "a": ["ferdinand ii", "ferdinand ii.", "ferdinand 2"], "xp": 1000},
        {"q": "Jak se jmenoval mírový traktát z roku 1648, který oficiálně ukončil Třicetiletou válku v Evropě? 📜", "a": ["vestfalsky mir", "vestfálský mír"], "xp": 1000},
        {"q": "Která významná operace RAF v roce 1943 zničila přehrady v německém Porúří pomocí 'skákajících bomb'? 💣", "a": ["chastise", "operace chastise", "dambusters"], "xp": 1000},
        {"q": "Jak se jmenovala linie opevnění, kterou Francie postavila na hranicích s Německem před 2. světovou válkou? 🛡️", "a": ["maginotova linie", "maginotova"], "xp": 1000},
        {"q": "Ve kterém roce proběhla invaze vojsk Varšavské smlouvy do Československa (Operace Dunaj)? 🪖", "a": ["1968"], "xp": 1000},
        {"q": "Jak se jmenovala první umělá družice Země vypuštěná SSSR v roce 1957, která zahájila vesmírné závody Studené války? 🛰️", "a": ["sputnik 1", "sputnik"], "xp": 1000},
        {"q": "Jak se jmenoval sovětský vůdce, který vedl SSSR během Karibské krize v roce 1962? 🏛️", "a": ["nikita chruscov", "nikita chruščov", "chruscov", "chruščov"], "xp": 1000},
        {"q": "Které německé město bylo po 2. světové válce rozděleno do 4 okupačních sektorů a v roce 1961 v něm vyrostla zeď? 🧱", "a": ["berlin", "berlín"], "xp": 1000},
        {"q": "Který americký prezident pronesl v roce 1987 u Berlínské zdi slavnou větu: 'Mister Gorbachev, tear down this wall!'? 🎙️", "a": ["ronald reagan", "reagan"], "xp": 1000},        
        {"q": "Jaká je časová složitost v nejhorším případě (Worst-case) u algoritmu QuickSort v O-notaci? 💻", "a": ["o(n^2)", "o(n2)", "o(n**2)"], "xp": 1000},
        {"q": "Který britský matematik je považován za otce moderní počítačové vědy a prolomil kód Enigma? 🧠", "a": ["alan turing", "turing"], "xp": 1000},
        {"q": "Jak se jmenuje princip v objektově orientovaném programování, kdy třída přebírá vlastnosti a metody jiné třídy? 🏗️", "a": ["dedicnost", "dědičnost", "inheritance"], "xp": 1000},
        {"q": "Který port se standardně používá pro zabezpečený protokol HTTPS? 🔒", "a": ["443"], "xp": 1000},
        {"q": "Jak se jmenuje datová struktura typu LIFO (Last In, First Out)? 📚", "a": ["zasobnik", "zásobník", "stack"], "xp": 1000},
        {"q": "Který programovací jazyk vytvořil Guido van Rossum v roce 1991? 🐍", "a": ["python"], "xp": 1000},
        {"q": "Jak se nazývá stav v multithreadingu, kdy dva nebo více procesů čekají jeden na druhého a ani jeden nemůže pokračovat? 🛑", "a": ["deadlock", "uviznuti", "uvíznutí"], "xp": 1000},
        {"q": "Kolik bitů obsahuje přesně jeden byte (bajt)? 🔢", "a": ["8"], "xp": 1000},
        {"q": "Jak se jmenuje architektura operačních systémů, kde celé jádro běží v jednom velkém paměťovém prostoru (opak mikrojádra)? ⚙️", "a": ["monoliticke jadro", "monolitické jádro", "monolit", "monolith"], "xp": 1000},
        {"q": "Který příkaz v Git slouží k sloučení změn z jedné větve do druhé? 🔀", "a": ["git merge", "merge"], "xp": 1000}
    ],
    "football": [
        {"q": "Kolik minut trvá standardní fotbalový zápas bez prodloužení? ⏱️", "a": ["90"], "xp": 150},
        {"q": "Který národní tým vyhrál Mistrovství světa ve fotbale v roce 2022 v Kataru? 🏆", "a": ["argentina"], "xp": 300},
        {"q": "Který hráč získal v historii nejvíce Zlatých míčů (Ballon d'Or)? ⚽", "a": ["lionel messi", "messi"], "xp": 250},
        {"q": "Jak se jmenuje slavný fotbalový stadion klubu Real Madrid? 🏟️", "a": ["santiago bernabeu", "bernabeu", "santiago bernabéu"], "xp": 400},
        {"q": "Který klub vyhrál nejvíce titulů v Lize mistrů (Champions League)? 🏆", "a": ["real madrid", "real"], "xp": 300},
        {"q": "Který český fotbalista získal v roce 2003 Zlatý míč? 🇨🇿", "a": ["pavel nedved", "pavel nedvěd", "nedved", "nedvěd"], "xp": 400},
        {"q": "Která země uspořádala vůbec první Mistrovství světa ve fotbale v roce 1930? 🇺🇾", "a": ["uruguay"], "xp": 600},
        {"q": "Který fotbalový klub má přezdívku 'Red Devils' (Rudí ďáblové)? 🔴", "a": ["manchester united", "man utd", "mufc"], "xp": 350},
        {"q": "Jak se jmenuje pravidlo, které zakazuje útočníkovi být za posledním obráncem v momentě přihrávky? 🚩", "a": ["ofsajd", "offside", "mimo hru"], "xp": 200},
        {"q": "Jak se jmenuje slavný brazilský fotbalista, přezdívaný 'Král fotbalu', který zemřel v roce 2022? 🇧🇷", "a": ["pele", "pelé"], "xp": 300},
        {"q": "Který anglický klub dokázal vyhrát Premier League v sezóně 2003/04 bez jediné porážky ('Invincibles')? 🏆", "a": ["arsenal", "arsenal fc"], "xp": 500},
        {"q": "Kdo je historicky nejlepší střelec v historii Ligy mistrů? ⚽", "a": ["cristiano ronaldo", "ronaldo", "cr7"], "xp": 350},
        {"q": "Ve kterém městě sídlí fotbalový klub Borussia Dortmund? 🇩🇪", "a": ["dortmund"], "xp": 200},
        {"q": "Jak se jmenuje slavné derby mezi Realem Madrid a FC Barcelona? 🇪🇸", "a": ["el clasico", "el clásico", "clasico"], "xp": 300},
        {"q": "Který manažer vedl Manchester United neuvěřitelných 26 let (1986–2013)? 👔", "a": ["alex ferguson", "sir alex ferguson", "ferguson"], "xp": 450},
        {"q": "Který stát vyhrál Euro 2004 jako absolutní outsider po finálové výhře nad Portugalskem? 🇬🇷", "a": ["recko", "řecko"], "xp": 450},
        {"q": "Který fotbalový klub je známý pod přezdívkou 'Stará dáma' (La Vecchia Signora)? 🇮🇹", "a": ["juventus", "juventus turin", "juventus turín"], "xp": 350},
        {"q": "Ve kterém roce vyhrála Chelsea poprvé v historii Ligu mistrů (po penaltách proti Bayernu)? 🏆", "a": ["2012"], "xp": 500},
        {"q": "Který český klub si v sezóně 1995/96 zahrál finále Poháru UEFA? 🇨🇿", "a": ["slavia", "slavia praha"], "xp": 500},
        {"q": "Ve kterém francouzském klubu odstartoval svou evropskou kariéru Ronaldinho před přestupem do Barcy? 🇫🇷", "a": ["psg", "paris saint-germain", "paris saint germain"], "xp": 500},
        {"q": "Jak se jmenoval slavný nizozemský fotbalista a trenér, který je považován za otce 'totálního fotbalu'? 🇳🇱", "a": ["johan cruyff", "cruyff", "cruijff"], "xp": 500},
        {"q": "Která země vyhrála historicky nejvíce titulů na Mistrovství světa (celkem 5)? 🟡🟢", "a": ["brazilie", "brazílie"], "xp": 300},
        {"q": "Který brankář jako jediný v historii získal Zlatý míč (v roce 1963)? 🧤", "a": ["lev jasin", "lev jašin", "jasin", "jašin"], "xp": 600},
        {"q": "Jak se jmenuje oficiální hymna anglického klubu Liverpool FC? 🔴", "a": ["youll never walk alone", "you'll never walk alone", "ynwa"], "xp": 400},
        {"q": "Který stadion má největší kapacitu v Evropě (přes 99 000 diváků)? 🏟️", "a": ["camp nou", "spotify camp nou"], "xp": 450}
    ]
}

# -------------------------------------------------------------------
# CHAT REVIVE COG TŘÍDA
# -------------------------------------------------------------------

class ChatReviveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_questions = {}

    @app_commands.command(name="revive", description="Spustí kvízovou otázku pro oživení chatu")
    @app_commands.choices(difficulty=[
    app_commands.Choice(name="🎲 Náhodná obtížnost", value="random"),
    app_commands.Choice(name="🟢 Lehká (Easy)", value="easy"),
    app_commands.Choice(name="🟡 Střední (Medium)", value="medium"),
    app_commands.Choice(name="🔴 Těžká (Hard)", value="hard"),
    app_commands.Choice(name="🟣 Ultra Těžká (Ultra Hard)", value="ultrahard"),
    app_commands.Choice(name="⚽ Fotbalové", value="fotball")
])
    async def revive(self, interaction: discord.Interaction, difficulty: str = "random"):
        channel_id = interaction.channel.id
        
        if self.active_questions.get(channel_id, False):
            await interaction.response.send_message("V tomto kanálu už běží jedna otázka!", ephemeral=True)
            return

        # Určení obtížnosti (buď zvolená, nebo náhodná)
        if difficulty == "random":
            rand_val = random.random()
            if rand_val < 0.40:
                selected_diff = "easy"
            elif rand_val < 0.75:
                selected_diff = "medium"
            elif rand_val < 0.95:
                selected_diff = "hard"
            else:
                selected_diff = "ultrahard"
        else:
            selected_diff = difficulty

        # Nastavení vizuálu podle vybrané obtížnosti
        diff_config = {
            "easy": ("🟢 LEHKÁ", discord.Color.green()),
            "medium": ("🟡 STREDNÍ", discord.Color.gold()),
            "hard": ("🔴 TĚŽKÁ", discord.Color.red()),
            "ultrahard": ("🟣 ULTRA TĚŽKÁ", discord.Color.purple())
        }
        
        diff_label, color = diff_config[selected_diff]

        question_data = random.choice(QUESTIONS[selected_diff])
        question_text = question_data["q"]
        correct_answers = question_data["a"]
        xp_reward = question_data["xp"]

        embed = discord.Embed(
            title="⚡ CHAT REVIVE - KVÍZ ⚡",
            description=f"**{question_text}**\n\nNapiš odpověď přímo do chatu!\n*(Máš na to 5 minut)*",
            color=color
        )
        embed.add_field(name="Obtížnost", value=diff_label, inline=True)
        embed.add_field(name="Odměna", value=f"**+{xp_reward} XP**", inline=True)
        embed.set_footer(text="První správná odpověď vyhrává!")

        await interaction.response.send_message(embed=embed)
        self.active_questions[channel_id] = True

        def check(message: discord.Message):
            if message.channel.id != channel_id or message.author.bot:
                return False
            user_ans = normalize_text(message.content)
            return any(ans in user_ans for ans in correct_answers)

        try:
            winner_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
        except asyncio.TimeoutError:
            self.active_questions[channel_id] = False
            timeout_embed = discord.Embed(
                title="⏰ Čas vypršel!",
                description=f"Nikdo neodpověděl správně.\nSprávná odpověď byla: **{correct_answers[0].capitalize()}**",
                color=discord.Color.dark_gray()
            )
            await interaction.channel.send(embed=timeout_embed)
            return

        self.active_questions[channel_id] = False

        # Odměnění výherce XP přes Leveling Cog (pokud existuje)
        level_cog = self.bot.get_cog("LevelingCog")
        if level_cog and hasattr(level_cog, "add_xp"):
            await level_cog.add_xp(winner_msg.author, xp_reward, interaction.channel)

        win_embed = discord.Embed(
            title="🎉 Máme vítěze!",
            description=f"{winner_msg.author.mention} odpověděl(a) správně: **{winner_msg.content}**\n\nZískává **+{xp_reward} XP**!",
            color=discord.Color.gold()
        )
        await interaction.channel.send(embed=win_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChatReviveCog(bot))