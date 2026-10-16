# Counting 2.0

Česká counting minihra pro Discord s PostgreSQL / Supabase Session poolerem.

## Co je nové

- `/counting info`: aktuální číslo, serverový rekord, série, další milník a pravidla.
- `/counting leaderboard`: dnešní, týdenní a celkové pořadí; přepínače, stránkování po 10 a obnovení. Tlačítka ovládá autor příkazu a po 3 minutách neaktivity se vypnou. Po restartu otevři nový přehled.
- `/counting profile [user]`: celkový a denní počet, pořadí, úspěšnost, výdělky a 7 achievementů od prvního čísla po 10 000. Ranky jsou označení v profilu, nevytvářejí Discord role.
- Oslavy stovek, tisícovek a nových osobních achievementů bez pingování uživatelů.
- `/counting help`: nápověda přímo na Discordu.

## Administrace

| Příkaz | Význam |
| --- | --- |
| `/counting setup_channel` | Vybere kanál, výchozí číslo a reset při chybě. Výchozí číslo je poslední již dosažené číslo. |
| `/counting set_number` | Ruční oprava čísla. Nemaže statistiky; zahájí novou sérii. |
| `/counting settings` | Volby `solo`, `reset`, `cooldown` (0–60 s), `reactions`, `paused`. Bez parametrů vypíše nastavení. |
| `/counting rewards` | Tokeny za novou stovku (0–100), gemy za novou tisícovku (0–1000). Nula danou odměnu vypne. |
| `/counting setup_time` | Čas HH:MM v Europe/Prague nebo `off`. Souhrn ukazuje **předchozí kalendářní den**. |

Výchozí pravidla: sólo povoleno, cooldown 0 s, reakce zapnuté, 1 token za stovku a 80 gemů za tisícovku místo tokenu. Původní nastavení resetu zůstává.

### Počítání a férovost

První slovo zprávy musí být celé nezáporné číslo složené z číslic 0–9 (např. `42 dobré ráno`). Výrazy, desetinná čísla, záporná čísla a běžný chat se ignorují. Horní hranice je 2 miliardy. Upravené či smazané zprávy skóre nemění.

- ✅ číslo uloženo; ❌ chybné číslo; ⏳ zakázané sólo nebo cooldown (bez resetu); ⚠️ databázová chyba, číslo nebylo potvrzeno.
- Měnu získává autor milníku. Stejný serverový milník se odměňuje jen jednou, i po resetu. Ruční posunutí čísla dopředu přeskočené odměny nevyplácí a posune hranici pro budoucí odměny.
- Nastavení, číslo, statistiky a Brawl odměna se zapisují v transakci. Zámek serverového řádku brání současnému přijetí stejného čísla; ID zpráv brání opakovanému zpracování po restartu. Opožděné zprávy s ID nižším než poslední zpracované ID se ignorují.
- Pro jeden token provozuj jen jednu instanci bota; starší verze nezná novou ochranu.

## Databáze a přechod

Při startu `database.py` automaticky spustí přidávací migraci z `counting_store.py`. Stávající tabulky a Brawl zůstatky se nemažou. Aktuální číslo založí počáteční rekord; historický rekord nelze zpětně zjistit. Existující celková skóre zůstávají. Staré denní počty nemají datum, proto se jednorázově přiřadí dni migrace. Historické týdenní výsledky se nedopočítávají. Chyby a získaná měna v profilech se začínají evidovat upgradem.

Dny se mění o půlnoci a týdny v pondělí podle Europe/Prague, včetně letního času. Souhrn nenuluje živá skóre. Po výpadku se souhrn za včerejšek doplní po spuštění téhož dne; více vynechaných dní se zpětně neposílá. Databázová rezervace brání běžnému dvojímu odeslání, ale pád procesu mezi rezervací a odesláním může souhrn vynechat (Discord zpráva a SQL nejsou jedna transakce).

Denní agregace starší než 35 dní se pro úsporu prostoru mažou; celkové skóre a měna zůstávají. Mimo counting kanál není žádný databázový dotaz. Nastavení se načte při startu, při změně příkazem a jednou za minutu. Pool používá nejvýše 5 spojení.

## Nasazení

1. Před upgradem zazálohuj produkční databázi.
2. Nasaď společně `cogs/counting.py`, `counting_store.py`, `database.py` a `requirements.txt` z této větve. Nepřejmenovávej soubor na `Counting.py` ani nenechávej oba soubory v `cogs`.
3. Render stále používá `python -u main.py`, `DATABASE_URL` a `DISCORD_TOKEN`. Tajné údaje patří pouze do Environment / lokálního `.env`.
4. Po startu ověř načtení cogu a synchronizaci slash příkazů. Stávající kanál zůstává nastavený; zbytečně znovu nespouštěj setup s nulou.
5. Vyzkoušej `/counting info`, `/counting leaderboard`, `/counting profile`. Na testovacím serveru ověř správné číslo, chybu, cooldown a restart.

## Testy

Lokální jednotkové testy: `pip install -r requirements.txt pytest pytest-asyncio` a `python -m pytest -q`.

Integrační testy: nastav `TEST_DATABASE_URL` na **samostatnou zahoditelnou PostgreSQL databázi**. Testy v ní mažou celé schéma `public`. Nikdy nepoužívej produkční URL. Pokrývají migraci, souběžné zpracování, rollback, odměny, reset, cooldown, dny/týdny a oddělení serverů.

GitHub Actions tyto testy spouští proti vlastnímu PostgreSQL 16; nepotřebuje produkční hesla.
