"""Skutečné vítání, loučení a serverové logy pro Puvod Bota.

Nastav přes /setup_vitej, /setup_goodbye, /setup_logs.
Konfiguraci čte z tabulky guild_settings v Supabase PostgreSQL.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from database import db

logger = logging.getLogger(__name__)
CONFIG_CACHE_SECONDS = 45.0

DEFAULT_WELCOME = "Ahoj {user}, vítej na **{server}**! Jsme rádi, že jsi tady. Rozkoukej se a užij si to s námi."
DEFAULT_WELCOME_TITLE = "VÍTEJ NA {server}!"
DEFAULT_WELCOME_COLOR = "#8B5CF6"
DEFAULT_WELCOME_STYLE = "clean"
DEFAULT_WELCOME_EMOJI = "✨"
DEFAULT_GOODBYE = "**{username}** opustil(a) server **{server}**. 👋"

CONFIG_SQL = """
    SELECT welcome_channel_id, goodbye_channel_id, logs_channel_id,
           welcome_message, goodbye_message,
           welcome_title, welcome_emoji, welcome_color, welcome_banner,
           welcome_rules_channel_id, welcome_style
      FROM guild_settings WHERE guild_id = $1
"""


@dataclass(frozen=True)
class EventConfig:
    welcome_channel_id: int | None = None
    goodbye_channel_id: int | None = None
    logs_channel_id: int | None = None
    welcome_message: str | None = None
    goodbye_message: str | None = None
    welcome_title: str | None = None
    welcome_emoji: str | None = None
    welcome_color: str | None = None
    welcome_banner: str | None = None
    welcome_rules_channel_id: int | None = None
    welcome_style: str | None = None


def _safe(value: str, limit: int = 950) -> str:
    """Výňatek zprávy vhodný do Discord embedu, bez pingování dalších uživatelů."""
    value = discord.utils.escape_mentions(value or "")
    value = discord.utils.escape_markdown(value)
    if not value:
        return "*(bez textu / zpráva nebyla v cache)*"
    return value[:limit] + ("…" if len(value) > limit else "")


def render_template(template: str, *, member: discord.Member,
                    departing: bool = False) -> str:
    """Pouze bezpečná explicitní substituce, bez formátovacích výrazů."""
    guild = member.guild
    subs = {
        "{user}": discord.utils.escape_markdown(member.display_name) if departing else member.mention,
        "{username}": discord.utils.escape_markdown(member.display_name),
        "{server}": discord.utils.escape_markdown(guild.name),
        "{count}": str(guild.member_count if guild.member_count is not None else "?"),
    }
    for key, value in subs.items():
        template = template.replace(key, value)
    return template[:1900]


def make_welcome_embed(member: discord.Member, cfg: EventConfig) -> discord.Embed:
    """Jediný renderer pro skutečné příchody i admin náhledy."""
    guild = member.guild
    style = cfg.welcome_style if cfg.welcome_style in ("clean", "minimal", "premium") else DEFAULT_WELCOME_STYLE
    raw_color = cfg.welcome_color or DEFAULT_WELCOME_COLOR
    try:
        color = discord.Color(int(raw_color.lstrip("#"), 16))
    except (ValueError, TypeError):
        color = discord.Color(0x8B5CF6)

    # Emoji je před uložením validované proti emoji serveru. Pokud bylo
    # mezitím smazáno, Discord jej nemusí správně vykreslit, ale bot nespadne.
    emoji = cfg.welcome_emoji or DEFAULT_WELCOME_EMOJI
    title = render_template(cfg.welcome_title or DEFAULT_WELCOME_TITLE, member=member)
    content = render_template(cfg.welcome_message or DEFAULT_WELCOME, member=member)

    # Všechna možná @everyone a @role jsou navíc blokovaná v channel.send.
    intro = f"{emoji}  **NOVÝ ČLEN NA SERVERU**"
    if style == "minimal":
        description = f"{emoji}  {content}"
    elif style == "premium":
        description = f"{intro}\n\n{content}\n\n*Vítej v naší komunitě. Tvoje místo už čekalo.*"
    else:
        description = f"{intro}\n\n{content}"

    embed = discord.Embed(title=title[:256], description=description[:4096], color=color)
    if guild.icon:
        embed.set_author(name=f"{guild.name[:220]}  •  WELCOME", icon_url=guild.icon.url)
    else:
        embed.set_author(name=f"{guild.name[:220]}  •  WELCOME")
    embed.set_thumbnail(url=member.display_avatar.url)

    if style != "minimal":
        embed.add_field(name="👤 Nový člen", value=f"**{discord.utils.escape_markdown(member.display_name[:100])}**", inline=True)
        count = guild.member_count
        embed.add_field(name="👥 Počet členů", value=f"**{count:,}**" if count is not None else "**—**", inline=True)
        if cfg.welcome_rules_channel_id and guild.get_channel(int(cfg.welcome_rules_channel_id)):
            embed.add_field(name="📜 Začni tady", value=f"<#{cfg.welcome_rules_channel_id}>", inline=False)
    elif cfg.welcome_rules_channel_id and guild.get_channel(int(cfg.welcome_rules_channel_id)):
        embed.add_field(name="📜 Pravidla", value=f"<#{cfg.welcome_rules_channel_id}>", inline=False)

    if cfg.welcome_banner:
        embed.set_image(url=cfg.welcome_banner)
    embed.set_footer(text="PUVOD  •  Užij si pobyt na serveru ✦")
    return embed


class ServerEvents(commands.Cog):
    """Event listenery; bez Slash příkazů, konfigurace v Setup cogu."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache: dict[int, tuple[float, EventConfig]] = {}

    def invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    async def _config(self, guild_id: int) -> EventConfig | None:
        cached = self._cache.get(guild_id)
        if cached and time.monotonic() - cached[0] < CONFIG_CACHE_SECONDS:
            return cached[1]
        try:
            row = await db.fetchrow(CONFIG_SQL, str(guild_id))
        except Exception:
            logger.exception("ServerEvents: nelze načíst konfiguraci serveru %s", guild_id)
            return None
        if row is None:
            config = EventConfig()
        else:
            data = dict(row)
            config = EventConfig(**{field: data.get(field) for field in EventConfig.__dataclass_fields__})
        self._cache[guild_id] = (time.monotonic(), config)
        return config

    @staticmethod
    def _channel(guild: discord.Guild, channel_id: int | None) -> discord.TextChannel | None:
        if channel_id is None:
            return None
        channel = guild.get_channel(int(channel_id))
        return channel if isinstance(channel, discord.TextChannel) else None

    @staticmethod
    async def _send(channel: discord.TextChannel | None, embed: discord.Embed,
                    *, ping_member: discord.Member | None = None) -> None:
        if channel is None:
            return
        allowed = (discord.AllowedMentions(users=[ping_member], roles=False, everyone=False)
                   if ping_member else discord.AllowedMentions.none())
        try:
            await channel.send(embed=embed, allowed_mentions=allowed)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("ServerEvents: odeslání do %s selhalo (zkontroluj práva)", channel.id)

    async def _log(self, guild: discord.Guild, embed: discord.Embed,
                   *, source_channel_id: int | None = None) -> None:
        cfg = await self._config(guild.id)
        if cfg is None or cfg.logs_channel_id is None:
            return
        if source_channel_id is not None and int(cfg.logs_channel_id) == int(source_channel_id):
            return  # Nezachycujeme vlastní log kanál; zabráníme zpětným smyčkám.
        await self._send(self._channel(guild, cfg.logs_channel_id), embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await self._config(member.guild.id)
        if cfg is None:
            return
        channel = self._channel(member.guild, cfg.welcome_channel_id)
        if channel is not None:
            await self._send(channel, make_welcome_embed(member, cfg), ping_member=member)

        embed = discord.Embed(title="📥 Člen se připojil", color=discord.Color.green(),
                              description=f"{_safe(member.display_name, 150)} (`{member.id}`)")
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await self._config(member.guild.id)
        if cfg is None:
            return
        channel = self._channel(member.guild, cfg.goodbye_channel_id)
        if channel is not None:
            text = render_template(cfg.goodbye_message or DEFAULT_GOODBYE,
                                   member=member, departing=True)
            embed = discord.Embed(title="🚪 Někdo nás opustil", description=text,
                                  color=discord.Color.orange())
            embed.set_thumbnail(url=member.display_avatar.url)
            await self._send(channel, embed)
        embed = discord.Embed(title="📤 Člen odešel", color=discord.Color.orange(),
                              description=f"{_safe(member.display_name, 150)} (`{member.id}`)")
        await self._log(member.guild, embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return  # Nikdy nečteme ani nelogujeme soukromé DM zprávy.
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        cfg = await self._config(guild.id)
        if cfg is None or not cfg.logs_channel_id or payload.channel_id == cfg.logs_channel_id:
            return
        message = payload.cached_message
        if message is not None and message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Smazaná zpráva", color=discord.Color.red())
        embed.add_field(name="Kanál", value=f"<#{payload.channel_id}>", inline=True)
        embed.add_field(name="ID zprávy", value=f"`{payload.message_id}`", inline=True)
        if message is not None:
            embed.add_field(name="Autor", value=f"{_safe(message.author.display_name, 140)} (`{message.author.id}`)", inline=False)
            embed.add_field(name="Obsah", value=_safe(message.content), inline=False)
            if message.attachments:
                embed.add_field(name="Přílohy", value=f"{len(message.attachments)} souborů (původní přílohy nemusí být dostupné)", inline=False)
        else:
            embed.add_field(name="Obsah", value="*Není v Discord cache — původní text nelze zjistit.*", inline=False)
        await self._log(guild, embed, source_channel_id=payload.channel_id)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id is None or "content" not in payload.data:
            return  # Embed-only úpravy nejsou editace textu.
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        cfg = await self._config(guild.id)
        if cfg is None or not cfg.logs_channel_id or payload.channel_id == cfg.logs_channel_id:
            return
        before = payload.cached_message
        after_content = payload.data.get("content", "")
        if before is not None:
            if before.author.bot or before.content == after_content:
                return
        embed = discord.Embed(title="✏️ Upravená zpráva", color=discord.Color.blue())
        embed.add_field(name="Kanál", value=f"<#{payload.channel_id}>", inline=True)
        embed.add_field(name="ID zprávy", value=f"`{payload.message_id}`", inline=True)
        if before is not None:
            embed.add_field(name="Autor", value=f"{_safe(before.author.display_name, 140)} (`{before.author.id}`)", inline=False)
            embed.add_field(name="Před úpravou", value=_safe(before.content), inline=False)
        else:
            embed.add_field(name="Před úpravou", value="*Původní obsah není v cache.*", inline=False)
        embed.add_field(name="Po úpravě", value=_safe(after_content), inline=False)
        embed.add_field(name="Odkaz", value=f"[Otevřít zprávu](https://discord.com/channels/{guild.id}/{payload.channel_id}/{payload.message_id})", inline=False)
        await self._log(guild, embed, source_channel_id=payload.channel_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        embed = discord.Embed(title="🧹 Hromadné mazání zpráv", color=discord.Color.orange(),
                              description=f"V <#{payload.channel_id}> bylo smazáno **{len(payload.message_ids)}** zpráv.")
        await self._log(guild, embed, source_channel_id=payload.channel_id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick:
            embed = discord.Embed(title="🪪 Změna přezdívky", color=discord.Color.blurple())
            embed.description = (f"Člen: {_safe(after.display_name, 200)} (`{after.id}`)\n"
                                 f"Předtím: {_safe(before.nick or before.name, 240)}\n"
                                 f"Nyní: {_safe(after.nick or after.name, 240)}")
            await self._log(after.guild, embed)
        before_ids, after_ids = {r.id for r in before.roles}, {r.id for r in after.roles}
        added, removed = after_ids - before_ids, before_ids - after_ids
        if added or removed:
            embed = discord.Embed(title="🎭 Změna rolí člena", color=discord.Color.blurple())
            embed.description = f"Člen: {_safe(after.display_name, 200)} (`{after.id}`)"
            if added:
                embed.add_field(name="Přidáno", value=" ".join(f"<@&{rid}>" for rid in list(sorted(added))[:20]), inline=False)
            if removed:
                embed.add_field(name="Odebráno", value=" ".join(f"<@&{rid}>" for rid in list(sorted(removed))[:20]), inline=False)
            await self._log(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(title="🔨 Ban uživatele", color=discord.Color.red(),
                              description=f"{_safe(user.name, 200)} (`{user.id}`)")
        await self._log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(title="🔓 Unban uživatele", color=discord.Color.green(),
                              description=f"{_safe(user.name, 200)} (`{user.id}`)")
        await self._log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(title="➕ Nový kanál", color=discord.Color.green(),
                              description=f"{_safe(channel.name, 180)} (`{channel.id}`)")
        await self._log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(title="➖ Smazaný kanál", color=discord.Color.orange(),
                              description=f"{_safe(channel.name, 180)} (`{channel.id}`)")
        await self._log(channel.guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerEvents(bot))