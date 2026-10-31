import sqlite3
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "finance.db")


class _DBConnection:
    """Context manager that guarantees the sqlite3 connection is closed on exit."""

    def __init__(self, db_url: str):
        self._db_url = db_url
        self._conn = None

    def __enter__(self):
        self._conn = sqlite3.connect(self._db_url)
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            self._conn.close()
        return False  # Do not suppress exceptions


def get_db_connection() -> "_DBConnection":
    # Evaluate DATABASE_URL dynamically to allow tests to override it via environment variables
    db_url = os.getenv("DATABASE_URL", "finance.db")
    return _DBConnection(db_url)


def init_db():
    with get_db_connection() as conn:
        # Transactions: deduplication via unique constraint on (date, description, amount)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT,
                merchant TEXT,
                source TEXT,
                hash TEXT UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Profile: financial preferences
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                user_id TEXT PRIMARY KEY,
                monthly_income REAL,
                monthly_budget REAL,
                fixed_costs REAL,
                emergency_fund REAL,
                currency TEXT DEFAULT 'INR',
                risk_tolerance TEXT,
                goals_enabled BOOLEAN DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Goals: target and progress
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Merchant/Category Rules: learned associations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Subscriptions: recurring payment records
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                merchant TEXT PRIMARY KEY,
                amount REAL,
                billing_cycle TEXT,
                last_billed_date TEXT,
                is_unused BOOLEAN DEFAULT 0,
                alert TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Guardrail Audit Logs: security and compliance
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guardrail_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                input TEXT,
                action TEXT,
                reason TEXT
            )
        """)

        conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
