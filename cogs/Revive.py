from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import unicodedata
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from database import add_tokens_and_gems, get_user_brawl_data

logger = logging.getLogger(__name__)
QUESTION_TIMEOUT = 60.0
RECENT_QUESTIONS_PER_CATEGORY = 8


def normalize_text(text: str) -> str:
    """Case-insensitive matching: accents and terminal punctuation ignored."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("–", "-").replace("−", "-")
    normalized = re.sub(r"[^\w\s-]+", " ", normalized, flags=re.UNICODE)
    normalized = normalized.replace("_", " ")
    return " ".join(normalized.split())


ANSWER_PREFIXES = (
    "odpoved je ", "odpoved: ", "myslim ze ", "je to ", "tipuju ", "asi ",
)


def is_correct_answer(message_text: str, correct_answers: list[str]) -> bool:
    answer = normalize_text(message_text)
    for prefix in ANSWER_PREFIXES:
        if answer.startswith(prefix):
            answer = answer[len(prefix):].strip()
            break
    # Do not use substring matching: 'shelly' must not match 'neni to shelly'.
    return answer in {normalize_text(alias) for alias in correct_answers}


# Original bank is intentionally kept below. Existing question reward values are preserved.

QUESTIONS = {
    # ==========================================
    # BRAWL STARS (Odměny +20 %)
    # ==========================================
    "brawlstars_easy": [
        {"q": "Jaký je základní Brawler, kterého dostaneš hned na začátku hry? 🌵", "a": ["shelly"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Jak se jmenuje Brawler, který drží kytaru a léčí své spoluhráče? 🎸", "a": ["poco"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Jaký Brawler má jako super schopnost přitáhnout nepřítele pomocí háku/ruky? 🧲", "a": ["gene"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Jak se jmenuje herní mód, kde sbíráte fialové krystaly a musíte je udržet 15 sekund? 💎", "a": ["gem grab"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Jak se nazývá herní mód 'Battle Royale', kde bojuje 10 hráčů a zůstane jen jeden? 🏆", "a": ["showdown", "solo showdown"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Který legendární Brawler používá Super pro zneviditelnění? 🦎", "a": ["leon"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Který Brawler útočí raketometem a dokáže vystřelovat rakety? 🚀", "a": ["brock"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Do které rarity patří Spike, Crow a Leon? 🌟", "a": ["legendary", "legendarni", "legendárna", "legendarna"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Jak se jmenuje Brawler – kostlivec, který hraje na kytaru? 💀", "a": ["poco"], "xp": 100, "gems": 1, "tokens": 1},
        {"q": "Který Brawler házící dynamity má ultra schopnost odpálit velkou sudovou bombu? 🧨", "a": ["dynamike", "mike"], "xp": 100, "gems": 1, "tokens": 1}
    ],

    "brawlstars_medium": [
        {"q": "Jak se jmenuje Brawler, který dokáže vyskočit do vzduchu a zanechá za sebou granáty? 💣", "a": ["piper"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Který Brawler vytváří pískovou bouři, která skrývá spojence? ⏳", "a": ["sandy"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Jak se jmenuje vývojářské studio, které vytvořilo hru Brawl Stars? 🎮", "a": ["supercell"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Který legendární Brawler útočí proudem plamenů? 🔥", "a": ["amber"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Jaký Brawler je slepý sniper/odstřelovačka, která udílí větší poškození na delší vzdálenost? ☂️", "a": ["piper"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Jak se jmenuje Brawler, který vystřeluje magické karty a umí otevřít portál / neviditelnost? 🃏", "a": ["tara"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Který Brawler je velitel vesmírné posádky a vypadá jako pes? 🐶", "a": ["colonel ruffs", "ruffs"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Jak se jmenuje robotický Brawler, který prodává zmrzlinu a zmrazuje soupeře? 🍦", "a": ["lou"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Jaký Brawler střílí ze své věže (turret) a umí léčit spoluhráče na určitém území? 🎒", "a": ["pam"], "xp": 250, "gems": 1, "tokens": 2},
        {"q": "Který Brawler používá baseballovou pálku a má štít z žvýkačky? ⚾", "a": ["bibi"], "xp": 250, "gems": 1, "tokens": 2}
    ],

    "brawlstars_hard": [
        {"q": "Ve kterém roce byla hra Brawl Stars celosvětově (globálně) vydána na iOS a Android? 📅", "a": ["2018"], "xp": 500, "gems": 6, "tokens": 6},
        {"q": "Jak se jmenovala dřívější speciální rarita Brawlerů spojená s Brawl Passem? 🎫", "a": ["chromatic", "chromaticka", "chromatická"], "xp": 500, "gems": 6, "tokens": 6},
        {"q": "Jaké bylo původní kódové/vývojové jméno pro Brawl Stars během raného konceptu? 🏜️", "a": ["laser", "project laser"], "xp": 500, "gems": 6, "tokens": 6},
        {"q": "Který Brawler umí nastoupit do vlastního mecha a změnit tím styl útoku? 🤖", "a": ["meg"], "xp": 500, "gems": 6, "tokens": 6},
        {"q": "Kolik maximálně power pointů / power cube dokážeš sebrat v Showdownu? (Omezení/Limit neexistuje, napiš 'neomezeno' nebo 'infinity') ♾️", "a": ["neomezeno", "neobmedzene", "infinity", "unlimited", "zadne", "ziadne"], "xp": 500, "gems": 6, "tokens": 6},
        {"q": "Jak se jmenuje oficiální šampionát / e-sport turnaj v Brawl Stars organizovaný Supercellem? 🏆", "a": ["brawl stars world championship", "bwc", "bsc"], "xp": 500, "gems": 6, "tokens": 6}
    ],

    # ==========================================
    # EASY (1 token, 0 gemů)
    # ==========================================
    "easy": [
        {"q": "Jaké je hlavní město Austrálie? (Pozor, Sydney to není!) 🇦🇺", "a": ["canberra"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který chemický prvek má značku **Au**? 🥇", "a": ["zlato", "gold"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje nejhlubší místo na Zemi? 🌊", "a": ["mariansky prikop", "mariánský příkop", "marianska priekopa", "mariánska priekopa", "mariana trench"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Rychlá matematika: Kolik je **15 x 15**? 🧮", "a": ["225"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Kanady? 🇨🇦", "a": ["ottawa"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje největší horká poušť na světě? 🏜️", "a": ["sahara"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která kost v lidském těle je nejdelší a nejsilnější? 🦴", "a": ["kost stehenni", "kost stehenní", "stehenni kost", "stehenní kost", "stehenna kost", "stehenná kosť", "femur"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Brazílie? 🇧🇷", "a": ["brasilia", "brasília"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která planeta má nejvíce potvrzených měsíců ve Sluneční soustavě? 🪐", "a": ["saturn"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Rychlá matematika: Kolik je **(45 + 55) x 3**? 🧮", "a": ["300"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který stát má největší rozlohu na světě? 🗺️", "a": ["rusko", "russia"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se nazývá nejtvrdší přírodní minerál? 💎", "a": ["diamant", "diamond"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaká je nejmenší nezávislá země na světě? 🇻🇦", "a": ["vatikan", "vatikán", "vatican", "vatican city"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který panovník v roce 1348 založil univerzitu v Praze? 👑", "a": ["karel iv", "karel 4", "karel iv.", "karol iv", "karol 4", "charles iv"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje nejvyšší činná sopka v Evropě? 🌋", "a": ["etna"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Rychlá matematika: Kolik je **17 x 17**? 🧮", "a": ["289"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaká je chemická značka pro sodík? 🧪", "a": ["na"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Nového Zélandu? 🇳🇿", "a": ["wellington"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Ve kterém roce padla Berlínská zeď? 🧱", "a": ["1989"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která řeka protéká Londýnem? 🌊", "a": ["temze", "temže", "thames"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která země je známá jako 'Země vycházejícího slunce'? 🇯🇵", "a": ["japonsko", "japan"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Kolik kostí má dospělé lidské tělo? 🦴", "a": ["206"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje největší vnitrozemská vodní plocha / jezero na světě? 🌊", "a": ["kaspicke more", "kaspické moře", "caspian sea"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Které pohoří tvoří tradiční hranici mezi Evropou a Asií? 🏔️", "a": ["ural", "ural mountains"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Švédska? 🇸🇪", "a": ["stockholm"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který objevitel v roce 1492 doplul do Ameriky? ⛵", "a": ["kristof kolumbus", "krištof kolumbus", "christopher columbus"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Rychlá matematika: Kolik je **1024 / 16**? 🧮", "a": ["64"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je nejsevernější hlavní město na světě? ❄️", "a": ["reykjavik", "reykjavík"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který kov je za pokojové teploty kapalný? 🧪", "a": ["rtut", "rtuť", "ortut", "ortuť", "mercury"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Který plyn tvoří většinu atmosféry Země? 🌌", "a": ["dusik", "dusík", "nitrogen"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje proces, při kterém rostliny vyrábějí kyslík? 🌿", "a": ["fotosynteza", "fotosyntéza", "photosynthesis"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Kdo napsal drama R.U.R., kde se poprvé objevilo slovo 'Robot'? 🤖", "a": ["karel capek", "karel čapek"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaká je nejvyšší budova světa (v Dubaji)? 🏙️", "a": ["burj khalifa"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Ve kterém roce začala 1. světová válka? 📜", "a": ["1914"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaký je chemický symbol pro železo? 🧪", "a": ["fe"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se jmenuje největší ostrov světa? 🏝️", "a": ["gronsko", "grónsko", "greenland"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Ve kterém roce vzniklo samostatné Československo po 1. světové válce? 🇨🇿", "a": ["1918"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Kdo byl prvním člověkem, který vstoupil na povrch Měsíce (1969)? 🌕", "a": ["neil armstrong"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která krevní skupina je považována za univerzálního dárce? 🩸", "a": ["0-", "0 negativni", "0 negativní", "o negative"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Ve kterém století proběhla Bitva na Bílé hoře (1620)? ⚔️", "a": ["17", "17.", "sedmnactem", "sedmnáctém", "sedemnástom", "17th"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která řeka je nejdelší v České republice? 🌊", "a": ["vltava"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Španělska? 🇪🇸", "a": ["madrid"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jak se nazývá samice od psa? 🐕", "a": ["fena", "bitch"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Která planeta je nejblíže k naší Hvězdě (Slunci)? ☀️", "a": ["merkur", "mercury"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaká je chemická značka pro kyslík? 🧪", "a": ["o"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Kolik minut má jedna celá hodina? ⏱️", "a": ["60"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Rychlá matematika: Kolik je **12 x 12**? 🧮", "a": ["144"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Jaké je hlavní město Itálie? 🇮🇹", "a": ["rim", "řím", "rome"], "xp": 100, "gems": 0, "tokens": 1},
        {"q": "Kolik dní má přestupný rok? 📅", "a": ["366"], "xp": 100, "gems": 0, "tokens": 1}
    ],

    # ==========================================
    # MEDIUM (2 tokeny, 0 gemů)
    # ==========================================
    "medium": [
        {"q": "Jak se jmenovala karibská krize z roku 1962 ohledně raket na Kubě? 🚀", "a": ["kubanska krize", "kubánská krize", "kubanska kriza", "kubánska kríza", "cuban missile crisis"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenovala dohoda z roku 1938, ve které velmoci podstoupily české pohraničí Německu? 📜", "a": ["mnichovska dohoda", "mnichovská dohoda", "mnichovska zmluva", "munich agreement"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenoval spojenecký vojenský výsadek v Normandii v roce 1944 (Den D)? 🎖️", "a": ["operace overlord", "operácia overlord", "operation overlord"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který renesanční sochař vytvořil mramorovou sochu Davida? 🗿", "a": ["michelangelo", "michelangelo buonarroti"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenovala kosmická loď, se kterou Neil Armstrong přistál na Měsíci? 🚀", "a": ["apollo 11"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Egypta? 🇪🇬", "a": ["kahira", "káhira", "cairo"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který chemický prvek má značku **C**? 🧪", "a": ["uhlik", "uhlík", "carbon"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Rychlá matematika: Kolik je **18 x 18**? 🧮", "a": ["324"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje náš první československý prezident? 🏛️", "a": ["tomas garrigue masaryk", "tomáš garrigue masaryk", "tgm"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Která řeka je nejdelší v Evropě? 🌊", "a": ["volha", "volga"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Číny? 🇨🇳", "a": ["peking", "beijing"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který vědec objevil penicilin? 🧫", "a": ["alexander fleming"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro měď? 🧪", "a": ["cu"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Ve kterém roce byla založena organizace OSN? 🌐", "a": ["1945"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Portugalska? 🇵🇹", "a": ["lisabon", "lisbon"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Rychlá matematika: Kolik je **512 / 8**? 🧮", "a": ["64"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který hudební génius složil operu Kouzelná flétna? 🎼", "a": ["wolfgang amadeus mozart", "mozart"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se nazývá přechod skupenství z kapaliny na plyn za jakékoliv teploty? 💨", "a": ["odparovani", "odpařování", "odparovanie", "vyparovani", "vypařování", "evaporation"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Norska? 🇳🇴", "a": ["oslo"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Kdo je autorem slavného antiutopického románu 1984? 📖", "a": ["george orwell"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Rychlá matematika: Kolik je **19 x 19**? 🧮", "a": ["361"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Maďarska? 🇭🇺", "a": ["budapest", "budapešť"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Která vrstva atmosféry nás chrání před škodlivým UV zářením? ☀️", "a": ["ozonova vrstva", "ozónová vrstva", "ozone layer"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Ve kterém roce poprvé vyhořelo Národní divadlo v Praze? 🎭", "a": ["1881"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro vápník (kalcium)? 🧪", "a": ["ca"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Argentiny? 🇦🇷", "a": ["buenos aires"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenoval slavný starověký řecký filosof, učitel Platóna? 🏛️", "a": ["sokrates", "sókratés", "socrates"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje hlavní tepna lidského těla vycházející ze srdce? 🩸", "a": ["aorta"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je de facto hlavní (sídlem vlády) město Švýcarska? 🇨🇭", "a": ["bern"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Která země je nejlidnatějším vnitrozemským státem na světě? 🌍", "a": ["etiopie", "etiopia", "ethiopia"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je přibližná rychlost světla ve vakuu v km/s? (např. 300 000) ⚡", "a": ["300000", "299792", "300 000", "299 792"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenovala tajná operace atentátu na Reinharda Heydricha v roce 1942? 🎖️", "a": ["anthropoid", "operace anthropoid", "operácia anthropoid", "operation anthropoid"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který fyzik jako první v roce 1932 objevil neutron? ⚛️", "a": ["james chadwick"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro draslík (Kalium)? 🧪", "a": ["k"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro wolfram? 🧪", "a": ["w"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro rtuť (Hydrargyrum)? 🧪", "a": ["hg"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro olovo (Plumbum)? 🧪", "a": ["pb"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro stříbro (Argentum)? 🧪", "a": ["ag"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Ve kterém roce začala Stoletá válka mezi Anglií a Francií? ⚔️", "a": ["1337"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje nejhlubší bod Mariánského příkopu? 🌊", "a": ["challenger deep", "challengeruv prohluben", "challengerova prohluben", "challengerova priepasť"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který filosof a matematik formuloval větu 'Cogito, ergo sum'? 🧠", "a": ["rene descartes", "rené descartes"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje nejmenší kost v lidském těle? 🦴", "a": ["trminek", "třmínek", "strmienok", "stirrup"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který zvířecí druh je považován za nejrychlejšího tvora na Zemi při střemhlavém letu? 🦅", "a": ["sokol stahovavy", "sokol stěhovavý", "peregrine falcon"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje největší zvíře, které kdy žilo na Zemi? 🐋", "a": ["vrastenec obrovsky", "vráskavec obrovský", "plejtvak obrovsky", "plejtvák obrovský", "blue whale"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který ostrovní stát v Středozemním moři má hlavní město Vallettu? 🇲🇹", "a": ["malta"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Která planeta je čtvrtá od Slunce a říká se jí 'Rudá planeta'? 🪐", "a": ["mars"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Ve kterém roce došlo k havárii jaderné elektrárny Černobyl? ☢️", "a": ["1986"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje nejvyšší pohoří v České republice? 🏔️", "a": ["krkonose", "krkonoše", "giant mountains"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Která země vyhrála první Mistrovství světa ve fotbale v roce 1930? ⚽", "a": ["uruguay"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Finska? 🇫🇮", "a": ["helsinky", "helsinki"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Který vědec navrhl teorii relativity? ⚛️", "a": ["albert einstein"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaké je hlavní město Dánska? 🇩🇰", "a": ["kodan", "kodaň", "copenhagen"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Které moře rozděluje Evropu a Afriku? 🌊", "a": ["stredozemni more", "středozemní moře", "stredozemne morse", "mediterranean sea"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jaká je chemická značka pro kremík (silicon)? 🧪", "a": ["si"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje nejznámější sopka v Itálii u Neapole, která zničila Pompeje? 🌋", "a": ["vesuv", "vezuv", "vesuvius"], "xp": 250, "gems": 0, "tokens": 2}
    ],

    # ==========================================
    # HARD (5 tokenů, 5 gemů)
    # ==========================================
    "hard": [
        {"q": "Jaké je zákonodárné hlavní město Jihoafrické republiky (JAR)? 🇿🇦", "a": ["kapske mesto", "kapské město", "cape town"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Které město bylo hlavním městem Kazachstánu před Astanou (do r. 1997)? 🇰🇿", "a": ["almaty", "alma-ata", "alma ata"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který král Anglie založil anglikánskou církev a měl celkem 6 manželek? 👑", "a": ["jindrich viii", "jindřich viii", "jindrich 8", "jindřich 8", "henry viii"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje největší aktivní sopka na světě podle objemu (na Havaji)? 🌋", "a": ["mauna loa"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se nazývá úžina oddělující Španělsko a Maroko? 🌊", "a": ["gibraltarska uzina", "gibraltarská úžina", "gibraltarsky prieliv", "strait of gibraltar"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Maroka? 🇲🇦", "a": ["rabat"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Mongolska? 🇲🇳", "a": ["ulanbatar", "ulánbátar", "ulaanbaatar"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Turecka? (Pozor, Istanbul to není!) 🇹🇷", "a": ["ankara"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Vietnamu? 🇻🇳", "a": ["hanoj", "hanoi"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Keni? 🇰🇪", "a": ["nairobi"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Lichtenštejunska? 🇱🇮", "a": ["vaduz"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje slavná Shakespeareova hra, kde vystupuje princ dánský a zazní 'Být, či nebýt'? 🎭", "a": ["hamlet"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který britský evoluční biolog napsal v roce 1976 knihu 'Sobecký gen'? 🧬", "a": ["richard dawkins"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje postava z Shakespearova Kupce benátského, která požadovala liber masa jako splátku? 🎭", "a": ["shylock"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který francouzský osvícenský filozof napsal satirický román Candide? 📖", "a": ["voltaire"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který rakouský fyzik zformuloval myšlenkový experiment s kočkou v krabici? 🐱", "a": ["erwin schrodinger", "erwin schrödinger"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který antický dramatik napsal tragédii Oidipus rex (Král Oidipus)? 🎭", "a": ["sofokles", "sofoklés", "sophocles"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve kterém přesném roce proběhla Bitva na Bílé hoře? ⚔️", "a": ["1620"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který císař Svaté říše římské vládl během Bitvy na Bílé hoře? 👑", "a": ["ferdinand ii", "ferdinand ii.", "ferdinand 2"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenoval mírový traktát z roku 1648, který ukončil Třicetiletou válku? 📜", "a": ["vestfalsky mir", "vestfálský mír", "vestfalsky mier", "peace of westphalia"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Která významná operace RAF v roce 1943 zničila přehrady v německém Porúří? 💣", "a": ["operace chastise", "operácia chastise", "operation chastise", "chastise"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenovala linie opevnění, kterou Francie postavila na hranicích s Německem? 🛡️", "a": ["maginotova linie", "maginotova linia", "maginot line"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve kterém roce proběhla invaze vojsk Varšavské smlouvy do Československa? 🪖", "a": ["1968"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenovala první umělá družice Země vypuštěná SSSR v roce 1957? 🛰️", "a": ["sputnik 1", "sputnik"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenoval sovětský vůdce, který vedl SSSR během Karibské krize v roce 1962? 🏛️", "a": ["nikita chruscov", "nikita chruščov", "nikita khrushchev"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenoval český malíř a grafik, který vytvořil dílo 'Slovanská epopej'? 🎨", "a": ["alfons mucha", "alphonse mucha"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Která jihoamerická řeka má největší průtok vody na světě? 🌊", "a": ["amazonka", "amazon"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje nejvyšší vodopád na světě (nachází se ve Venezuele)? 🌊", "a": ["angeluv vodopad", "angelův vodopád", "anjelsky vodopad", "salto angel", "angel falls"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který slavný norský malíř vytvořil ikonický obraz 'Výkřik' (Scream)? 🖼️", "a": ["edvard munch"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenovala římská provincie na území dnešní Francie a Belgie? 🛡️", "a": ["galie", "gália", "gaul"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který astronom formuloval heliocentrický model Sluneční soustavy v díle z roku 1543? 🌌", "a": ["mikulas kopernik", "mikuláš koperník", "nicolaus copernicus"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Které město v Kanadě je druhé největší a hovoří se v něm převážně francouzsky? 🇨🇦", "a": ["montreal", "montréal"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenoval perský král, kterého Alexandr Veliký porazil v bitvě u Gaugamél? ⚔️", "a": ["dareios iii", "dareios 3", "darios iii", "darius iii"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který slavný objevitel jako první vedením výpravy obeplul Zemi (i když během ní zemřel)? ⛵", "a": ["fernao de magalhaes", "fernando magalhaes", "ferdinand magellan"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve kterém roce proběhla Velká francouzská revoluce (dobytí Bastily)? 📜", "a": ["1789"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje nejvyšší hora Afriky? 🏔️", "a": ["kilimandzaro", "kilimandžáro", "kilimanjaro"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Která země darovala USA slavnou Sochu Svobody? 🗽", "a": ["francie", "francúzsko", "france"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Islandu? 🇮🇸", "a": ["reykjavik", "reykjavík"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje největší záliv na světě podle rozlohy? 🌊", "a": ["bengalsky zaliv", "bengálský záliv", "bay of bengal"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který prvek má nejnižší bod tání ze všech látek (zůstává kapalný i při absolutní nule)? 🧪", "a": ["helium"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje největší mořská želva na světě? 🐢", "a": ["kozatka velka", "kožatka velká", "leatherback turtle"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Které město je oficiálním sídlem Evropského parlamentu (společně s Bruselem)? 🇪🇺", "a": ["strasburk", "štrasburk", "strasbourg"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje slavná přehrada na řece Nil v Egyptě? 🌊", "a": ["asuan", "asúan", "aswan dam"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který slavný fysik vymyslel zákony pohybu a gravitace po pád jablka? 🍏", "a": ["isaac newton", "sir isaac newton"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Severní Koreje (KDR)? 🇰🇵", "a": ["pchjongjang", "pyongyang"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve kterém roce proběhl černý čtvrtek / krach na newyorské burze? 📉", "a": ["1929"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Kolumbie? 🇨🇴", "a": ["bogota", "bogotá"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který spisovatel vytvořil postavu soukromého detektiva Hercula Poirota? 🔍", "a": ["agatha christie"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Který filosof napsal dílo 'Tato promluvil Zarathustra'? 📜", "a": ["friedrich nietzsche", "nietzsche"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se jmenuje největší vnitřní orgán v lidském těle? 🫀", "a": ["jatra", "játra", "pecen", "pečeň", "liver"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve které evropské zemi leží město Tampere a hlavním městem je Helsinky? 🇫🇮", "a": ["finsko", "finland"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Která římská provincie odpovídá dnešnímu území Egypta? 🇪🇬", "a": ["aegyptus", "egypt"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jaké je hlavní město Etiopie? 🇪🇹", "a": ["addis abeba", "addis ababa"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Jak se nazývá vědní obor zabývající se studiem ryb? 🐟", "a": ["ichtyologie", "ichthyology"], "xp": 500, "gems": 5, "tokens": 5},
        {"q": "Ve kterém roce byl založen fotbalový klub FC Barcelona? ⚽", "a": ["1899"], "xp": 500, "gems": 5, "tokens": 5}
    ],

    # ==========================================
    # ULTRA HARD (10 tokenů, 15 gemů)
    # ==========================================
    "ultrahard": [
        {"q": "Jak se jmenoval úplně první pes, který se vrátil z vesmíru ŽIVÝ (společně s Bělkou)? 🐕", "a": ["strelka", "střelka"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je přesné kódové označení (písmeno a číslo) první německé ponorky potopené ve 2. světové válce? ⚓", "a": ["u-27", "u27"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala vlajková loď Kryštofa Kolumba při jeho první výpravě v roce 1492? ⛵", "a": ["santa maria", "santa maría"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Která starověká bitva v roce 480 př. n. l. proslavila spartského krále Leónida proti Peršanům? ⚔️", "a": ["bitva u thermopyl", "bitka pri thermopylach", "battle of thermopylae"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který římský císař vládl v době, kdy v roce 79 n. l. výbuch Vesuvu zničil Pompeje? 🏛️", "a": ["titus"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala první žena, která vzlétla do vesmíru (v roce 1963)? 🚀", "a": ["valentina tereskovova", "valentina těreškovová", "valentina tereshkova"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Ve kterém roce byl spáchán atentát na amerického prezidenta Johna F. Kennedyho v Dallasu? 📜", "a": ["1963"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Ve kterém roce byla podepsána Magna Charta Libertatum v Anglii? 📜", "a": ["1215"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který švédský král padl v bitvě u Lützenu v roce 1632 během Třicetileté války? ⚔️", "a": ["gustav ii adolf", "gustav adolf", "gustavus adolphus"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je hlavní město Myanmaru (Barmy)? (Není to Rangún!) 🇲🇲", "a": ["naypyidaw", "najpijto"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je oficiální ústavní/hlavní město Bolívie (sídlo vlády je La Paz)? 🇧🇴", "a": ["sucre"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je hlavní město Šalamounových ostrovů? 🇸🇧", "a": ["honiara"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje nejlidnatější ostrov na světě (nachází se v Indonésii)? 🏝️", "a": ["java", "jáva"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Které je nejchladnější trvale obydlené místo na Zemi (vesnice na Sibiři)? ❄️", "a": ["ojmjakon", "oimjakon", "oymyakon"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který vnitrozemský stát Jižní Ameriky nemá žádný přístup k moři (kromě Bolívie)? 🌎", "a": ["paraguay"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je hlavní město Madagaskaru? 🇲🇬", "a": ["antananarivo"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je atomové číslo (protonové číslo) Oganessonu (Og)? ⚛️", "a": ["118"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaká je přesná frekvence (v Hz) tónu komorního A (A4) podle mezinárodní normy ISO 16? 🎼", "a": ["440", "440hz", "440 hz"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje největší žijící ještěr na světě (žije v Indonésii)? 🦎", "a": ["varan komodsky", "varan komodský", "komodo dragon"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který chemický prvek má nejvyšší bod tání ze všech kovů (přes 3400 °C)? 🧪", "a": ["wolfram", "tungsten"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje vědní obor zabývající se studiem mechů a játrovek? 🌿", "a": ["bryologie", "bryology"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Která část lidského mozku je zodpovědná za koordinaci pohybů a rovnováhu? 🧠", "a": ["mozecek", "mozeček", "cerebellum"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje hlavní hormon štítné žlázy, který obsahuje jód? 🩸", "a": ["thyroxin", "tiroxin", "thyroxine"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Kdo byl architektem, který navrhl ikonický vysílač a hotel na Ještědu? 🏔️", "a": ["karel hubacek", "karel hubáček"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala první manželka Jindřicha VIII., kvůli které se odtrhl od katolické církve? 👑", "a": ["katerina aragonska", "kateřina aragonská", "katarina aragonska", "catherine of aragon"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který český barokní skladatel složil slavné dílo 'Missa Sanctissimae Trinitatis'? 🎼", "a": ["jan dismas zelenka"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který španělský architekt navrhl slavnou baziliku Sagrada Família v Barceloně? 🏰", "a": ["antoni gaudi", "antoni gaudí"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Kdo napsal slavný antický epos Ilias a Odysseia? 📖", "a": ["homer", "homér"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala slavná římská gladiátorka / koncept gladiátorky (ženský ekvivalent)? 🗡️", "a": ["gladiatrix"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaký HTTP status kód znamená „I'm a teapot“? ☕", "a": ["418"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala první počítačová síť z roku 1969, která byla předchůdcem Internetu? 🌐", "a": ["arpanet"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Které číslo je v hexadecimální (šestnáctkové) soustavě reprezentováno řetězcem 'FF'? 🔢", "a": ["255"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké bylo původní kódové označení (codename) pro Windows 95 během vývoje? 💻", "a": ["chicago"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se nazývá teoretická hranice černá díry, za kterou již nic (ani světlo) nemůže uniknout? 🕳️", "a": ["horizont udalosti", "horizont událostí", "event horizon"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Které město bylo hlavním městem Svaté říše římské v letech 1583–1611 za vlády Rudolfa II.? 👑", "a": ["praha", "prague"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se nazývá typ elementární částice, z níž se skládají protony a neutrony? ⚛️", "a": ["kvark", "quark"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenoval slavný byzantský císař, který nechal postavit chrám Hagia Sophia v Konstantinopoli? 🏛️", "a": ["justinian i", "justinián i", "justinian 1", "justinian"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který fyzik formuloval princip neurčitosti v kvantové mechanice? ⚛️", "a": ["werner heisenberg", "heisenberg"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje nejstarší dosud dochovaný epos v historii lidstva? 📖", "a": ["epos o gilgamesovi", "gilgames", "gilgameš", "epic of gilgamesh"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Které japonské město je známé částmi Šibuja a Šindžuku? 🇯🇵", "a": ["tokio", "tokyo"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Která skupina savců jako jediná dokáže aktivně létat? 🦇", "a": ["netopyr", "netopýr", "netopier", "bat"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Která bitva v roce 1805 je známá jako Bitva tří císařů? ⚔️", "a": ["bitva u slavkova", "slavkov", "austerlitz", "battle of austerlitz"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se nazývá enzym v lidských slinách, který začíná štěpit škroby? 🧪", "a": ["ptyalin", "amylaza", "amyláza"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaké je hlavní město Tichomořského státu Kiribati? 🇰🇮", "a": ["tarawa", "south tarawa"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Které knížectví leží mezi Švýcarskem a Rakouskem? 🏔️", "a": ["lichtenstejnsko", "lichtenštejnsko", "liechtenstein"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Který filozof vymyslel paradox o Achillovi a želvě? 🐢", "a": ["zenon z eleje", "zenon", "zeno of elea"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenovala operační složka sovětské tajné policie za Stalina před KGB? 🕵️", "a": ["nkvd"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jaký je nejvzácnější přirozeně se vyskytující prvek v zemské kůře (radioaktivní halogen)? 🧪", "a": ["astat", "astatine"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Ve kterém roce byla vydána první verze operačního systému Linux (Linusem Torvaldem)? 🐧", "a": ["1991"], "xp": 1000, "gems": 15, "tokens": 10},
        {"q": "Jak se jmenuje nejsvětlejší hvězda na noční obloze (v souhvězdí Velkého psa)? 🌟", "a": ["sirius"], "xp": 1000, "gems": 15, "tokens": 10}
    ],

    # ==========================================
    # FOOTBALL (Odměněno jako medium: 2 tokeny, 0 gemů)
    # ==========================================
    "football": [
        {"q": "Kolik minut trvá standardní fotbalový zápas bez prodloužení? ⏱️", "a": ["90"], "xp": 150, "gems": 0, "tokens": 2},
        {"q": "Který národní tým vyhrál Mistrovství světa ve fotbale v roce 2022 v Kataru? 🏆", "a": ["argentina"], "xp": 300, "gems": 0, "tokens": 2},
        {"q": "Který hráč získal v historii najvíce Zlatých míčů (Ballon d'Or)? ⚽", "a": ["lionel messi", "messi"], "xp": 250, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje slavný fotbalový stadion klubu Real Madrid? 🏟️", "a": ["santiago bernabeu", "santiago bernabéu", "bernabeu"], "xp": 400, "gems": 0, "tokens": 2},
        {"q": "Který klub vyhrál nejvíce titulů v Lize mistrů (Champions League)? 🏆", "a": ["real madrid", "real"], "xp": 300, "gems": 0, "tokens": 2},
        {"q": "Který český fotbalista získal v roce 2003 Zlatý míč? 🇨🇿", "a": ["pavel nedved", "pavel nedvěd"], "xp": 400, "gems": 0, "tokens": 2},
        {"q": "Která země uspořádala vůbec první Mistrovství světa ve fotbale v roce 1930? 🇺🇾", "a": ["uruguay"], "xp": 600, "gems": 0, "tokens": 2},
        {"q": "Který fotbalový klub má přezdívku 'Red Devils' (Rudí ďáblové)? 🔴", "a": ["manchester united", "man utd", "mufc"], "xp": 350, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje pravidlo, které zakazuje útočníkovi být za posledním obráncem v momentě přihrávky? 🚩", "a": ["ofsajd", "offside", "mimo hru"], "xp": 200, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje slavný brazilský fotbalista, přezdívaný 'Král fotbalu', který zemřel v roce 2022? 🇧🇷", "a": ["pele", "pelé"], "xp": 300, "gems": 0, "tokens": 2},
        {"q": "Který anglický klub dokázal vyhrát Premier League v sezóně 2003/04 bez jediné porážky ('Invincibles')? 🏆", "a": ["arsenal", "arsenal fc"], "xp": 500, "gems": 0, "tokens": 2},
        {"q": "Kdo je historicky nejlepší střelec v historii Ligy mistrů? ⚽", "a": ["cristiano ronaldo", "ronaldo", "cr7"], "xp": 350, "gems": 0, "tokens": 2},
        {"q": "Ve kterém městě sídlí fotbalový klub Borussia Dortmund? 🇩🇪", "a": ["dortmund"], "xp": 200, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje slavné derby mezi Realem Madrid a FC Barcelona? 🇪🇸", "a": ["el clasico", "el clásico", "clasico"], "xp": 300, "gems": 0, "tokens": 2},
        {"q": "Který manažer vedl Manchester United neuvěřitelných 26 let (1986–2013)? 👔", "a": ["alex ferguson", "sir alex ferguson"], "xp": 450, "gems": 0, "tokens": 2},
        {"q": "Který stát vyhrál Euro 2004 jako absolutní outsider po finálové výhře nad Portugalskem? 🇬🇷", "a": ["recko", "řecko", "greece"], "xp": 450, "gems": 0, "tokens": 2},
        {"q": "Který fotbalový klub je známý pod přezdívkou 'Stará dáma' (La Vecchia Signora)? 🇮🇹", "a": ["juventus", "juventus turin", "juventus turín"], "xp": 350, "gems": 0, "tokens": 2},
        {"q": "Ve kterém roce vyhrála Chelsea poprvé v historii Ligu mistrů (po penaltách proti Bayernu)? 🏆", "a": ["2012"], "xp": 500, "gems": 0, "tokens": 2},
        {"q": "Který český klub se v sezóně 1995/96 dostal do semifinále Poháru UEFA? 🇨🇿", "a": ["slavia", "slavia praha", "slavia prague"], "xp": 500, "gems": 0, "tokens": 2},
        {"q": "Ve kterém francouzském klubu odstartoval svou evropskou kariéru Ronaldinho před přestupem do Barcy? 🇫🇷", "a": ["psg", "paris saint-germain", "paris saint germain"], "xp": 500, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenoval slavný nizozemský fotbalista a trenér, který je považován za otce 'totálního fotbalu'? 🇳🇱", "a": ["johan cruyff", "johan cruijff"], "xp": 500, "gems": 0, "tokens": 2},
        {"q": "Která země vyhrála historicky nejvíce titulů na Mistrovství světa (celkem 5)? 🟡🟢", "a": ["brazilie", "brazília", "brazil"], "xp": 300, "gems": 0, "tokens": 2},
        {"q": "Který brankář jako jediný v historii získal Zlatý míč (v roce 1963)? 🧤", "a": ["lev jasin", "lev jašin", "lev yashin"], "xp": 600, "gems": 0, "tokens": 2},
        {"q": "Jak se jmenuje oficiální hymna anglického klubu Liverpool FC? 🔴", "a": ["youll never walk alone", "you'll never walk alone", "ynwa"], "xp": 400, "gems": 0, "tokens": 2},
        {"q": "Který stadion má největší kapacitu v Evropě (přes 99 000 diváků)? 🏟️", "a": ["camp nou", "spotify camp nou"], "xp": 450, "gems": 0, "tokens": 2}
    ]
}


# Additional questions: rewards follow the existing difficulty economy.
NEW_QUESTION_REWARDS = {
    "easy": (100, 0, 1),
    "medium": (250, 0, 2),
    "hard": (500, 5, 5),
    "ultrahard": (1000, 15, 10),
    "football": (300, 0, 2),
    "brawlstars_easy": (100, 1, 1),
    "brawlstars_medium": (250, 1, 2),
    "brawlstars_hard": (500, 6, 6),
}

ADDITIONAL_QUESTIONS = {'brawlstars_easy': [('Který Brawler nosí dva revolvery a střílí rychlé dávky? 🔫', ['colt']),
                     ('Který Brawler dokáže vyvolat medvěda? 🐻', ['nita']),
                     ('Který Brawler se kutálí v sudu pomocí svého Superu? 🛢️', ['darryl']),
                     ('Jak se jmenuje Brawler, který umisťuje věž Scrappy? 🔧', ['jessie']),
                     ('Který Brawler je zápasník s maskou a skáče na soupeře? 🤼', ['el primo']),
                     ('Který Brawler je herní automat s číslem 8 ve jménu? 🕹️', ['8-bit', '8bit']),
                     ('Který Brawler pěstuje rostliny a bojuje boxerskými rukavicemi? 🌹', ['rosa']),
                     ('Jak se jmenuje Brawler, který používá krumpáč jako bumerang? ⛏️', ['carl']),
                     ('Který Brawler používá veliké kladivo a je nemrtvý? 🔨', ['frank']),
                     ('Který Brawler má baseballovou pálku? ⚾', ['bibi'])],
 'brawlstars_medium': [('Který Brawler umí svým Superem postavit dočasnou zeď? 🧱', ['sprout']),
                       ('Který Brawler vypadá jako živý lepkavý výtvor a hází lepkavé střely? 🧪', ['squeak']),
                       ('Který Brawler posiluje tým energetickým nápojem a je extrémně rychlý? ⚡', ['max']),
                       ('Který Brawler střílí z děla na zádech a může postavit minomet? 🏴\u200d☠️',
                        ['penny']),
                       ('Který Brawler používá balónky a je známý jako duch? 🎈', ['gus']),
                       ('Který Brawler má černobílou masku a používá hvězdicové miny? 🪤', ['bo']),
                       ('Jaký Brawler si dokáže Superem přitáhnout soupeře pomocí magické ruky? 🖐️',
                        ['gene'])],
 'brawlstars_hard': [('Do jaké rarity v našem Discord Brawl systému patří Wendy? 💫',
                      ['mythic', 'myticka', 'mytická']),
                     ('Do jaké rarity v našem Discord Brawl systému patří Cosmo? 🌌',
                      ['mythic', 'myticka', 'mytická']),
                     ('Do jaké rarity v našem Discord Brawl systému patří Vince? 🏆',
                      ['mythic', 'myticka', 'mytická']),
                     ('Jak se jmenuje Brawler, který může protihráče přesunout do Shadow Realm? 🌑',
                      ['cordelius']),
                     ('Který Brawler se dokáže rozdělit na horní a spodní část těla? 🤖',
                      ['r-t', 'rt', 'r t']),
                     ('Který Brawler používá párky a dokáže spoluhráče oživit svým Superem? 🌭', ['doug']),
                     ('Kolik nových Brawlerů získáš z jednoho boxu v našem Discord Brawl systému? 📦',
                      ['1', 'jeden', 'jednoho']),
                     ('Jmenuj jednoho ze dvou Ultra Legendary Brawlerů v našem Discord systému. 🔮',
                      ['kaze', 'sirius']),
                     ('Ve které zemi sídlí studio Supercell? 🇫🇮', ['finsko', 'finland', 'finsku']),
                     ('Jak se jmenuje Brawler, který díky Superu může vstoupit do velkého robotického mecha? '
                      '🤖',
                      ['meg'])],
 'easy': [('Kolik hodin má jeden den? 🕒', ['24']),
          ('Jaká je chemická značka vody? 💧', ['h2o']),
          ('Která planeta je největší ve Sluneční soustavě? 🪐', ['jupiter']),
          ('Kolik je 25 × 4? 🧮', ['100']),
          ('Která země má hlavní město Varšava? 🇵🇱', ['polsko', 'poland']),
          ('Jaké je hlavní město Rakouska? 🇦🇹', ['viden', 'vídeň', 'vienna']),
          ('Jak se jmenuje přirozená družice Země? 🌕', ['mesic', 'měsíc', 'moon']),
          ('Který světadíl je největší podle rozlohy? 🌏', ['asie', 'azie', 'asia']),
          ('Jak se nazývá přístroj k měření teploty? 🌡️', ['teplomer', 'teploměr', 'thermometer']),
          ('Kolik stran má pravidelný šestiúhelník? ⬡', ['6', 'sest', 'šest']),
          ('Ve kterém městě stojí Eiffelova věž? 🗼', ['pariz', 'paříž', 'paris']),
          ('Která česká řeka protéká Prahou? 🌊', ['vltava'])],
 'medium': [('Která chemická značka patří stříbru? 🥈', ['ag']),
            ('Který český vědec proslul zákony dědičnosti při pokusech s hrachem? 🌱',
             ['gregor mendel', 'johann gregor mendel', 'mendel']),
            ('Jaké je hlavní město Irska? 🇮🇪', ['dublin']),
            ('Jaký je největší oceán na Zemi? 🌊', ['tichy ocean', 'tichý oceán', 'pacifik', 'pacific ocean']),
            ('Ve kterém roce došlo k sametové revoluci? 🇨🇿', ['1989']),
            ('Který polský astronom je spojován s heliocentrickým modelem? ☀️',
             ['mikulas kopernik', 'mikuláš koperník', 'kopernik', 'koperník', 'copernicus']),
            ('Jak se nazývá skupenství přecházející ze skupenství pevného přímo na plynné? 💨',
             ['sublimace', 'sublimation']),
            ('Kolik stupňů má součet vnitřních úhlů trojúhelníku? 📐', ['180', '180 stupnu', '180 stupňů']),
            ('Jaké je hlavní město Jižní Koreje? 🇰🇷', ['soul', 'seoul']),
            ('Kdo napsal Malého prince? 📖',
             ['antoine de saint exupery', 'saint exupery', 'antoine de saint-exupéry', 'saint-exupéry']),
            ('Která země má na vlajce javorový list? 🍁', ['kanada', 'canada'])],
 'hard': [('Ve kterém roce byla vyhlášena nezávislost USA? 🇺🇸', ['1776']),
          ('Jaké je protonové číslo zlata (Au)? ⚛️', ['79']),
          ('V jakém roce byly poprvé uděleny Nobelovy ceny? 🏅', ['1901']),
          ('Jak se nazývá nejstarší dochovaný zákoník starověkého Babylonu spojovaný s králem Chammurapim? 📜',
           ['chammurapiho zakonik',
            'chammurapiho zákoník',
            'kodex chammurapi',
            'code of hammurabi',
            'hammurabiho zakonik']),
          ('Který astronom objevil čtyři největší měsíce Jupiteru roku 1610? 🔭',
           ['galileo galilei', 'galileo']),
          ('Jaké bylo křestní jméno skladatele Dvořáka, autora Novosvětské symfonie? 🎼',
           ['antonin', 'antonín']),
          ('Jak se jmenuje proces, při kterém atomové jádro vyzáří částici alfa? ☢️',
           ['alfa rozpad', 'alfa-rozpad', 'rozpad alfa', 'alpha decay']),
          ('Jak se nazývá hexadecimální soustava ve světě programování stručně? 💻',
           ['sestnactkova', 'šestnáctková', 'hexadecimalni', 'hexadecimální', 'hex']),
          ('Jaké bylo hlavní město Osmanské říše po dobytí Konstantinopole roku 1453? 🕌',
           ['konstantinopol', 'constantinople', 'istanbul']),
          ('Kdo napsal román Proces? 📚', ['franz kafka', 'kafka']),
          ('Jaké je hlavní město Peru? 🇵🇪', ['lima'])],
 'ultrahard': [('Kolik metrů za sekundu je přesná definovaná rychlost světla ve vakuu? ⚡',
                ['299792458', '299 792 458']),
               ('Kdo objevil první pulsar v roce 1967 jako doktorandka? 🌌',
                ['jocelyn bell burnell', 'jocelyn bell', 'bell burnell']),
               ('Který český vědec získal Nobelovu cenu za polarografii v roce 1959? 🧪',
                ['jaroslav heyrovsky', 'jaroslav heyrovský', 'heyrovsky', 'heyrovský']),
               ('Jaký je rok dobytí Konstantinopole Osmany? 🏰', ['1453']),
               ('Jaké je binární vyjádření desítkového čísla 13? 💻', ['1101']),
               ('Jak se jmenuje matematická konstanta přibližně 2,71828? 🔢',
                ['e', 'eulerovo cislo', 'eulerovo číslo']),
               ('Který elementární fermion nese elektrický náboj −1 a nachází se kolem atomového jádra? ⚛️',
                ['elektron', 'electron']),
               ('Který český skladatel zkomponoval operu Rusalka? 🎼',
                ['antonin dvorak', 'antonín dvořák', 'dvorak', 'dvořák']),
               ('Jaký prvek má chemickou značku Sb? 🧪', ['antimon', 'antimony']),
               ('Jak se jmenuje matematický pojem pro číslo dělitelné pouze 1 a samo sebou? 🔢',
                ['prvocislo', 'prvočíslo', 'prime number'])],
 'football': [('Která země vyhrála Mistrovství světa ve fotbale 2014? 🏆', ['nemecko', 'německo', 'germany']),
              ('Která země vyhrála Mistrovství světa ve fotbale 2010? 🏆',
               ['spanelsko', 'španělsko', 'spain']),
              ('Ve kterém roce vyhrálo Řecko fotbalové Euro? 🇬🇷', ['2004']),
              ('Který klub je známý stadionem Anfield? 🏟️', ['liverpool', 'liverpool fc']),
              ('Ve kterém městě sídlí italský klub AC Milan? 🇮🇹', ['milan', 'milano', 'milán']),
              ('Kdo vstřelil slavný gól „Boží rukou“ na MS 1986? ⚽', ['diego maradona', 'maradona']),
              ('Který fotbalový klub má přezdívku Blaugrana? 🔵🔴',
               ['barcelona', 'fc barcelona', 'barca', 'barça']),
              ('Který klub sídlí na stadionu Old Trafford? 🏟️', ['manchester united', 'man utd']),
              ('Které zemi patří klub Ajax Amsterdam? 🇳🇱',
               ['nizozemsko', 'nizozemí', 'holandsko', 'netherlands']),
              ('Která země vyhrála Mistrovství světa ve fotbale 2006? 🏆', ['italie', 'itálie', 'italy']),
              ('Ve kterém roce proběhlo fotbalové MS v Jihoafrické republice? 🌍', ['2010'])]}

for category, question_list in ADDITIONAL_QUESTIONS.items():
    xp, gems, tokens = NEW_QUESTION_REWARDS[category]
    QUESTIONS[category].extend(
        {"q": question, "a": answers, "xp": xp, "gems": gems, "tokens": tokens}
        for question, answers in question_list
    )


def validate_questions() -> None:
    for category, items in QUESTIONS.items():
        seen = set()
        for item in items:
            prompt = item["q"]
            if prompt in seen:
                logger.warning("Duplicate quiz question in %s: %s", category, prompt)
            seen.add(prompt)
            if not isinstance(item["a"], list) or not item["a"] or not all(normalize_text(v) for v in item["a"]):
                raise ValueError(f"Invalid quiz answers for {category}: {prompt}")
            if any(not isinstance(item[k], int) or item[k] < 0 for k in ("xp", "gems", "tokens")):
                raise ValueError(f"Invalid quiz rewards for {category}: {prompt}")


validate_questions()

DIFFICULTIES = {
    "easy": ("🟢 LEHKÁ", discord.Color.green()),
    "medium": ("🟡 STŘEDNÍ", discord.Color.gold()),
    "hard": ("🔴 TĚŽKÁ", discord.Color.red()),
    "ultrahard": ("🟣 ULTRA TĚŽKÁ", discord.Color.purple()),
    "football": ("⚽ FOTBALOVÉ", discord.Color.blue()),
    "brawlstars_easy": ("🌵 BRAWL STARS • LEHKÁ", discord.Color.green()),
    "brawlstars_medium": ("🌵 BRAWL STARS • STŘEDNÍ", discord.Color.magenta()),
    "brawlstars_hard": ("🌵 BRAWL STARS • TĚŽKÁ", discord.Color.dark_purple()),
}


class ChatReviveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_questions: set[int] = set()
        self.recent_questions: dict[tuple[int, str], deque[str]] = defaultdict(
            lambda: deque(maxlen=RECENT_QUESTIONS_PER_CATEGORY)
        )

    def _draw_question(self, channel_id: int, category: str) -> dict:
        key = (channel_id, category)
        recent = self.recent_questions[key]
        candidates = [q for q in QUESTIONS[category] if q["q"] not in recent]
        question = random.choice(candidates or QUESTIONS[category])
        recent.append(question["q"])
        return question

    @staticmethod
    async def _safe_error(interaction: discord.Interaction, message: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.warning("Could not send error to Discord interaction %s", interaction.id)

    @app_commands.guild_only()
    @app_commands.command(name="revive", description="Spusť chatový kvíz. První správná odpověď vyhrává!")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="🎲 Náhodná obtížnost", value="random"),
        app_commands.Choice(name="🟢 Lehká (Easy)", value="easy"),
        app_commands.Choice(name="🟡 Střední (Medium)", value="medium"),
        app_commands.Choice(name="🔴 Těžká (Hard)", value="hard"),
        app_commands.Choice(name="🟣 Ultra Těžká (Ultra Hard)", value="ultrahard"),
        app_commands.Choice(name="⚽ Fotbalové", value="football"),
        app_commands.Choice(name="🌵 BS - Lehká", value="brawlstars_easy"),
        app_commands.Choice(name="🌵 BS - Střední", value="brawlstars_medium"),
        app_commands.Choice(name="🌵 BS - Těžká", value="brawlstars_hard"),
    ])
    async def revive(self, interaction: discord.Interaction, difficulty: str = "random"):
        channel = interaction.channel
        if channel is None or interaction.guild_id is None:
            await self._safe_error(interaction, "❌ Kvíz můžeš spustit pouze na serveru.")
            return

        # Mark active *before* first await, so two users cannot start together.
        if channel.id in self.active_questions:
            await self._safe_error(interaction, "⏳ V tomto kanálu už jedna otázka běží!")
            return
        self.active_questions.add(channel.id)
        answered = False
        try:
            try:
                await interaction.response.defer(thinking=True)
            except discord.NotFound as exc:
                if exc.code == 10062:
                    logger.warning("Revive interaction expired (%s)", interaction.id)
                    return
                raise

            if difficulty == "random":
                value = random.random()
                selected = "easy" if value < 0.40 else "medium" if value < 0.75 else "hard" if value < 0.95 else "ultrahard"
            else:
                selected = difficulty
            if selected not in QUESTIONS:
                await interaction.followup.send("❌ Neplatná obtížnost.", ephemeral=True)
                return

            question = self._draw_question(channel.id, selected)
            xp_reward = int(question["xp"])
            tokens_reward = int(question["tokens"])
            gems_reward = int(question["gems"])
            correct_answers = question["a"]
            level_cog = self.bot.get_cog("LevelingCog")
            has_leveling = level_cog is not None and callable(getattr(level_cog, "add_xp", None))
            reward_lines = [f"🪙 **{tokens_reward} tokenů**", f"💎 **{gems_reward} gemů**"]
            if has_leveling:
                reward_lines.insert(0, f"⭐ **{xp_reward} XP**")

            diff_label, color = DIFFICULTIES[selected]
            deadline = int(time.time() + QUESTION_TIMEOUT)
            embed = discord.Embed(
                title="⚡ CHAT REVIVE • KVÍZ",
                description=(
                    f"## {question['q']}\n\n"
                    f"Napiš odpověď **do tohoto kanálu**.\n"
                    f"⏳ Čas vyprší <t:{deadline}:R>."
                ),
                color=color,
            )
            embed.add_field(name="🎯 Obtížnost", value=diff_label, inline=True)
            embed.add_field(name="🎁 Odměny", value="\n".join(reward_lines), inline=True)
            embed.set_footer(text="První správná odpověď vyhrává • 60 sekund • diakritika není nutná")

            # Register wait_for before publishing the embed; avoids missing instant replies.
            waiter = asyncio.create_task(self.bot.wait_for(
                "message",
                timeout=QUESTION_TIMEOUT,
                check=lambda m: (
                    m.channel.id == channel.id
                    and not m.author.bot
                    and is_correct_answer(m.content, correct_answers)
                ),
            ))
            try:
                await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except Exception:
                waiter.cancel()
                try:
                    await waiter
                except asyncio.CancelledError:
                    pass
                raise

            try:
                winner_msg = await waiter
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⌛ Čas vypršel",
                    description=(
                        f"Nikdo neodpověděl správně.\n\n"
                        f"✅ Správná odpověď: **{discord.utils.escape_markdown(correct_answers[0])}**"
                    ),
                    color=discord.Color.dark_gray(),
                )
                await channel.send(embed=timeout_embed, allowed_mentions=discord.AllowedMentions.none())
                return

            answered = True
            currency_awarded = False
            xp_awarded = False
            try:
                if tokens_reward or gems_reward:
                    # Exactly the same Supabase table/user balance as Brawl /inventory & /boxshop.
                    await add_tokens_and_gems(
                        guild_id=interaction.guild_id,
                        user_id=winner_msg.author.id,
                        tokens=tokens_reward,
                        gems=gems_reward,
                    )
                currency_awarded = True
            except Exception:
                logger.exception("Supabase quiz reward failed, guild=%s, user=%s", interaction.guild_id, winner_msg.author.id)

            if has_leveling:
                try:
                    await level_cog.add_xp(winner_msg.author, xp_reward, channel)
                    xp_awarded = True
                except Exception:
                    logger.exception("Quiz XP reward failed, guild=%s, user=%s", interaction.guild_id, winner_msg.author.id)

            earned = []
            if currency_awarded:
                if tokens_reward:
                    earned.append(f"🪙 **+{tokens_reward} tokenů**")
                if gems_reward:
                    earned.append(f"💎 **+{gems_reward} gemů**")
            else:
                earned.append("⚠️ **Odměny v Supabase se nepodařilo potvrdit.** Kontaktuj admina.")
            if xp_awarded:
                earned.append(f"⭐ **+{xp_reward} XP**")
            elif has_leveling:
                earned.append("⚠️ XP odměnu se nepodařilo potvrdit.")

            # Read-only confirmation. A query failure must not create a second payout.
            if currency_awarded:
                try:
                    wallet = await get_user_brawl_data(interaction.guild_id, winner_msg.author.id)
                    earned.append(
                        f"\n**Nový zůstatek:** 🪙 {int(wallet['tokens'])} tokenů • "
                        f"💎 {int(wallet['gems'])} gemů"
                    )
                except Exception:
                    logger.warning("Quiz balance refresh failed; reward had already been awarded", exc_info=True)

            win_embed = discord.Embed(
                title="🏆 Máme vítěze!",
                description=(
                    f"{winner_msg.author.mention} odpověděl jako první správně!\n"
                    f"✅ **{discord.utils.escape_markdown(correct_answers[0])}**\n\n"
                    "**Výsledek odměn:**\n" + "\n".join(earned)
                ),
                color=discord.Color.green() if currency_awarded else discord.Color.orange(),
            )
            win_embed.set_footer(text="Měna je společná pro Revive, Brawl Boxy i Counting")
            await channel.send(embed=win_embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

        except discord.HTTPException:
            logger.exception("Discord HTTP error in Revive: channel=%s", channel.id)
        except Exception:
            logger.exception("Unexpected Revive error: channel=%s", channel.id)
            if not answered:
                await self._safe_error(interaction, "❌ Kvíz se nepodařilo spustit nebo dokončit. Zkus to později.")
        finally:
            self.active_questions.discard(channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatReviveCog(bot))
