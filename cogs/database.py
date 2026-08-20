import os
import asyncpg

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=os.getenv("DATABASE_URL"),
                min_size=1,
                max_size=10
            )
            await self.init_tables()
            await self.seed_initial_data()  # <-- PO PRVNÍM SPUŠTĚNÍ TENTO ŘÁDEK ZAKOMENTUJ (#)

    async def init_tables(self):
        async with self.pool.acquire() as conn:
            # 1. Vytvoření tabulek
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id VARCHAR(50) PRIMARY KEY,
                    welcome_channel_id VARCHAR(50),
                    logs_channel_id VARCHAR(50),
                    counting_channel_id VARCHAR(50),
                    current_number INT DEFAULT 0,
                    last_user_id VARCHAR(50),
                    reset_on_fail INT DEFAULT 1,
                    counting_time VARCHAR(10),
                    current_streak INT DEFAULT 0
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS counting_leaderboard (
                    guild_id VARCHAR(50),
                    user_id VARCHAR(50),
                    daily_counts INT DEFAULT 0,
                    total_counts INT DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS selectable_roles (
                    guild_id VARCHAR(50),
                    role_id VARCHAR(50)
                );
            """)

    async def seed_initial_data(self):
        """Jednorázové nahrání zálohovaných dat. Po prvním spuštění bota zavolání této metody vypni!"""
        async with self.pool.acquire() as conn:
            # Obnova selectable_roles
            roles = [
                '1463231879414157446', '1463232272164585474', '1463232392281198776',
                '1463232501949399164', '1463232574313988168', '1463869188543217789',
                '1463870812032340072', '1463871025065365681', '1463871191910453350',
                '1464661112565006459', '1468012122356191337', '1468012330041348362', '1475934465623588904'
            ]
            for r_id in roles:
                await conn.execute("""
                    INSERT INTO selectable_roles (guild_id, role_id) 
                    VALUES ('1463229014901657850', $1)
                """, r_id)

            # Obnova guild_settings (OPRAVENO: counting_channel_id předáno jako string v uvozovkách)
            await conn.execute("""
                INSERT INTO guild_settings (guild_id, counting_channel_id, counting_time, current_number, current_streak, reset_on_fail) 
                VALUES ('1463229014901657850', '1464000345561628743', '15:00', 20057, 11257, 0)
                ON CONFLICT (guild_id) DO UPDATE SET 
                    counting_channel_id = EXCLUDED.counting_channel_id,
                    counting_time = EXCLUDED.counting_time,
                    current_number = EXCLUDED.current_number,
                    current_streak = EXCLUDED.current_streak,
                    reset_on_fail = EXCLUDED.reset_on_fail;
            """)

            # Obnova counting_leaderboard
            top_data = [
                ('1148172177527554161', 2), ('1333739505357819948', 3), ('1342464783349186623', 1006),
                ('1348208550266146846', 1007), ('1374631878799130657', 68), ('1426919153071034379', 122),
                ('1441064615940456549', 63), ('1451552250974699560', 1062), ('1452780776369295606', 3203),
                ('1454180637819932753', 10), ('1468698720949239908', 4160), ('1479510195251056662', 118),
                ('1481744055120433374', 50), ('1482442900636958822', 46), ('1494993577724481538', 105),
                ('1519336351403741294', 15), ('1519393164593725701', 10), ('1524071634607276162', 32),
                ('1529176118471426272', 113), ('1534951757430521939', 20), ('704630491290009600', 1),
                ('722739479034593280', 32), ('921011084779995166', 9)
            ]
            for u_id, count in top_data:
                await conn.execute("""
                    INSERT INTO counting_leaderboard (guild_id, user_id, total_counts) 
                    VALUES ('1463229014901657850', $1, $2)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET total_counts = EXCLUDED.total_counts;
                """, u_id, count)

    async def execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def close(self):
        if self.pool:
            await self.pool.close()

# Vytvoření globální instance
db = Database()

# --- DATABÁZOVÉ FUNKCE PRO COUNTING ---

async def get_setting(guild_id, setting_name):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT {setting_name} FROM guild_settings WHERE guild_id = $1", str(guild_id))
        return row[0] if row else None

async def update_setting(guild_id, setting_name, value):
    async with db.pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO guild_settings (guild_id, {setting_name}) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET {setting_name} = $2
        """, str(guild_id), value)

async def set_counting_number(guild_id, number):
    await update_setting(guild_id, "current_number", number)

async def increment_user_count(guild_id, user_id):
    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO counting_leaderboard (guild_id, user_id, daily_counts, total_counts)
            VALUES ($1, $2, 1, 1)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET 
                daily_counts = counting_leaderboard.daily_counts + 1,
                total_counts = counting_leaderboard.total_counts + 1
        """, str(guild_id), str(user_id))

async def get_top_users_daily(guild_id, limit=10):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, daily_counts FROM counting_leaderboard WHERE guild_id = $1 AND daily_counts > 0 ORDER BY daily_counts DESC LIMIT $2", str(guild_id), limit)
        return [(int(r['user_id']), r['daily_counts']) for r in rows]

async def get_top_users_lifetime(guild_id, limit=10):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, total_counts FROM counting_leaderboard WHERE guild_id = $1 AND total_counts > 0 ORDER BY total_counts DESC LIMIT $2", str(guild_id), limit)
        return [(int(r['user_id']), r['total_counts']) for r in rows]

async def reset_daily_stats(guild_id):
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE counting_leaderboard SET daily_counts = 0 WHERE guild_id = $1", str(guild_id))

async def get_all_guilds_with_counting():
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT guild_id, counting_channel_id, counting_time FROM guild_settings WHERE counting_time IS NOT NULL")
        return [(int(r['guild_id']), int(r['counting_channel_id']), r['counting_time']) for r in rows if r['counting_channel_id']]