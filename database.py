import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Vytvoří a vrátí připojení k PostgreSQL databázi."""
    if not DATABASE_URL:
        raise ValueError("❌ Chybí proměnná prostředí DATABASE_URL!")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Vytvoření základní tabulky guild_settings
    cursor.execute('''
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
        )
    ''')
    
    # 2. Vytvoření tabulky pro leaderboard
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counting_leaderboard (
            guild_id VARCHAR(50),
            user_id VARCHAR(50),
            total_counts INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')

    # 3. NOVÁ TABULKA PRO ROLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS selectable_roles (
            guild_id VARCHAR(50),
            role_id VARCHAR(50),
            PRIMARY KEY (guild_id, role_id)
        )
    ''')
    
    # FIX PRO EXISTUJÍCÍ DATABÁZI
    try:
        cursor.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS reset_on_fail INTEGER DEFAULT 1")
    except Exception:
        pass

    conn.commit()
    cursor.close()
    conn.close()
    print("🗄️ PostgreSQL Databáze byla úspěšně inicializována.")

# --- TVÉ PŮVODNÍ FUNKCE ---

def get_setting(guild_id: int, column_name: str):
    allowed_columns = {
        "welcome_channel_id", "logs_channel_id", "counting_channel_id",
        "counting_time", "current_number", "last_user_id", "current_streak",
        "reset_on_fail"
    }
    if column_name not in allowed_columns:
        raise ValueError(f"Nepovolený název sloupce: {column_name}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {column_name} FROM guild_settings WHERE guild_id = %s", (str(guild_id),))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

def update_setting(g_id, column_name, value):
    allowed_columns = {
        "welcome_channel_id", "logs_channel_id", "counting_channel_id",
        "counting_time", "current_number", "last_user_id", "current_streak",
        "reset_on_fail"
    }
    if column_name not in allowed_columns:
        raise ValueError(f"Nepovolený název sloupce: {column_name}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO guild_settings (guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING",
        (str(g_id),)
    )
    cursor.execute(
        f"UPDATE guild_settings SET {column_name} = %s WHERE guild_id = %s",
        (value, str(g_id))
    )
    conn.commit()
    cursor.close()
    conn.close()

def set_counting_number(guild_id: int, number: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    g_id = str(guild_id)
    cursor.execute("INSERT INTO guild_settings (guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING", (g_id,))
    cursor.execute("UPDATE guild_settings SET current_number = %s, last_user_id = NULL WHERE guild_id = %s", (number, g_id))
    conn.commit()
    cursor.close()
    conn.close()

def increment_user_count(guild_id: int, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    g_id, u_id = str(guild_id), str(user_id)
    cursor.execute('''
        INSERT INTO counting_leaderboard (guild_id, user_id, total_counts)
        VALUES (%s, %s, 1)
        ON CONFLICT (guild_id, user_id)
        DO UPDATE SET total_counts = counting_leaderboard.total_counts + 1
    ''', (g_id, u_id))
    conn.commit()
    cursor.close()
    conn.close()

def get_top_users(guild_id: int, limit=10):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, total_counts FROM counting_leaderboard WHERE guild_id = %s ORDER BY total_counts DESC LIMIT %s", (str(guild_id), limit))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

def get_all_guilds_with_counting():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT guild_id, counting_channel_id, counting_time FROM guild_settings WHERE counting_channel_id IS NOT NULL AND counting_time IS NOT NULL")
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

# --- NOVÉ FUNKCE PRO ROLE ---

def add_selectable_role(guild_id: int, role_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO selectable_roles (guild_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (str(guild_id), str(role_id))
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_selectable_roles(guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role_id FROM selectable_roles WHERE guild_id = %s", (str(guild_id),))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in results]