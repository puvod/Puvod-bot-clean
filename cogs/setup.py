from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from database import db
from cogs.server_events import EventConfig, make_welcome_embed

logger = logging.getLogger(__name__)

# Sloupce vybírá pouze náš kód, nikdy volný vstup uživatele.
CHANNEL_COLUMNS = {
    "logs": "logs_channel_id",
    "welcome": "welcome_channel_id",
    "goodbye": "goodbye_channel_id",
    "discussion": "discussion_channel_id",
}
MESSAGE_COLUMNS = {
    "welcome": "welcome_message",
    "goodbye": "goodbye_message",
}
CHANNEL_TITLES = {
    "logs": "📜 Serverové logy",
    "welcome": "👋 Uvítání nových členů",
    "goodbye": "🚪 Loučení členů",
    "discussion": "💬 Diskuzní témata",
}

# Schéma se aktualizuje při načtení cogu. Žádné ruční mazání nebo migrace dat.
SCHEMA_SQL = (
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS goodbye_channel_id BIGINT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS discussion_channel_id BIGINT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_message TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS goodbye_message TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS discussion_time TEXT DEFAULT '18:00'",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS discussion_last_post_date DATE",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_title TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_emoji TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_color TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_banner TEXT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_rules_channel_id BIGINT",
    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_style TEXT",
)

CONFIG_QUERY = """
    SELECT logs_channel_id, welcome_channel_id, goodbye_channel_id,
           discussion_channel_id, welcome_message, goodbye_message, discussion_time,
           welcome_title, welcome_emoji, welcome_color, welcome_banner,
           welcome_rules_channel_id, welcome_style,
           counting_channel_id, counting_time, current_number,
           current_streak, last_user_id, reset_on_fail
      FROM guild_settings
     WHERE guild_id = $1
"""


def _channel_value(value: int | None) -> str:
    return f"<#{value}>" if value else "*Nenastaveno*"


def _number(value: int | None) -> str:
    return f"{int(value or 0):,}".replace(",", " ")


WELCOME_CONFIG_QUERY = """
    SELECT welcome_channel_id, welcome_title, welcome_emoji, welcome_color,
           welcome_message, welcome_banner, welcome_rules_channel_id, welcome_style
      FROM guild_settings WHERE guild_id = $1
"""
CUSTOM_EMOJI = re.compile(r"<a?:([a-zA-Z0-9_]{2,32}):(\d{15,22})>\Z")
COLOR_HEX = re.compile(r"#?[0-9a-fA-F]{6}\Z")


def parse_server_emoji(guild: discord.Guild, input_text: str) -> str:
    """Podporuje <:name:id>, <a:name:id>, :name:, name a Unicode emoji.

    Vlastní Discord emoji akceptujeme pouze ze stejného serveru a pouze dostupné.
    """
    value = input_text.strip()
    if not value:
        raise ValueError("Prázdné emoji. Pro výchozí emoji použij `/setup_vitej_reset`.")
    match = CUSTOM_EMOJI.fullmatch(value)
    guild_emojis = list(guild.emojis)
    if match:
        emoji = discord.utils.get(guild_emojis, id=int(match.group(2)))
        if emoji is None:
            raise ValueError("Tohle emoji není na tomto serveru. Použij emoji z vlastního serveru.")
        if not emoji.available:
            raise ValueError("Tohle emoji je momentálně nedostupné.")
        return str(emoji)
    clean_name = value[1:-1] if value.startswith(":") and value.endswith(":") else value
    for emoji in guild_emojis:
        if emoji.name.casefold() == clean_name.casefold():
            if not emoji.available:
                raise ValueError("Tohle emoji je momentálně nedostupné.")
            return str(emoji)
    # Unicode emoji: přijímáme malé skupiny znaků bez ASCII písmen a pingů.
    if 1 <= len(value) <= 20 and all(ord(c) > 127 for c in value) and not any(c in value for c in ("<", ">", "@")):
        return value
    raise ValueError("Použij `:nazev_emoji:`, vložené serverové emoji `<:nazev:ID>` nebo běžné emoji 👋.")


def validate_banner(url: str) -> str:
    value = url.strip()
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or len(value) > 600 or any(c.isspace() for c in value)):
            raise ValueError
    except ValueError:
        raise ValueError("Banner musí být přímá HTTPS adresa obrázku, třeba z Discord CDN.") from None
    return value


class Setup(commands.Cog):
    """Administrátorská konfigurace pro welcome/goodbye/logy/diskuze."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # main.py volá db.connect() před načítáním cogů.
        for statement in SCHEMA_SQL:
            await db.execute(statement)
        logger.info("Setup: DB schéma pro welcome/goodbye/logy je připraveno")

    @staticmethod
    async def _defer(interaction: discord.Interaction) -> bool:
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            return True
        except discord.NotFound as exc:
            if exc.code == 10062:
                logger.warning("Setup: interakce %s vypršela", interaction.id)
                return False
            raise

    @staticmethod
    async def _reply(interaction: discord.Interaction, *, content: str | None = None,
                     embed: discord.Embed | None = None) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content=content, embed=embed, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.send_message(content=content, embed=embed, ephemeral=True,
                                                        allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            logger.warning("Setup: nepodařilo se odpovědět na interakci %s: %s", interaction.id, exc)

    def _invalidate_cache(self, guild_id: int) -> None:
        events = self.bot.get_cog("ServerEvents")
        if events is not None:
            events.invalidate(guild_id)

    async def _set_channel(self, interaction: discord.Interaction, key: str,
                           channel: discord.TextChannel | None) -> None:
        if not await self._defer(interaction):
            return
        guild = interaction.guild
        if guild is None or key not in CHANNEL_COLUMNS:
            await self._reply(interaction, content="❌ Neplatné nastavení serveru.")
            return
        if channel is not None:
            if channel.guild.id != guild.id:
                await self._reply(interaction, content="❌ Vyber kanál na tomto serveru.")
                return
            member = guild.me
            if member is not None:
                perms = channel.permissions_for(member)
                if not (perms.view_channel and perms.send_messages and perms.embed_links):
                    await self._reply(
                        interaction,
                        content=f"❌ V {channel.mention} potřebuji **Zobrazit kanál**, **Posílat zprávy** a **Vkládat odkazy (embedy)**.",
                    )
                    return
        try:
            column = CHANNEL_COLUMNS[key]
            await db.execute(
                f"INSERT INTO guild_settings (guild_id, {column}) VALUES ($1, $2) "
                f"ON CONFLICT (guild_id) DO UPDATE SET {column} = EXCLUDED.{column}",
                str(guild.id), channel.id if channel else None,
            )
            self._invalidate_cache(guild.id)
        except Exception:
            logger.exception("Setup: nelze uložit %s pro server %s", key, guild.id)
            await self._reply(interaction, content="❌ Chyba ukládání do Supabase. Podrobnosti jsou v logu Renderu.")
            return

        target = f"{channel.mention}" if channel else "*vypnuto*"
        await self._reply(interaction, content=f"✅ **{CHANNEL_TITLES[key]}:** {target}\n💾 Uloženo v Supabase.")

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_logs", description="[Admin] Nastaví kanál pro logování událostí serveru.")
    async def setup_logs(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self._set_channel(interaction, "logs", channel)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_vitej", description="[Admin] Nastaví CLEAN welcome embed, emoji a uvítací kanál.")
    @app_commands.describe(
        channel="Kanál, kam bude bot posílat uvítání",
        emoji="Serverové emoji (:wave:, <:wave:ID>) nebo běžné emoji 👋",
        nadpis="Vlastní nadpis (může obsahovat {server} nebo {username})",
        zprava="Text uvítání: {user}, {username}, {server}, {count}",
        barva="Barva embedu v HEX, např. #8B5CF6",
        banner="Přímé HTTPS URL obrázku na šířku (volitelné)",
        pravidla="Kanál s pravidly, na který welcome odkáže",
        styl="Clean, minimalistický nebo premium design",
    )
    @app_commands.choices(styl=[
        app_commands.Choice(name="✨ Clean — doporučeno", value="clean"),
        app_commands.Choice(name="🤍 Minimal", value="minimal"),
        app_commands.Choice(name="💎 Premium", value="premium"),
    ])
    async def setup_vitej(
        self, interaction: discord.Interaction,
        channel: discord.TextChannel,
        emoji: str | None = None,
        nadpis: str | None = None,
        zprava: str | None = None,
        barva: str | None = None,
        banner: str | None = None,
        pravidla: discord.TextChannel | None = None,
        styl: str | None = None,
    ) -> None:
        if not await self._defer(interaction):
            return
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await self._reply(interaction, content="❌ Kanál musí být na tomto serveru.")
            return
        member = guild.me
        if member is not None:
            permissions = channel.permissions_for(member)
            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                await self._reply(interaction, content="❌ Bot potřebuje v uvítacím kanálu práva číst, psát a vkládat embedy.")
                return
        if pravidla is not None and pravidla.guild.id != guild.id:
            await self._reply(interaction, content="❌ Pravidla musí být na stejném serveru.")
            return
        if nadpis is not None and not (1 <= len(nadpis.strip()) <= 120):
            await self._reply(interaction, content="❌ Nadpis musí mít 1 až 120 znaků.")
            return
        if zprava is not None and not (1 <= len(zprava.strip()) <= 1000):
            await self._reply(interaction, content="❌ Zpráva musí mít 1 až 1000 znaků.")
            return
        if styl is not None and styl not in ("clean", "minimal", "premium"):
            await self._reply(interaction, content="❌ Neplatný styl.")
            return
        try:
            resolved_emoji = parse_server_emoji(guild, emoji) if emoji is not None else None
            if barva is not None and not COLOR_HEX.fullmatch(barva.strip()):
                raise ValueError("Barva musí být šestimístný HEX kód, například `#8B5CF6`.")
            resolved_color = f"#{barva.strip().lstrip('#').upper()}" if barva is not None else None
            resolved_banner = validate_banner(banner) if banner is not None else None
        except ValueError as exc:
            await self._reply(interaction, content=f"❌ {exc}")
            return

        # Aktualizujeme jen vyplněná pole: opakované /setup_vitej nevymaže design.
        changes: dict[str, object] = {"welcome_channel_id": channel.id}
        optional = {
            "welcome_emoji": resolved_emoji,
            "welcome_title": nadpis.strip() if nadpis is not None else None,
            "welcome_message": zprava.strip() if zprava is not None else None,
            "welcome_color": resolved_color,
            "welcome_banner": resolved_banner,
            "welcome_rules_channel_id": pravidla.id if pravidla is not None else None,
            "welcome_style": styl,
        }
        changes.update({key: value for key, value in optional.items() if value is not None})
        # Klíče změn vybírá výhradně zdrojový kód, nikdy uživatel.
        columns = list(changes)
        placeholders = [f"${n}" for n in range(2, len(columns) + 2)]
        assignments = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns)
        sql = (f"INSERT INTO guild_settings (guild_id, {', '.join(columns)}) "
               f"VALUES ($1, {', '.join(placeholders)}) "
               f"ON CONFLICT (guild_id) DO UPDATE SET {assignments}")
        try:
            await db.execute(sql, str(guild.id), *changes.values())
            self._invalidate_cache(guild.id)
            row = await db.fetchrow(WELCOME_CONFIG_QUERY, str(guild.id))
        except Exception:
            logger.exception("Setup: chyba ukládání welcome pro guild %s", guild.id)
            await self._reply(interaction, content="❌ Ukládání do Supabase selhalo. Zkontroluj Render logy.")
            return
        cfg = EventConfig(**{k: (dict(row).get(k) if row else None) for k in EventConfig.__dataclass_fields__})
        admin_member = interaction.user
        if not isinstance(admin_member, discord.Member):
            admin_member = guild.get_member(interaction.user.id)
        if admin_member is not None:
            preview = make_welcome_embed(admin_member, cfg)
            await self._reply(interaction, content=f"✅ **Welcome uložen do Supabase!** Kanál: {channel.mention}\n🔎 *Náhled (vidíš pouze ty):*", embed=preview)
        else:
            await self._reply(interaction, content=f"✅ Welcome uložen pro {channel.mention}. Náhled zkus přes `/setup_test typ:welcome`.")

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_vitej_reset", description="[Admin] Obnoví výchozí clean vzhled uvítání (kanál zůstane).")
    async def setup_vitej_reset(self, interaction: discord.Interaction) -> None:
        if not await self._defer(interaction):
            return
        try:
            await db.execute("""
                UPDATE guild_settings
                   SET welcome_emoji = NULL, welcome_title = NULL, welcome_message = NULL,
                       welcome_color = NULL, welcome_banner = NULL,
                       welcome_rules_channel_id = NULL, welcome_style = NULL
                 WHERE guild_id = $1
            """, str(interaction.guild_id))
            self._invalidate_cache(interaction.guild_id)
        except Exception:
            logger.exception("Setup: reset welcome selhal")
            await self._reply(interaction, content="❌ Reset vzhledu v Supabase selhal.")
            return
        await self._reply(interaction, content="✅ Welcome vzhled resetován na **Clean**. Uvítací kanál zůstal zachovaný.")

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_goodbye", description="[Admin] Nastaví kanál pro loučení s členy.")
    async def setup_goodbye(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self._set_channel(interaction, "goodbye", channel)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_diskuze", description="[Admin] Nastaví samostatný kanál pro diskuzní témata.")
    async def setup_diskuze(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self._set_channel(interaction, "discussion", channel)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_clear", description="[Admin] Vypne nastavený kanál vybrané funkce.")
    @app_commands.choices(typ=[
        app_commands.Choice(name="📜 Logy", value="logs"),
        app_commands.Choice(name="👋 Vítání", value="welcome"),
        app_commands.Choice(name="🚪 Loučení", value="goodbye"),
        app_commands.Choice(name="💬 Diskuze", value="discussion"),
    ])
    async def setup_clear(self, interaction: discord.Interaction, typ: str) -> None:
        await self._set_channel(interaction, typ, None)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_diskuze_cas", description="[Admin] Kdy se zveřejní denní diskuzní téma (český čas).")
    @app_commands.describe(cas="Čas ve formátu HH:MM (např. 18:30)")
    async def setup_diskuze_cas(self, interaction: discord.Interaction, cas: str) -> None:
        import re
        if not await self._defer(interaction):
            return
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cas):
            await self._reply(interaction, content="❌ Čas zadej ve formátu `HH:MM`, například `18:30`.")
            return
        try:
            await db.execute(
                "INSERT INTO guild_settings (guild_id, discussion_time) VALUES ($1, $2) "
                "ON CONFLICT (guild_id) DO UPDATE SET discussion_time = EXCLUDED.discussion_time",
                str(interaction.guild_id), cas,
            )
        except Exception:
            logger.exception("Setup: nelze uložit čas diskuze")
            await self._reply(interaction, content="❌ Chyba ukládání do Supabase.")
            return
        await self._reply(interaction, content=f"✅ Denní diskuzní téma se bude posílat v **{cas}** (Europe/Prague).")

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_zprava", description="[Admin] Vlastní zpráva při příchodu/odchodu; bez textu obnoví výchozí.")
    @app_commands.describe(
        typ="Vyber uvítání nebo loučení",
        zprava="Text; používej {user}, {username}, {server}, {count}. Nech prázdné pro reset.",
    )
    @app_commands.choices(typ=[
        app_commands.Choice(name="👋 Uvítání", value="welcome"),
        app_commands.Choice(name="🚪 Loučení", value="goodbye"),
    ])
    async def setup_zprava(self, interaction: discord.Interaction, typ: str,
                           zprava: str | None = None) -> None:
        if not await self._defer(interaction):
            return
        if interaction.guild is None or typ not in MESSAGE_COLUMNS:
            await self._reply(interaction, content="❌ Neplatný typ zprávy.")
            return
        if zprava and len(zprava) > 1000:
            await self._reply(interaction, content="❌ Text může mít maximálně 1 000 znaků.")
            return
        text = zprava.strip() if zprava else None
        if text == "":
            text = None
        column = MESSAGE_COLUMNS[typ]
        try:
            await db.execute(
                f"INSERT INTO guild_settings (guild_id, {column}) VALUES ($1, $2) "
                f"ON CONFLICT (guild_id) DO UPDATE SET {column} = EXCLUDED.{column}",
                str(interaction.guild_id), text,
            )
            self._invalidate_cache(interaction.guild_id)
        except Exception:
            logger.exception("Setup: chyba ukládání šablony pro server %s", interaction.guild_id)
            await self._reply(interaction, content="❌ Nepodařilo se uložit text do Supabase.")
            return
        await self._reply(
            interaction,
            content="✅ Výchozí zpráva obnovena." if text is None else
                    f"✅ **{CHANNEL_TITLES[typ]}** — nový text uložen.\n```{text[:900]}```",
        )

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_test", description="[Admin] Odešle testovací embed do nastaveného kanálu.")
    @app_commands.choices(typ=[
        app_commands.Choice(name="📜 Logy", value="logs"),
        app_commands.Choice(name="👋 Vítání", value="welcome"),
        app_commands.Choice(name="🚪 Loučení", value="goodbye"),
        app_commands.Choice(name="💬 Diskuze", value="discussion"),
    ])
    async def setup_test(self, interaction: discord.Interaction, typ: str) -> None:
        if not await self._defer(interaction):
            return
        if interaction.guild is None or typ not in CHANNEL_COLUMNS:
            await self._reply(interaction, content="❌ Neplatný typ.")
            return
        try:
            column = CHANNEL_COLUMNS[typ]
            row = await db.fetchrow(f"SELECT {column} FROM guild_settings WHERE guild_id = $1", str(interaction.guild_id))
            channel_id = row[column] if row else None
            channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
            if not isinstance(channel, discord.TextChannel):
                await self._reply(interaction, content="❌ Kanál není nastavený nebo už neexistuje.")
                return
            if typ == "welcome":
                # Stejný vizuál jako při reálném příchodu uživatele.
                cfg_row = await db.fetchrow(WELCOME_CONFIG_QUERY, str(interaction.guild_id))
                data = dict(cfg_row) if cfg_row else {}
                cfg = EventConfig(**{key: data.get(key) for key in EventConfig.__dataclass_fields__})
                fake_member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
                if fake_member is None:
                    await self._reply(interaction, content="❌ Nepodařilo se načíst profil pro náhled.")
                    return
                embed = make_welcome_embed(fake_member, cfg)
            else:
                embed = discord.Embed(
                    title="🧪 Test konfigurace Puvod Bota",
                    description=f"✅ **{CHANNEL_TITLES[typ]}** jsou funkční.\nToto je pouze testovací zpráva.",
                    color=discord.Color.green(),
                )
            # Náhled nesmí nikoho pingnout ani při použití {user}.
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await self._reply(interaction, content=f"✅ Testovací zpráva odeslána do {channel.mention}.")
        except (discord.HTTPException, discord.Forbidden):
            logger.exception("Setup: chyba při odesílání testu")
            await self._reply(interaction, content="❌ Nemohu odeslat zprávu. Zkontroluj oprávnění v kanálu.")
        except Exception:
            logger.exception("Setup: chyba při testování Supabase")
            await self._reply(interaction, content="❌ Chyba načítání nastavení ze Supabase.")

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="show_config", description="[Admin] Zobrazí úplné nastavení serveru v Supabase.")
    async def show_config(self, interaction: discord.Interaction) -> None:
        if not await self._defer(interaction):
            return
        guild = interaction.guild
        if guild is None:
            await self._reply(interaction, content="❌ Příkaz funguje pouze na serveru.")
            return
        try:
            row = await db.fetchrow(CONFIG_QUERY, str(guild.id))
        except Exception:
            logger.exception("Setup: chyba čtení konfigurace pro %s", guild.id)
            await self._reply(interaction, content="❌ Nepodařilo se načíst Supabase nastavení.")
            return
        data = dict(row) if row else {}
        embed = discord.Embed(
            title="⚙️ Nastavení Puvod Bota",
            description=discord.utils.escape_markdown(guild.name) + "\nKonfigurace uložená v PostgreSQL / Supabase.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="📨 Serverové kanály", inline=False, value=(
            f"📜 **Logy:** {_channel_value(data.get('logs_channel_id'))}\n"
            f"👋 **Vítání:** {_channel_value(data.get('welcome_channel_id'))}\n"
            f"🚪 **Loučení:** {_channel_value(data.get('goodbye_channel_id'))}\n"
            f"💬 **Diskuze:** {_channel_value(data.get('discussion_channel_id'))}\n"
            f"🔢 **Counting:** {_channel_value(data.get('counting_channel_id'))}"
        ))
        if data.get("counting_channel_id"):
            reset = data.get("reset_on_fail")
            embed.add_field(name="🔢 Counting", inline=False, value=(
                f"Aktuální číslo: **{_number(data.get('current_number'))}**\n"
                f"Série: **{_number(data.get('current_streak'))}**\n"
                f"Reset po chybě: **{'Zapnuto' if reset is None or reset == 1 else 'Vypnuto'}**\n"
                f"Denní žebříček: **{data.get('counting_time') or 'Nenastaveno'}** (Europe/Prague)"
            ))
        embed.add_field(name="💬 Diskuze", inline=False, value=(
            f"Čas automatického tématu: **{data.get('discussion_time') or '18:00'}** (Europe/Prague)"
        ))
        embed.add_field(name="✏️ Vlastní zprávy", inline=False, value=(
            f"Uvítání: {'Vlastní' if data.get('welcome_message') else 'Výchozí'}\n"
            f"Styl: **{data.get('welcome_style') or 'clean'}**, "
            f"barva: **{data.get('welcome_color') or '#8B5CF6'}**\n"
            f"Emoji: {data.get('welcome_emoji') or '✨'}  •  "
            f"Banner: {'Nastavený' if data.get('welcome_banner') else 'Bez banneru'}\n"
            f"Pravidla: {_channel_value(data.get('welcome_rules_channel_id'))}\n"
            f"Loučení: {'Vlastní' if data.get('goodbye_message') else 'Výchozí'}"
        ))
        embed.add_field(name="🛠️ Příkazy", inline=False, value=(
            "`/setup_logs` `/setup_vitej` `/setup_goodbye` `/setup_diskuze`\n"
            "`/setup_zprava` `/setup_clear` `/setup_diskuze_cas`\n"
            "`/setup_vitej_reset` `/setup_test` `/show_config`"
        ))
        embed.set_footer(text=f"Server ID: {guild.id} • Viditelné pouze administrátorům")
        await self._reply(interaction, embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction,
                                    error: app_commands.AppCommandError) -> None:
        source = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(source, app_commands.MissingPermissions):
            await self._reply(interaction, content="⛔ Potřebuješ administrátorská oprávnění.")
        elif isinstance(source, app_commands.NoPrivateMessage):
            await self._reply(interaction, content="❌ Pouze pro servery.")
        else:
            logger.error("Setup: chyba /%s", getattr(interaction.command, "name", "?"),
                         exc_info=(type(source), source, source.__traceback__))
            await self._reply(interaction, content="❌ Příkaz se nepodařilo dokončit, zkontroluj logy Renderu.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Setup(bot))
