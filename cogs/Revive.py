import random
import asyncio
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands

# Pomocná funkce pro odstranění diakritiky a převod na malá písmena
def normalize_text(text: str) -> str:
    text = text.lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    
# -------------------------------------------------------------------
# DATABÁZE OTÁZEK PRO CHAT REVIVE
# -------------------------------------------------------------------
QUESTIONS = {
    # EASY (Základní všeobecný přehled, historie, geografie, rychlá matematika)
    "easy": [
        {"q": "Jaké je hlavní město Austrálie? (Pozor, Sydney to není!) 🇦🇺", "a": ["canberra"], "xp": 100},
        {"q": "Který chemický prvek má značku **Au**? 🥇", "a": ["zlato"], "xp": 100},
        {"q": "Jak se jmenuje nejhlubší místo na Zemi? 🌊", "a": ["mariansky prikop", "mariánský příkop"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **15 x 15**? 🧮", "a": ["225"], "xp": 100},
        {"q": "Jaké je hlavní město Kanady? 🇨🇦", "a": ["ottawa"], "xp": 100},
        {"q": "Jak se jmenuje největší horká poušť na světě? 🏜️", "a": ["sahara"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš **HYPERPROSTOR** pozpátku! 🔄", "a": ["rostorprepyh"], "xp": 100},
        {"q": "Která kost v lidském těle je nejdelší a nejsilnější? 🦴", "a": ["kost stehenni", "kost stehenní", "stehenni kost", "stehenní kost", "stehenni", "stehenní"], "xp": 100},
        {"q": "Jaké je hlavní město Brazílie? 🇧🇷", "a": ["brasilia", "brasília"], "xp": 100},
        {"q": "Která planeta má nejvíce potvrzených měsíců ve Sluneční soustavě? 🪐", "a": ["saturn"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **(45 + 55) x 3**? 🧮", "a": ["300"], "xp": 100},
        {"q": "Který stát má největší rozlohu na světě? 🗺️", "a": ["rusko"], "xp": 100},
        {"q": "Jak se nazývá nejtvrdší přírodní minerál? 💎", "a": ["diamant"], "xp": 100},
        {"q": "Jaká je nejmenší nezávislá země na světě? 🇻🇦", "a": ["vatikan", "vatikán"], "xp": 100},
        {"q": "Který panovník v roce 1348 založil univerzitu v Praze? 👑", "a": ["karel iv", "karel 4", "karel iv."], "xp": 100},
        {"q": "Jak se jmenuje nejvyšší činná sopka v Evropě? 🌋", "a": ["etna"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **17 x 17**? 🧮", "a": ["289"], "xp": 100},
        {"q": "Jaká je chemická značka pro sodík? 🧪", "a": ["na"], "xp": 100},
        {"q": "Jaké je hlavní město Nového Zélandu? 🇳🇿", "a": ["wellington"], "xp": 100},
        {"q": "Ve kterém roce padla Berlínská zeď? 🧱", "a": ["1989"], "xp": 100},
        {"q": "Která řeka protéká Londýnem? 🌊", "a": ["temze", "temže"], "xp": 100},
        {"q": "Která země je známá jako 'Země vycházejícího slunce'? 🇯🇵", "a": ["japonsko"], "xp": 100},
        {"q": "Kolik kostí má dospělé lidské tělo? 🦴", "a": ["206"], "xp": 100},
        {"q": "Jak se jmenuje největší vnitrozemská vodní plocha / jezero na světě? 🌊", "a": ["kaspicke more", "kaspické moře", "kaspik"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš **DISCORD** pozpátku! 🔄", "a": ["drocsid"], "xp": 100},
        {"q": "Které pohoří tvoří tradiční hranici mezi Evropou a Asií? 🏔️", "a": ["ural"], "xp": 100},
        {"q": "Jaké je hlavní město Švédska? 🇸🇪", "a": ["stockholm"], "xp": 100},
        {"q": "Který objevitel v roce 1492 doplul do Ameriky? ⛵", "a": ["kristof kolumb", "krištof kolumbus", "kolumbus", "kristof kolumbus"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **1024 / 16**? 🧮", "a": ["64"], "xp": 100},
        {"q": "Ve kterém roce skončila 2. světová válka? 📜", "a": ["1945"], "xp": 100},
        {"q": "Jaké je nejsevernější hlavní město na světě? ❄️", "a": ["reykjavik", "reykjavík"], "xp": 100},
        {"q": "Který kov je za pokojové teploty kapalný? 🧪", "a": ["rtut", "rtuť"], "xp": 100},
        {"q": "Který plyn tvoří většinu atmosféry Země? 🌌", "a": ["dusik", "dusík"], "xp": 100},
        {"q": "Jak se jmenuje proces, při kterém rostliny vyrábějí kyslík? 🌿", "a": ["fotosynteza", "fotosyntéza"], "xp": 100},
        {"q": "Kdo napsal drama R.U.R., kde se poprvé objevilo slovo 'Robot'? 🤖", "a": ["karel capek", "karel čapek", "capek", "čapek"], "xp": 100},
        {"q": "Jaká je nejvyšší budova světa (v Dubaji)? 🏙️", "a": ["burj khalifa"], "xp": 100},
        {"q": "Ve kterém roce začala 1. světová válka? 📜", "a": ["1914"], "xp": 100},
        {"q": "Jaký je chemický symbol pro železo? 🧪", "a": ["fe"], "xp": 100},
        {"q": "Slovo pozpátku: Napiš **SERVER** pozpátku! 🔄", "a": ["revres"], "xp": 100},
        {"q": "Jak se jmenuje největší ostrov světa? 🏝️", "a": ["gronsko", "grónsko"], "xp": 100},
        {"q": "Ve kterém roce vzniklo samostatné Československo po 1. světové válce? 🇨🇿", "a": ["1918"], "xp": 100},
        {"q": "Kdo byl prvním člověkem, který vstoupil na povrch Měsíce (1969)? 🌕", "a": ["neil armstrong", "armstrong"], "xp": 100},
        {"q": "Která krevní skupina je považována za univerzálního dárce? 🩸", "a": ["0-", "0 negativni", "0 negativní", "0 minus", "0"], "xp": 100},
        {"q": "Ve kterém století proběhla Bitva na Bílé hoře (1620)? ⚔️", "a": ["17", "17.", "sedmnactem", "sedmnáctém"], "xp": 100},
        {"q": "Jak se jmenoval rakouský arcivévoda, jehož atentát v Sarajevě rozpoutal 1. světovou válku? 👑", "a": ["frantisek ferdinand", "františek ferdinand", "ferdinand", "frantisek ferdinand d'este"], "xp": 100},
        {"q": "Která řeka je nejdelší v České republice? 🌊", "a": ["vltava"], "xp": 100},
        {"q": "Jaké je hlavní město Španělska? 🇪🇸", "a": ["madrid"], "xp": 100},
        {"q": "Jak se nazývá samice od psa? 🐕", "a": ["fena"], "xp": 100},
        {"q": "Která planeta je nejblíže k naší Hvězdě (Slunci)? ☀️", "a": ["merkur"], "xp": 100},
        {"q": "Jaká je chemická značka pro kyslík? 🧪", "a": ["o", "o2", "kyslik", "kyslík"], "xp": 100},
        {"q": "Kolik minut má jedna celá hodina? ⏱️", "a": ["60"], "xp": 100},
        {"q": "Rychlá matematika: Kolik je **12 x 12**? 🧮", "a": ["144"], "xp": 100},
        {"q": "Jaké je hlavní město Itálie? 🇮🇹", "a": ["rim", "řím"], "xp": 100}
    ],

    # MEDIUM (Pokročilejší vědomosti, věda, historie, geografie)
    "medium": [
        {"q": "Jak se jmenovala karibská krize z roku 1962 ohledně raket na Kubě? 🚀", "a": ["kubanska", "kubánská", "kubanska krize", "kubánská krize"], "xp": 250},
        {"q": "Jak se jmenovala dohoda z roku 1938, ve které velmoci podstoupily české pohraničí Německu? 📜", "a": ["mnichovska dohoda", "mnichovská dohoda", "mnichovska", "mnichovská"], "xp": 250},
        {"q": "Jak se jmenoval spojenecký vojenský výsadek v Normandii v roce 1944 (Den D)? 🎖️", "a": ["operace overlord", "overlord"], "xp": 250},
        {"q": "Který renesanční sochař vytvořil mramorovou sochu Davida? 🗿", "a": ["michelangelo", "michelangelo buonarroti"], "xp": 250},
        {"q": "Jak se jmenovala kosmická loď, se kterou Neil Armstrong přistál na Měsíci? 🚀", "a": ["apollo 11", "apollo"], "xp": 250},
        {"q": "Jaké je hlavní město Egypta? 🇪🇬", "a": ["kahira", "káhira"], "xp": 250},
        {"q": "Který chemický prvek má značku **C**? 🧪", "a": ["uhlik", "uhlík"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **18 x 18**? 🧮", "a": ["324"], "xp": 250},
        {"q": "Jak se jmenuje náš první československý prezident? 🏛️", "a": ["tomas garrigue masaryk", "tomáš garrigue masaryk", "masaryk", "tgm"], "xp": 250},
        {"q": "Která řeka je nejdelší v Evropě? 🌊", "a": ["volha"], "xp": 250},
        {"q": "Jaké je hlavní město Číny? 🇨🇳", "a": ["peking", "beijing"], "xp": 250},
        {"q": "Který vědec objevil penicilin? 🧫", "a": ["alexander fleming", "fleming"], "xp": 250},
        {"q": "Jaká je chemická značka pro měď? 🧪", "a": ["cu"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **ALGORITMUS** pozpátku! 🔄", "a": ["sumtirogla"], "xp": 250},
        {"q": "Ve kterém roce byla založena organizace OSN? 🌐", "a": ["1945"], "xp": 250},
        {"q": "Jaké je hlavní město Portugalska? 🇵🇹", "a": ["lisabon"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **512 / 8**? 🧮", "a": ["64"], "xp": 250},
        {"q": "Který hudební génius složil operu Kouzelná flétna? 🎼", "a": ["mozart", "wolfgang amadeus mozart"], "xp": 250},
        {"q": "Jak se nazývá přechod skupenství z kapaliny na plyn za jakékoliv teploty? 💨", "a": ["odparovani", "odpařování", "vyparovani", "vypařování"], "xp": 250},
        {"q": "Jaké je hlavní město Norska? 🇳🇴", "a": ["oslo"], "xp": 250},
        {"q": "Kdo je autorem slavného antiutopického románu 1984? 📖", "a": ["george orwell", "orwell"], "xp": 250},
        {"q": "Rychlá matematika: Kolik je **19 x 19**? 🧮", "a": ["361"], "xp": 250},
        {"q": "Jaké je hlavní město Maďarska? 🇭🇺", "a": ["budapest", "budapešť"], "xp": 250},
        {"q": "Slovo pozpátku: Napiš **DATABASE** pozpátku! 🔄", "a": ["esabatad"], "xp": 250},
        {"q": "Která vrstva atmosféry nás chrání před škodlivým UV zářením? ☀️", "a": ["ozonova", "ozónová", "ozonova vrstva", "ozónová vrstva"], "xp": 250},
        {"q": "Ve kterém roce poprvé vyhořelo Národní divadlo v Praze? 🎭", "a": ["1881"], "xp": 250},
        {"q": "Jaká je chemická značka pro vápník (kalcium)? 🧪", "a": ["ca"], "xp": 250},
        {"q": "Jaké je hlavní město Argentiny? 🇦🇷", "a": ["buenos aires"], "xp": 250},
        {"q": "Jak se jmenoval slavný starověký řecký filosof, učitel Platóna? 🏛️", "a": ["sokrates", "sókratés"], "xp": 250},
        {"q": "Jak se jmenuje hlavní tepna lidského těla vycházející ze srdce? 🩸", "a": ["aorta"], "xp": 250},
        {"q": "Jaké je de facto hlavní (sídlem vlády) město Švýcarska? 🇨🇭", "a": ["bern"], "xp": 250},
        {"q": "Která země je nejlidnatějším vnitrozemským státem na světě? 🌍", "a": ["etiopie"], "xp": 250},
        {"q": "Jaká je přibližná rychlost světla ve vakuu v tisících km/s? (např. 300 000) ⚡", "a": ["300000", "299792", "300 000", "299 792"], "xp": 250},
        {"q": "Jak se jmenovala tajná operace atentátu na Reinharda Heydricha v roce 1942? 🎖️", "a": ["anthropoid", "operace anthropoid"], "xp": 250},
        {"q": "Který fyzik jako první v roce 1932 objevil neutron? ⚛️", "a": ["james chadwick", "chadwick"], "xp": 250},
        {"q": "Jaká je chemická značka pro draslík (Kalium)? 🧪", "a": ["k"], "xp": 250},
        {"q": "Jaká je chemická značka pro wolfram? 🧪", "a": ["w"], "xp": 250},
        {"q": "Jaká je chemická značka pro rtuť (Hydrargyrum)? 🧪", "a": ["hg"], "xp": 250},
        {"q": "Jaká je chemická značka pro olovo (Plumbum)? 🧪", "a": ["pb"], "xp": 250},
        {"q": "Jaká je chemická značka pro stříbro (Argentum)? 🧪", "a": ["ag"], "xp": 250},
        {"q": "Ve kterém roce začala Stoletá válka mezi Anglií a Francií? ⚔️", "a": ["1337"], "xp": 250},
        {"q": "Jak se jmenuje nejhlubší bod Mariánského příkopu? 🌊", "a": ["challengeruv prohluben", "challengerova prohluben", "challenger deep", "challenger"], "xp": 250},
        {"q": "Který filosof a matematik formuloval větu 'Cogito, ergo sum'? 🧠", "a": ["rene descartes", "rené descartes", "descartes"], "xp": 250},
        {"q": "Jak se jmenuje nejmenší kost v lidském těle? 🦴", "a": ["strminek", "třmínek", "strmínek"], "xp": 250},
        {"q": "Který zvířecí druh je považován za nejrychlejšího tvora na Zemi při střemhlavém letu? 🦅", "a": ["sokol stahovavy", "sokol stěhovavý", "sokol"], "xp": 250},
        {"q": "Jak se jmenuje největší zvíře, které kdy žilo na Zemi? 🐋", "a": ["vrastenec obrovsky", "vráskavec obrovský", "plejtvak obrovsky", "plejtvák obrovský"], "xp": 250},
        {"q": "Který ostrovní stát v Středozemním moři má hlavní město Vallettu? 🇲🇹", "a": ["malta"], "xp": 250},
        {"q": "Která planeta je čtvrtá od Slunce a říká se jí 'Rudá planeta'? 🪐", "a": ["mars"], "xp": 250},
        {"q": "Ve kterém roce došlo k havárii jaderné elektrárny Černobyl? ☢️", "a": ["1986"], "xp": 250},
        {"q": "Jak se jmenuje nejvyšší pohoří v České republice? 🏔️", "a": ["krkonose", "krkonoše"], "xp": 250},
        {"q": "Která země vyhrála první Mistrovství světa ve fotbale v roce 1930? ⚽", "a": ["uruguay"], "xp": 250},
        {"q": "Jaké je hlavní město Finska? 🇫🇮", "a": ["helsinky", "helsinki"], "xp": 250},
        {"q": "Který vědec navrhl teorii relativity? ⚛️", "a": ["albert einstein", "einstein"], "xp": 250}
    ],

    # HARD (Chytáky, detailní geografie, těžká historie, kultura a literatura)
    "hard": [
        {"q": "Jaké je zákonodárné hlavní město Jihoafrické republiky (JAR)? 🇿🇦", "a": ["kapske mesto", "kapské město", "cape town"], "xp": 500},
        {"q": "Které město bylo hlavním městem Kazachstánu před Astanou (do r. 1997)? 🇰🇿", "a": ["almaty", "alma-ata", "alma ata"], "xp": 500},
        {"q": "Který král Anglie založil anglikánskou církev a měl celkem 6 manželek? 👑", "a": ["jindrich viii", "jindřich viii", "jindrich 8", "jindřich 8", "henry viii"], "xp": 500},
        {"q": "Jak se jmenuje největší aktivní sopka na světě podle objemu (na Havaji)? 🌋", "a": ["mauna loa"], "xp": 500},
        {"q": "Jak se nazývá úžina oddělující Španělsko a Maroko? 🌊", "a": ["gibraltarska uzina", "gibraltarská úžina", "gibraltar"], "xp": 500},
        {"q": "Jaké je hlavní město Maroka? 🇲🇦", "a": ["rabat"], "xp": 500},
        {"q": "Jaké je hlavní město Mongolska? 🇲🇳", "a": ["ulanbatar", "ulánbátar", "ulan batar"], "xp": 500},
        {"q": "Jaké je hlavní město Turecka? (Pozor, Istanbul to není!) 🇹🇷", "a": ["ankara"], "xp": 500},
        {"q": "Jaké je hlavní město Vietnamu? 🇻🇳", "a": ["hanoj", "hanoi"], "xp": 500},
        {"q": "Jaké je hlavní město Keni? 🇰🇪", "a": ["nairobi"], "xp": 500},
        {"q": "Jaké je hlavní město Lichtenštejunska? 🇱🇮", "a": ["vaduz"], "xp": 500},
        {"q": "Slovo pozpátku: Napiš **RESTRUKTURALIZACE** pozpátku! 🔄", "a": ["ecazilarutkurtser"], "xp": 500},
        {"q": "Jak se jmenuje slavná Shakespeareova hra, kde vystupuje princ dánský a zazní 'Být, či nebýt'? 🎭", "a": ["hamlet"], "xp": 500},
        {"q": "Který britský evoluční biolog napsal v roce 1976 knihu 'Sobecký gen'? 🧬", "a": ["richard dawkins", "dawkins"], "xp": 500},
        {"q": "Jak se jmenuje postava z Shakespearova Kupce benátského, která požadovala liber masa jako splátku? 🎭", "a": ["shylock"], "xp": 500},
        {"q": "Který francouzský osvícenský filozof napsal satirický román Candide? 📖", "a": ["voltaire"], "xp": 500},
        {"q": "Který rakouský fyzik zformuloval myšlenkový experiment s kočkou v krabici? 🐱", "a": ["erwin schrodinger", "erwin schrödinger", "schrodinger", "schrödinger"], "xp": 500},
        {"q": "Který antický dramatik napsal tragédii Oidipus rex (Král Oidipus)? 🎭", "a": ["sofokles", "sofoklés"], "xp": 500},
        {"q": "Ve kterém přesném roce proběhla Bitva na Bílé hoře? ⚔️", "a": ["1620"], "xp": 500},
        {"q": "Který císař Svaté říše římské vládl během Bitvy na Bílé hoře? 👑", "a": ["ferdinand ii", "ferdinand ii.", "ferdinand 2"], "xp": 500},
        {"q": "Jak se jmenoval mírový traktát z roku 1648, který ukončil Třicetiletou válku? 📜", "a": ["vestfalsky mir", "vestfálský mír"], "xp": 500},
        {"q": "Která významná operace RAF v roce 1943 zničila přehrady v německém Porúří? 💣", "a": ["chastise", "operace chastise", "dambusters"], "xp": 500},
        {"q": "Jak se jmenovala linie opevnění, kterou Francie postavila na hranicích s Německem? 🛡️", "a": ["maginotova linie", "maginotova"], "xp": 500},
        {"q": "Ve kterém roce proběhla invaze vojsk Varšavské smlouvy do Československa? 🪖", "a": ["1968"], "xp": 500},
        {"q": "Jak se jmenovala první umělá družice Země vypuštěná SSSR v roce 1957? 🛰️", "a": ["sputnik 1", "sputnik"], "xp": 500},
        {"q": "Jak se jmenoval sovětský vůdce, který vedl SSSR během Karibské krize v roce 1962? 🏛️", "a": ["nikita chruscov", "nikita chruščov", "chruscov", "chruščov"], "xp": 500},
        {"q": "Jak se jmenoval český malíř a grafik, který vytvořil dílo 'Slovanská epopej'? 🎨", "a": ["alfons mucha", "mucha"], "xp": 500},
        {"q": "Která řeka je nejdelší na světě podle nejnovějších měření (překonává Nil)? 🌊", "a": ["amazonka"], "xp": 500},
        {"q": "Jak se jmenuje nejvyšší vodopád na světě (nachází se ve Venezuele)? 🌊", "a": ["angeluv vodopad", "angelův vodopád", "salto angel", "angel"], "xp": 500},
        {"q": "Který slavný norský malíř vytvořil ikonický obraz 'Výkřik' (Scream)? 🖼️", "a": ["edvard munch", "munch"], "xp": 500},
        {"q": "Jak se jmenovala římská provincie na území dnešní Francie a Belgie? 🛡️", "a": ["galie"], "xp": 500},
        {"q": "Který slavný polský astronom dokázal, že Země obíhá kolem Slunce? 🌌", "a": ["mikulas kopernik", "mikuláš koperník", "kopernik", "koperník"], "xp": 500},
        {"q": "Které město v Kanadě je druhé největší a hovoří se v něm převážně francouzsky? 🇨🇦", "a": ["montreal"], "xp": 500},
        {"q": "Jak se jmenoval perský král, kterého Alexandr Veliký porazil v bitvě u Gaugamél? ⚔️", "a": ["dareios iii", "dareios 3", "darios iii", "dareios"], "xp": 500},
        {"q": "Který slavný objevitel jako první vedením výpravy obeplul Zemi (i když během ní zemřel)? ⛵", "a": ["fernao de magalhaes", "fernando magalhaes", "magalhaes", "magellan"], "xp": 500},
        {"q": "Ve kterém roce proběhla Velká francouzská revoluce (dobytí Bastily)? 📜", "a": ["1789"], "xp": 500},
        {"q": "Jak se jmenuje nejvyšší hora Afriky? 🏔️", "a": ["kilimandzaro", "kilimandžáro"], "xp": 500},
        {"q": "Která země darovala USA slavnou Sochu Svobody? 🗽", "a": ["francie"], "xp": 500},
        {"q": "Jaká je chemická značka pro zlato, stříbro a měď (v tomto pořadí bez mezer/čárek)? 🧪", "a": ["auagcu"], "xp": 500}
    ],

    # ULTRA HARD (Široký všeobecný přehled: Historie, Přírodopis, Geografie, Kultura, Věda, Osobnosti)
    "ultrahard": [
        {"q": "Jak se jmenoval úplně první pes, který se vrátil z vesmíru ŽIVÝ (společně s Bělkou)? 🐕", "a": ["strelka", "střelka"], "xp": 1000},
        {"q": "Jaké je přesné kódové označení (písmeno a číslo) první německé ponorky potopené ve 2. světové válce? ⚓", "a": ["u-27", "u27"], "xp": 1000},
        {"q": "Jak se jmenovala vlajková loď Kryštofa Kolumba při jeho první výpravě v roce 1492? ⛵", "a": ["santa maria"], "xp": 1000},
        {"q": "Která starověká bitva v roce 480 př. n. l. proslavila spartského krále Leónida proti Peršanům? ⚔️", "a": ["bitva u thermopyl", "thermopyl", "thermopylae"], "xp": 1000},
        {"q": "Který římský císař vládl v době, kdy v roce 79 n. l. výbuch Vesuvu zničil Pompeje? 🏛️", "a": ["titus"], "xp": 1000},
        {"q": "Jak se jmenovala první žena, která vzlétla do vesmíru (v roce 1963)? 🚀", "a": ["valentina tereskovova", "valentina těreškovová", "tereskovova", "těreškovová"], "xp": 1000},
        {"q": "Ve kterém roce byl spáchán atentát na amerického prezidenta Johna F. Kennedyho v Dallasu? 📜", "a": ["1963"], "xp": 1000},
        {"q": "Ve kterém roce byla podepsána Magna Charta Libertatum v Anglii? 📜", "a": ["1215"], "xp": 1000},
        {"q": "Který švédský král padl v bitvě u Lützenu v roce 1632 během Třicetileté války? ⚔️", "a": ["gustav ii adolf", "gustav adolf", "gustav 2 adolf"], "xp": 1000},
        {"q": "Jaké je hlavní město Myanmaru (Barmy)? (Není to Rangún!) 🇲🇲", "a": ["naypyidaw", "najpijto"], "xp": 1000},
        {"q": "Jaké je oficiální ústavní/hlavní město Bolívie (sídlo vlády je La Paz)? 🇧🇴", "a": ["sucre"], "xp": 1000},
        {"q": "Jaké je hlavní město Šalamounových ostrovů? 🇸🇧", "a": ["honiara"], "xp": 1000},
        {"q": "Jak se jmenuje nejlidnatější ostrov na světě (nachází se v Indonésii)? 🏝️", "a": ["java", "jáva"], "xp": 1000},
        {"q": "Které je nejchladnější trvale obydlené místo na Zemi (vesnice na Sibiři)? ❄️", "a": ["ojmjakon", "oimjakon"], "xp": 1000},
        {"q": "Který vnitrozemský stát Jižní Ameriky nemá žádný přístup k moři (kromě Bolívie)? 🌎", "a": ["paraguay"], "xp": 1000},
        {"q": "Jaké je hlavní město Madagaskaru? 🇲🇬", "a": ["antananarivo"], "xp": 1000},
        {"q": "Jaké je atomové číslo (protonové číslo) Oganessonu (Og)? ⚛️", "a": ["118"], "xp": 1000},
        {"q": "Jaká je přesná frekvence (v Hz) tónu komorního A (A4) podle mezinárodní normy ISO 16? 🎼", "a": ["440", "440hz", "440 hz"], "xp": 1000},
        {"q": "Jak se jmenuje největší žijící ještěr na světě (žije v Indonésii)? 🦎", "a": ["varan komodsky", "varan komodský"], "xp": 1000},
        {"q": "Který chemický prvek má nejvyšší bod tání ze všech kovů (přes 3400 °C)? 🧪", "a": ["wolfram"], "xp": 1000},
        {"q": "Jak se jmenuje vědní obor zabývající se studiem mechů a játrovek? 🌿", "a": ["bryologie"], "xp": 1000},
        {"q": "Která část lidského mozku je zodpovědná za koordinaci pohybů a rovnováhu? 🧠", "a": ["mozecek", "mozeček"], "xp": 1000},
        {"q": "Jak se jmenuje hlavní hormon štítné žlázy, který obsahuje jód? 🩸", "a": ["thyroxin", "tiroxin"], "xp": 1000},
        {"q": "Kdo byl architektem, který navrhl ikonický vysílač a hotel na Ještědu? 🏔️", "a": ["karel hubacek", "karel hubáček", "hubacek", "hubáček"], "xp": 1000},
        {"q": "Jak se jmenovala první manželka Jindřicha VIII., kvůli které se odtrhl od katolické církve? 👑", "a": ["katerina aragonska", "kateřina aragonská"], "xp": 1000},
        {"q": "Který český barokní skladatel složil slavné dílo 'Missa Sanctissimae Trinitatis'? 🎼", "a": ["jan dismas zelenka", "zelenka"], "xp": 1000},
        {"q": "Který španělský architekt navrhl slavnou baziliku Sagrada Família v Barceloně? 🏰", "a": ["antoni gaudi", "antoni gaudí", "gaudi", "gaudí"], "xp": 1000},
        {"q": "Kdo napsal slavný antický epos Ilias a Odysseia? 📖", "a": ["homer", "homér"], "xp": 1000},
        {"q": "Jak se jmenovala slavná římská gladiátorka / koncept gladiátorky (ženský ekvivalent)? 🗡️", "a": ["gladiatrix"], "xp": 1000},
        {"q": "Slovo pozpátku: Napiš **NEJNEOBHOSPODAŘOVATELNĚJŠÍMI** pozpátku! 🔄", "a": ["imijsotelavodapsohboennejen"], "xp": 1000},
        {"q": "Jaký je přesný chybový kód HTTP protokolu pro 'I'm a teapot' (Jsem čajová konvice)? ☕", "a": ["418"], "xp": 1000},
        {"q": "Jak se jmenovala první počítačová síť z roku 1969, která byla předchůdcem Internetu? 🌐", "a": ["arpanet"], "xp": 1000},
        {"q": "Které číslo je v hexadecimální (šestnáctkové) soustavě reprezentováno řetězcem 'FF'? 🔢", "a": ["255"], "xp": 1000},
        {"q": "Jaké bylo původní kódové označení (codename) pro Windows 95 během vývoje? 💻", "a": ["chicago"], "xp": 1000}
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
        app_commands.Choice(name="⚽ Fotbalové", value="football")
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
            "medium": ("🟡 STŘEDNÍ", discord.Color.gold()),
            "hard": ("🔴 TĚŽKÁ", discord.Color.red()),
            "ultrahard": ("🟣 ULTRA TĚŽKÁ", discord.Color.purple()),
            "football": ("⚽ FOTBALOVÉ", discord.Color.blue())
        }
        
        diff_label, color = diff_config[selected_diff]

        question_data = random.choice(QUESTIONS[selected_diff])
        question_text = question_data["q"]
        correct_answers = question_data["a"]
        xp_reward = question_data["xp"]

        embed = discord.Embed(
            title="⚡ CHAT REVIVE - KVÍZ ⚡",
            description=f"**{question_text}**\n\nNapiš odpověď přímo do chatu!\n*(Máš na to 1 minut)*",
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
            winner_msg = await self.bot.wait_for('message', timeout=60.0, check=check)
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