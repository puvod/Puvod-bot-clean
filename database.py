import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise ValueError("❌ Chybí proměnná prostředí DATABASE_URL!")
            
            self.pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=1,
                max_size=10
            )
            await self.init_db()

    async def init_db(self):
        async with self.pool.acquire() as conn:
            # 1. Nastavení guildy
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id VARCHAR(50) PRIMARY KEY,
                    welcome_channel_id BIGINT,
                    logs_channel_id BIGINT,
                    counting_channel_id BIGINT,
                    counting_time TEXT,
                    current_number INTEGER DEFAULT 0,
                    last_user_id VARCHAR(50),
                    current_streak INTEGER DEFAULT 0,
                    reset_on_fail INTEGER DEFAULT 1
                );
            ''')
            
            # 2. Leaderboard – přidány sloupce pro DENNÍ i CELKOVÝ počet
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS counting_leaderboard (
                    guild_id VARCHAR(50),
                    user_id VARCHAR(50),
                    daily_counts INTEGER DEFAULT 0,
                    lifetime_counts INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
            ''')

            # 3. Role
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS selectable_roles (
                    guild_id VARCHAR(50),
                    role_id VARCHAR(50),
                    PRIMARY KEY (guild_id, role_id)
                );
            ''')

            # Automatické opravení starých tabulek
            await conn.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS reset_on_fail INTEGER DEFAULT 1;")
            await conn.execute("ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS daily_counts INTEGER DEFAULT 0;")
            await conn.execute("ALTER TABLE counting_leaderboard ADD COLUMN IF NOT EXISTS lifetime_counts INTEGER DEFAULT 0;")
            print("🗄️ PostgreSQL Databáze byla úspěšně inicializována.")

    async def execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

db = Database()

# --- POMOCNÉ FUNKCE ---

async def get_setting(guild_id: int, column_name: str):
    allowed = {"welcome_channel_id", "logs_channel_id", "counting_channel_id", "counting_time", "current_number", "last_user_id", "current_streak", "reset_on_fail"}
    if column_name not in allowed:
        raise ValueError(f"Nepovolený název sloupce: {column_name}")
    row = await db.fetchrow(f"SELECT {column_name} FROM guild_settings WHERE guild_id = $1", str(guild_id))
    return row[0] if row else None

async def update_setting(g_id, column_name, value):
    allowed = {"welcome_channel_id", "logs_channel_id", "counting_channel_id", "counting_time", "current_number", "last_user_id", "current_streak", "reset_on_fail"}
    if column_name not in allowed:
        raise ValueError(f"Nepovolený název sloupce: {column_name}")

    await db.execute("INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING", str(g_id))
    await db.execute(f"UPDATE guild_settings SET {column_name} = $1 WHERE guild_id = $2", value, str(g_id))

async def set_counting_number(guild_id: int, number: int):
    g_id = str(guild_id)
    await db.execute("INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING", g_id)
    await db.execute("UPDATE guild_settings SET current_number = $1, last_user_id = NULL WHERE guild_id = $2", number, g_id)

async def increment_user_count(guild_id: int, user_id: int):
    g_id, u_id = str(guild_id), str(user_id)
    await db.execute('''
        INSERT INTO counting_leaderboard (guild_id, user_id, daily_counts, lifetime_counts)
        VALUES ($1, $2, 1, 1)
        ON CONFLICT (guild_id, user_id)
        DO UPDATE SET 
            daily_counts = counting_leaderboard.daily_counts + 1,
            lifetime_counts = counting_leaderboard.lifetime_counts + 1
    ''', g_id, u_id)

async def get_top_users_daily(guild_id: int, limit=10):
    rows = await db.fetch("SELECT user_id, daily_counts FROM counting_leaderboard WHERE guild_id = $1 AND daily_counts > 0 ORDER BY daily_counts DESC LIMIT $2", str(guild_id), limit)
    return rows

async def get_top_users_lifetime(guild_id: int, limit=10):
    rows = await db.fetch("SELECT user_id, lifetime_counts FROM counting_leaderboard WHERE guild_id = $1 ORDER BY lifetime_counts DESC LIMIT $2", str(guild_id), limit)
    return rows

async def reset_daily_stats(guild_id: int):
    await db.execute("UPDATE counting_leaderboard SET daily_counts = 0 WHERE guild_id = $1", str(guild_id))

async def get_all_guilds_with_counting():
    rows = await db.fetch("SELECT guild_id, counting_channel_id, counting_time FROM guild_settings WHERE counting_channel_id IS NOT NULL AND counting_time IS NOT NULL")
    return rows