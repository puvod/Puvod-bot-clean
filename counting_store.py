"""Counting persistence. All gameplay writes commit together under a guild row lock."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

ZONE = ZoneInfo('Europe/Prague')
MAX_NUMBER = 2_000_000_000
ACHIEVEMENTS = ((1, 'První krok'), (10, 'Rozjezd'), (100, 'Stovkař'),
                (500, 'Vytrvalec'), (1000, 'Tisícovkář'), (5000, 'Legenda'),
                (10000, 'Counting GOAT'))


def today():
    return datetime.now(ZONE).date()


def parse_number(content):
    parts = content.strip().split(maxsplit=1)
    if not parts or not re.fullmatch(r'[0-9]{1,10}', parts[0]):
        return None
    number = int(parts[0])
    return number if number <= MAX_NUMBER else None


def rank(total):
    return next((name for target, name in reversed(ACHIEVEMENTS) if total >= target), 'Nováček')


async def init_counting(conn):
    # Additive migration: existing counting and Brawl balances stay intact.
    async with conn.transaction():
        await conn.execute('''
            SELECT pg_advisory_xact_lock(73190421);
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_record BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_allow_solo BOOLEAN NOT NULL DEFAULT TRUE;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_cooldown INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_paused BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_reactions BOOLEAN NOT NULL DEFAULT TRUE;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_tokens INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_gems INTEGER NOT NULL DEFAULT 80;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_reward_highwater BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_last_message BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS counting_summary_date DATE;
            ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS mistakes BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS earned_tokens BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS earned_gems BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS last_count_at TIMESTAMPTZ;
            CREATE TABLE IF NOT EXISTS counting_days (
                guild_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
                day DATE NOT NULL, counts BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, day, user_id));
            CREATE INDEX IF NOT EXISTS counting_lifetime_idx
                ON counting_leaderboard (guild_id, lifetime_counts DESC, user_id);
            CREATE TABLE IF NOT EXISTS counting_migrations (version INTEGER PRIMARY KEY);
        ''')
        inserted = await conn.fetchval('INSERT INTO counting_migrations VALUES (1) ON CONFLICT DO NOTHING RETURNING version')
        if inserted:
            await conn.execute('''UPDATE guild_settings SET
                counting_record = GREATEST(COALESCE(current_number,0), counting_record),
                counting_reward_highwater = GREATEST(COALESCE(current_number,0), counting_reward_highwater)''')
            # Legacy daily counts have no dates. Preserve them on the migration day only.
            await conn.execute('''INSERT INTO counting_days (guild_id,user_id,day,counts)
                SELECT guild_id,user_id,$1,daily_counts FROM counting_leaderboard WHERE daily_counts > 0
                ON CONFLICT DO NOTHING''', today())


class CountingStore:
    def __init__(self, pool):
        self.pool = pool

    async def settings(self, guild_id):
        async with self.pool.acquire() as c:
            return await c.fetchrow('SELECT * FROM guild_settings WHERE guild_id=$1', str(guild_id))

    async def configs(self):
        async with self.pool.acquire() as c:
            return await c.fetch('SELECT * FROM guild_settings WHERE counting_channel_id IS NOT NULL')

    async def configure(self, guild_id, **values):
        allowed = {'counting_channel_id', 'counting_time', 'current_number', 'reset_on_fail',
                   'counting_allow_solo', 'counting_cooldown', 'counting_paused',
                   'counting_reactions', 'counting_tokens', 'counting_gems'}
        if not values or not values.keys() <= allowed:
            raise ValueError('Invalid settings')
        async with self.pool.acquire() as c, c.transaction():
            g = str(guild_id)
            await c.execute('INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING', g)
            await c.fetchrow('SELECT guild_id FROM guild_settings WHERE guild_id=$1 FOR UPDATE', g)
            assignments = [f'{key}=${i}' for i, key in enumerate(values, 2)]
            if 'current_number' in values:
                n = values['current_number']
                if not 0 <= n < MAX_NUMBER:
                    raise ValueError('Number out of range')
                # Admin adjustments do not award stats, records, or currency.
                assignments += ['last_user_id=NULL', 'current_streak=0',
                                f'counting_reward_highwater=GREATEST(counting_reward_highwater,${list(values).index("current_number")+2}::INTEGER)']
            return await c.fetchrow(f'UPDATE guild_settings SET {", ".join(assignments)} WHERE guild_id=$1 RETURNING *', g, *values.values())

    async def submit(self, guild_id, channel_id, user_id, message_id, number, created_at):
        g, u = str(guild_id), str(user_id)
        day = created_at.astimezone(ZONE).date()
        async with self.pool.acquire() as c, c.transaction():
            s = await c.fetchrow('SELECT * FROM guild_settings WHERE guild_id=$1 FOR UPDATE', g)
            if not s or s['counting_channel_id'] != channel_id or s['counting_paused']:
                return {'status': 'ignored'}
            # Snowflake high-water mark prevents replay across restarts/duplicate instances.
            if message_id <= s['counting_last_message']:
                return {'status': 'ignored'}
            await c.execute('UPDATE guild_settings SET counting_last_message=$2 WHERE guild_id=$1', g, message_id)
            expected = (s['current_number'] or 0) + 1
            if not s['counting_allow_solo'] and s['last_user_id'] == u:
                return {'status': 'solo', 'expected': expected}
            last = None
            if s['counting_cooldown']:
                last = await c.fetchval('SELECT last_count_at FROM counting_leaderboard WHERE guild_id=$1 AND user_id=$2', g, u)
            if last and (created_at-last).total_seconds() < s['counting_cooldown']:
                return {'status': 'cooldown', 'expected': expected}
            if number != expected:
                await c.execute('''INSERT INTO counting_leaderboard (guild_id,user_id,mistakes) VALUES ($1,$2,1)
                    ON CONFLICT (guild_id,user_id) DO UPDATE SET mistakes=counting_leaderboard.mistakes+1''', g,u)
                if s['reset_on_fail']:
                    await c.execute('UPDATE guild_settings SET current_number=0,last_user_id=NULL,current_streak=0 WHERE guild_id=$1',g)
                return {'status': 'wrong', 'expected': expected, 'reset': bool(s['reset_on_fail'])}
            tokens = gems = 0
            # Each server milestone pays once, even after a reset or manual rewind.
            if number > s['counting_reward_highwater']:
                if number % 1000 == 0:
                    gems = s['counting_gems']
                elif number % 100 == 0:
                    tokens = s['counting_tokens']
            await c.execute('''UPDATE guild_settings SET current_number=$2::INTEGER,last_user_id=$3,
                current_streak=COALESCE(current_streak,0)+1,
                counting_record=GREATEST(counting_record,$2::INTEGER),
                counting_reward_highwater=GREATEST(counting_reward_highwater,$2::INTEGER) WHERE guild_id=$1''',g,number,u)
            total = await c.fetchval('''INSERT INTO counting_leaderboard
                (guild_id,user_id,daily_counts,lifetime_counts,earned_tokens,earned_gems,last_count_at)
                VALUES ($1,$2,1,1,$3,$4,$5) ON CONFLICT (guild_id,user_id) DO UPDATE SET
                lifetime_counts=counting_leaderboard.lifetime_counts+1,
                earned_tokens=counting_leaderboard.earned_tokens+$3,
                earned_gems=counting_leaderboard.earned_gems+$4,last_count_at=$5
                RETURNING lifetime_counts''',g,u,tokens,gems,created_at)
            await c.execute('''INSERT INTO counting_days VALUES ($1,$2,$3,1)
                ON CONFLICT (guild_id,day,user_id) DO UPDATE SET counts=counting_days.counts+1''',g,u,day)
            if tokens or gems:
                await c.execute('''INSERT INTO user_brawl (guild_id,user_id,tokens,gems) VALUES ($1,$2,$3,$4)
                    ON CONFLICT (guild_id,user_id) DO UPDATE SET
                    tokens=user_brawl.tokens+$3,gems=user_brawl.gems+$4''',g,u,tokens,gems)
            return {'status':'ok','number':number,'tokens':tokens,'gems':gems,'total':total,
                    'record':number>s['counting_record'],'reactions':s['counting_reactions']}

    async def leaderboard(self, guild_id, period='daily', page=0, day=None):
        day = day or today()
        async with self.pool.acquire() as c:
            if period == 'lifetime':
                return await c.fetch('''SELECT user_id,lifetime_counts AS score FROM counting_leaderboard
                    WHERE guild_id=$1 AND lifetime_counts>0 ORDER BY score DESC,user_id LIMIT 11 OFFSET $2''',str(guild_id),page*10)
            start = day-timedelta(days=day.weekday()) if period == 'weekly' else day
            return await c.fetch('''SELECT user_id,SUM(counts)::BIGINT AS score FROM counting_days
                WHERE guild_id=$1 AND day BETWEEN $2 AND $3 GROUP BY user_id
                HAVING SUM(counts)>0 ORDER BY score DESC,user_id LIMIT 11 OFFSET $4''',str(guild_id),start,day,page*10)

    async def profile(self, guild_id, user_id):
        async with self.pool.acquire() as c:
            row = await c.fetchrow('''SELECT l.*,
                (SELECT COUNT(*)+1 FROM counting_leaderboard x WHERE x.guild_id=l.guild_id
                 AND x.lifetime_counts>l.lifetime_counts) AS position,
                COALESCE((SELECT counts FROM counting_days d WHERE d.guild_id=l.guild_id
                 AND d.user_id=l.user_id AND d.day=$3),0) AS today
                FROM counting_leaderboard l WHERE guild_id=$1 AND user_id=$2''',str(guild_id),str(user_id),today())
            return dict(row) if row else dict(lifetime_counts=0,mistakes=0,earned_tokens=0,earned_gems=0,position=0,today=0)

    async def claim_summary(self, guild_id, day):
        async with self.pool.acquire() as c:
            return await c.fetchval('''UPDATE guild_settings SET counting_summary_date=$2
                WHERE guild_id=$1 AND (counting_summary_date IS NULL OR counting_summary_date<$2)
                RETURNING guild_id''',str(guild_id),day)

    async def release_summary(self, guild_id, day):
        async with self.pool.acquire() as c:
            await c.execute('UPDATE guild_settings SET counting_summary_date=NULL WHERE guild_id=$1 AND counting_summary_date=$2',str(guild_id),day)

    async def cleanup(self):
        async with self.pool.acquire() as c:
            await c.execute('DELETE FROM counting_days WHERE day<$1', today()-timedelta(days=35))
