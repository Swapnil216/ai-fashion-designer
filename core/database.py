import sqlite3
import uuid
import os
import yaml
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")


def load_config():
    with open(CONFIG_PATH, "r") as file:
        return yaml.safe_load(file)


CONFIG = load_config()
DB_PATH = os.path.join(BASE_DIR, CONFIG['system']['db_path'])


def get_connection():
    """Establish a connection to the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the wardrobe table safely."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wardrobe (
            item_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            sub_category TEXT,
            color_hex TEXT,
            formality_score INTEGER,
            weather_suitability TEXT,
            image_path TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def add_item(category, sub_category, color_hex, formality_score, weather_suitability, image_path):
    conn = get_connection()
    cursor = conn.cursor()
    item_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO wardrobe (item_id, category, sub_category, color_hex, formality_score, weather_suitability, image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (item_id, category, sub_category, color_hex, formality_score, weather_suitability, image_path))
    conn.commit()
    conn.close()
    return item_id


def get_active_wardrobe(weather_filter=None):
    """Fetch active items, triggering auto-init if the table is missing."""
    init_db()

    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM wardrobe WHERE is_active = 1"
    params = []

    if weather_filter:
        query += " AND weather_suitability IN (?, 'all')"
        params.append(weather_filter)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def retire_item(item_id):
    """Soft delete an item so the AI no longer considers it."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE wardrobe SET is_active = 0 WHERE item_id = ?', (item_id,))

    conn.commit()
    conn.close()


def update_item(item_id, category, sub_category, color_hex, formality_score, weather_suitability):
    """Updates the metadata for a specific item."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE wardrobe 
        SET category = ?, sub_category = ?, color_hex = ?, formality_score = ?, weather_suitability = ?
        WHERE item_id = ?
    ''', (category, sub_category, color_hex, formality_score, weather_suitability, item_id))

    conn.commit()
    conn.close()

def upgrade_db_schema():
    """Safely adds the last_worn column to an existing database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE wardrobe ADD COLUMN last_worn DATE DEFAULT NULL")
        conn.commit()
        print("✅ Database upgraded: Added memory tracking.")
    except Exception:
        # If the column already exists, SQLite throws an error, which we can safely ignore
        pass
    finally:
        conn.close()

def log_outfit_as_worn(item_ids):
    """Updates the last_worn date for a list of items to today."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    # Filter out nulls/None
    valid_ids = [str(i) for i in item_ids if i]

    if valid_ids:
        placeholders = ','.join(['?'] * len(valid_ids))
        cursor.execute(f"UPDATE wardrobe SET last_worn = ? WHERE item_id IN ({placeholders})", [today] + valid_ids)
        conn.commit()
    conn.close()

init_db()