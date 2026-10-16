"""Counting 2.0 — Czech community game with transactional PostgreSQL storage."""
import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import db
from counting_store import CountingStore, ZONE, MAX_NUMBER, ACHIEVEMENTS, parse_number, rank, today

log = logging.getLogger(__name__)
ACCENT = 0x8B5CF6
PERIODS = {'daily': 'Dnes', 'weekly': 'Tento týden', 'lifetime': 'Celkově'}


def fmt(number):
    return f'{number:,}'.replace(',', ' ')


def card(title, description=None, color=ACCENT):
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text='PUVOD • COUNTING 2.0 • Europe/Prague')
    return e


def standings(rows, page=0):
    medals = ['🥇', '🥈', '🥉']
    return '\n'.join(f'{medals[i] if page == 0 and i < 3 else str(page*10+i+1)+"."} '
                     f'<@{r["user_id"]}>  **{fmt(r["score"])}**' for i,r in enumerate(rows[:10])) or 'První místo čeká na tebe. Napiš první správné číslo!'


class LeaderboardView(discord.ui.View):
    def __init__(self, cog, owner, guild_id, period):
        super().__init__(timeout=180)
        self.cog, self.owner, self.guild_id = cog, owner, guild_id
        self.period, self.page, self.message = period, 0, None
        self.lock = asyncio.Lock()

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message('Vlastní přehled otevřeš přes `/counting leaderboard`.', ephemeral=True)
        return False

    async def render(self):
        rows = await self.cog.store.leaderboard(self.guild_id,self.period,self.page)
        if not rows and self.page:
            self.page = 0
            rows = await self.cog.store.leaderboard(self.guild_id,self.period,0)
        self.previous.disabled = self.page == 0
        self.next_page.disabled = len(rows) <= 10
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label in PERIODS.values():
                item.style = discord.ButtonStyle.primary if item.label == PERIODS[self.period] else discord.ButtonStyle.secondary
        e = card(f'🏆 Žebříček · {PERIODS[self.period]}', standings(rows,self.page))
        e.set_footer(text=f'PUVOD • Strana {self.page+1} • Ovládání platí 3 minuty • Europe/Prague')
        return e

    async def change(self, interaction, period=None, step=0):
        await interaction.response.defer()
        async with self.lock:
            if period:
                self.period, self.page = period, 0
            self.page = max(0,self.page+step)
            await interaction.edit_original_response(embed=await self.render(),view=self)

    @discord.ui.button(label='Dnes', row=0)
    async def daily(self, i, b):
        await self.change(i,'daily')

    @discord.ui.button(label='Tento týden', row=0)
    async def weekly(self, i, b):
        await self.change(i,'weekly')

    @discord.ui.button(label='Celkově', row=0)
    async def lifetime(self, i, b):
        await self.change(i,'lifetime')

    @discord.ui.button(label='Zpět', emoji='⬅️', row=1)
    async def previous(self, i, b):
        await self.change(i,step=-1)

    @discord.ui.button(label='Obnovit', emoji='🔄', row=1)
    async def refresh(self, i, b):
        await self.change(i)

    @discord.ui.button(label='Další', emoji='➡️', row=1)
    async def next_page(self, i, b):
        await self.change(i,step=1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_error(self, interaction, error, item):
        log.error('Counting button failed',exc_info=(type(error),error,error.__traceback__))
        await interaction.followup.send('Přehled se nepodařilo načíst. Zkus nový `/counting leaderboard`.',ephemeral=True)


@app_commands.guild_only()
class Counting(commands.GroupCog, name='counting'):
    def __init__(self, bot):
        self.bot = bot
        self.store = CountingStore(db.pool)
        self.configs = {}
        self.locks = {}
        self.views = set()
        self.cleaned_on = None

    async def cog_load(self):
        await self.refresh_configs()
        self.maintenance.start()

    def cog_unload(self):
        self.maintenance.cancel()
        for view in self.views:
            view.stop()

    async def refresh_configs(self):
        self.configs = {int(r['guild_id']): dict(r) for r in await self.store.configs()}

    async def save(self, guild_id, **values):
        # Serialize admin changes with messages inside this process as well as in SQL.
        async with self.locks.setdefault(guild_id,asyncio.Lock()):
            result = await self.store.configure(guild_id,**values)
            self.configs[guild_id] = dict(result)
            return result

    @app_commands.command(name='setup_channel',description='Nastaví counting kanál, výchozí číslo a reset při chybě.')
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel,
                            výchozí_číslo: app_commands.Range[int,0,1_999_999_999]=0, reset_po_chybe: bool=True):
        await interaction.response.defer(ephemeral=True)
        p = channel.permissions_for(interaction.guild.me)
        if not (p.view_channel and p.send_messages and p.embed_links and p.add_reactions and p.read_message_history):
            return await interaction.followup.send('V kanálu potřebuji View Channel, Send Messages, Embed Links, Add Reactions a Read Message History.',ephemeral=True)
        await self.save(interaction.guild_id,counting_channel_id=channel.id,current_number=výchozí_číslo,reset_on_fail=int(reset_po_chybe))
        await interaction.followup.send(embed=card('✨ Counting je připraven',f'Kanál: {channel.mention}\nDalší číslo: **{fmt(výchozí_číslo+1)}**\nPravidla a odměny: `/counting info`\nDalší nastavení: `/counting settings`'),ephemeral=True)

    @app_commands.command(name='set_number',description='Posune číslo bez připsání statistik nebo odměn.')
    @app_commands.checks.has_permissions(administrator=True)
    async def set_number(self, interaction: discord.Interaction, číslo: app_commands.Range[int,0,1_999_999_999]):
        await interaction.response.defer(ephemeral=True)
        await self.save(interaction.guild_id,current_number=číslo)
        await interaction.followup.send(f'✅ Další číslo je **{fmt(číslo+1)}**. Statistiky zůstaly zachované.',ephemeral=True)

    @app_commands.command(name='settings',description='Upraví pravidla, cooldown a reakce. Bez parametrů ukáže nastavení.')
    @app_commands.checks.has_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction, solo: bool | None=None,
                       reset: bool | None=None, cooldown: app_commands.Range[int,0,60] | None=None,
                       reactions: bool | None=None, paused: bool | None=None):
        await interaction.response.defer(ephemeral=True)
        values = {k:v for k,v in {'counting_allow_solo':solo,'reset_on_fail':int(reset) if reset is not None else None,
                  'counting_cooldown':cooldown,'counting_reactions':reactions,'counting_paused':paused}.items() if v is not None}
        if values:
            await self.save(interaction.guild_id,**values)
        await interaction.followup.send(embed=await self.info_embed(interaction.guild_id),ephemeral=True)

    @app_commands.command(name='rewards',description='Nastaví Brawl odměny za nové stovky a tisícovky; 0 odměnu vypne.')
    @app_commands.checks.has_permissions(administrator=True)
    async def rewards(self, interaction: discord.Interaction, tokens: app_commands.Range[int,0,100]=1,
                      gems: app_commands.Range[int,0,1000]=80):
        await interaction.response.defer(ephemeral=True)
        await self.save(interaction.guild_id,counting_tokens=tokens,counting_gems=gems)
        await interaction.followup.send(f'🎁 Nová stovka: **{tokens} tokenů**. Nová tisícovka: **{gems} gemů** místo tokenů.\nOdměnu získá autor milníku, každý milník se platí jen jednou za server.',ephemeral=True)

    @app_commands.command(name='setup_time',description='Denní souhrn v českém čase HH:MM; off ho vypne. Shrnuje včerejšek.')
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_time(self, interaction: discord.Interaction, time: str):
        if time.lower() != 'off':
            try:
                parsed = datetime.strptime(time,'%H:%M')
                time = parsed.strftime('%H:%M')
            except ValueError:
                return await interaction.response.send_message('Zadej čas HH:MM, například `08:00`, nebo `off`.',ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.save(interaction.guild_id,counting_time=None if time.lower()=='off' else time)
        await interaction.followup.send('⏰ Souhrn vypnut.' if time.lower()=='off' else f'⏰ V {time} (Europe/Prague) pošlu výsledky za předchozí kalendářní den. Při výpadku je doplním po startu téhož dne.',ephemeral=True)

    async def info_embed(self, guild_id):
        s = await self.store.settings(guild_id)
        if not s or not s['counting_channel_id']:
            return card('🔢 Counting', 'Administrátor nejdřív vybere kanál přes `/counting setup_channel`.')
        n = s['current_number'] or 0
        milestone = (n//100+1)*100
        e = card('🔢 Counting · přehled',f'<#{s["counting_channel_id"]}> • '+('⏸️ Pozastaveno' if s['counting_paused'] else '🟢 Hrajeme'))
        e.add_field(name='Další číslo',value=f'**{fmt(n+1)}**')
        e.add_field(name='Rekord serveru',value=fmt(s['counting_record']))
        e.add_field(name='Série bez chyby',value=fmt(s['current_streak'] or 0))
        e.add_field(name='Další milník',value=f'**{fmt(milestone)}** • zbývá {milestone-n} čísel',inline=False)
        e.add_field(name='Pravidla',value=f'Sólo za sebou: {"ano" if s["counting_allow_solo"] else "ne"}\nReset při chybě: {"ano" if s["reset_on_fail"] else "ne"}\nCooldown hráče: {s["counting_cooldown"]} s\nReakce na úspěch: {"ano" if s["counting_reactions"] else "ne"}',inline=True)
        e.add_field(name='Odměny',value=f'Nová stovka: **{s["counting_tokens"]} tokenů**\nNová tisícovka: **{s["counting_gems"]} gemů** (místo tokenů)\nMilníky do {fmt(s["counting_reward_highwater"])} se znovu neodměňují.',inline=True)
        e.add_field(name='Denní souhrn',value=s['counting_time'] or 'Vypnutý',inline=False)
        return e

    @app_commands.command(name='info',description='Přehled hry, rekord, pravidla a další milník.')
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(embed=await self.info_embed(interaction.guild_id))

    @app_commands.command(name='leaderboard',description='Interaktivní denní, týdenní a celkový žebříček.')
    @app_commands.choices(typ=[app_commands.Choice(name=v,value=k) for k,v in PERIODS.items()])
    async def leaderboard(self, interaction: discord.Interaction, typ: str='daily'):
        await interaction.response.defer()
        view = LeaderboardView(self,interaction.user.id,interaction.guild_id,typ if typ in PERIODS else 'daily')
        self.views = {v for v in self.views if not v.is_finished()}
        self.views.add(view)
        view.message = await interaction.followup.send(embed=await view.render(),view=view,wait=True)

    @app_commands.command(name='profile',description='Osobní rank, úspěšnost, statistiky a odemčené achievementy.')
    async def profile(self, interaction: discord.Interaction, user: discord.Member | None=None):
        await interaction.response.defer()
        user = user or interaction.user
        p = await self.store.profile(interaction.guild_id,user.id)
        total, errors = p['lifetime_counts'],p['mistakes']
        e = card(f'👤 {user.display_name[:80]} · {rank(total)}')
        e.set_thumbnail(url=user.display_avatar.url)
        e.add_field(name='Správná čísla',value=f'**{fmt(total)}** celkem\n{fmt(p["today"])} dnes')
        e.add_field(name='Umístění',value=f'#{p["position"]}' if total else 'Zatím bez pořadí')
        e.add_field(name='Úspěšnost',value=f'{100*total/(total+errors):.1f}% • {fmt(errors)} chyb' if total+errors else 'Zatím bez pokusů')
        e.add_field(name='Vyděláno countingem',value=f'🪙 {fmt(p["earned_tokens"])} tokenů • 💎 {fmt(p["earned_gems"])} gemů',inline=False)
        next_rank = next(((target,name) for target,name in ACHIEVEMENTS if target>total),None)
        if next_rank:
            e.add_field(name='Další rank',value=f'{next_rank[1]} • ještě **{fmt(next_rank[0]-total)}** správných čísel',inline=False)
        e.add_field(name='Achievementy',value='\n'.join(f'{"✅" if total>=target else "🔒"} **{name}** · {fmt(target)}' for target,name in ACHIEVEMENTS),inline=False)
        e.set_footer(text='PUVOD • Chyby a výdělky se sledují od upgradu; rank není Discord role.')
        await interaction.followup.send(embed=e)

    @app_commands.command(name='help',description='Pravidla a seznam funkcí Counting 2.0.')
    async def help(self, interaction: discord.Interaction):
        e = card('✨ Counting 2.0', 'Společně zvyšujte číslo o **1**. Počítá se první slovo zprávy; text za číslem je povolen. Úpravy a smazání zpráv nemění skóre.')
        e.add_field(name='Pro hráče',value='`/counting info` — stav a pravidla\n`/counting leaderboard` — žebříčky s tlačítky\n`/counting profile` — rank a achievementy',inline=False)
        e.add_field(name='Pro administrátory',value='`setup_channel` • `set_number` • `settings` • `rewards` • `setup_time`',inline=False)
        e.add_field(name='Férová hra',value='Odměnu dostává autor nového serverového milníku. Reset ji neobnoví. Zakázané sólo nebo cooldown číslo neresetují. Den začíná o půlnoci a týden v pondělí, vždy podle Europe/Prague.',inline=False)
        await interaction.response.send_message(embed=e,ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        config = self.configs.get(message.guild.id)
        if not config or message.channel.id != config['counting_channel_id'] or config['counting_paused']:
            return
        number = parse_number(message.content)
        if number is None:
            return
        async with self.locks.setdefault(message.guild.id,asyncio.Lock()):
            try:
                r = await self.store.submit(message.guild.id,message.channel.id,message.author.id,message.id,number,message.created_at)
            except Exception:
                log.exception('Counting database write failed; message %s not confirmed',message.id)
                # Do not pretend that the number was accepted; never reset on a DB error.
                try:
                    await message.add_reaction('⚠️')
                except discord.HTTPException:
                    pass
                return
            try:
                if r['status']=='ignored':
                    return
                if r['status'] in ('solo','cooldown'):
                    await message.add_reaction('⏳')
                    return
                if r['status']=='wrong':
                    await message.add_reaction('❌')
                    if r['reset']:
                        await message.channel.send(embed=card('💥 Série přerušena',f'{message.author.mention}, čekalo se **{fmt(r["expected"])}**.\nDalší číslo je **1**. Rekord a statistiky zůstávají.',0xEF4444),allowed_mentions=discord.AllowedMentions.none())
                    return
                if r['reactions']:
                    await message.add_reaction(discord.utils.get(message.guild.emojis,name='verify') or '✅')
                unlocked = next((name for target,name in ACHIEVEMENTS if target==r['total']),None)
                if number%100==0 or unlocked:
                    lines = [f'{message.author.mention} zapsal **{fmt(number)}**.']
                    if r['record'] and number%100==0:
                        lines.append('🏆 Nový rekord serveru!')
                    if r['tokens'] or r['gems']:
                        lines.append(f'🎁 +{r["tokens"]} tokenů • +{r["gems"]} gemů')
                    if unlocked:
                        lines.append(f'✨ Achievement odemčen: **{unlocked}**')
                    await message.channel.send(embed=card('🎉 Milník dosažen' if number%100==0 else '✨ Nový achievement','\n'.join(lines),0xFBBF24),allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.exception('Counting saved, but Discord feedback failed for message %s',message.id)

    @tasks.loop(minutes=1)
    async def maintenance(self):
        try:
            await self.refresh_configs()
            if self.cleaned_on != today():
                await self.store.cleanup()
                self.cleaned_on = today()
            self.views = {v for v in self.views if not v.is_finished()}
        except Exception:
            log.exception('Counting maintenance failed; retrying next minute')
            return
        now = datetime.now(ZONE)
        for gid, config in list(self.configs.items()):
            scheduled = config['counting_time']
            if (not scheduled or now.strftime('%H:%M') < scheduled
                    or config['counting_summary_date'] == now.date()):
                continue
            channel = self.bot.get_channel(config['counting_channel_id'])
            if not channel:
                continue
            claimed = False
            try:
                day = now.date()-timedelta(days=1)
                claimed = bool(await self.store.claim_summary(gid,now.date()))
                if claimed:
                    rows = await self.store.leaderboard(gid,'daily',day=day)
                    await channel.send(embed=card(f'🌙 Denní souhrn · {day:%d. %m. %Y}',standings(rows)),allowed_mentions=discord.AllowedMentions.none())
            except Exception:
                log.exception('Counting daily summary failed for guild %s',gid)
                if claimed:
                    try:
                        await self.store.release_summary(gid,now.date())
                    except Exception:
                        log.exception('Could not release summary claim')

    @maintenance.before_loop
    async def before_maintenance(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Counting(bot))
