from db import get_db_connection
from schemas import Transaction, Rule, Profile, Goal, Subscription, GuardrailLog
from typing import List, Optional, Dict, Any


class DBService:

    # ---------------- TRANSACTIONS ----------------

    @staticmethod
    def get_transactions(
        month: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Transaction]:

        query = "SELECT * FROM transactions WHERE 1=1"
        params = []

        if month:
            query += " AND date LIKE ?"
            params.append(f"{month}%")

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Transaction(**dict(row)) for row in rows]

    @staticmethod
    def add_transaction(tx: Dict[str, Any]) -> int:
        """Insert a transaction, ignoring duplicates based on its unique hash."""

        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO transactions
                (date, description, amount, category, merchant, source, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx["date"],
                    tx["description"],
                    tx["amount"],
                    tx.get("category", "Uncategorized"),
                    tx.get("merchant", tx["description"]),
                    tx.get("source", "unknown"),
                    tx["hash"],
                ),
            )

            conn.commit()

            return cursor.lastrowid if cursor.rowcount > 0 else 0

    @staticmethod
    def add_transactions_atomic(
        transactions: List[Dict[str, Any]]
    ) -> int:
        """Insert multiple transactions and ignore duplicates."""

        with get_db_connection() as conn:
            count = 0

            try:
                for tx in transactions:
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO transactions
                        (date, description, amount, category, merchant, source, hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tx["date"],
                            tx["description"],
                            tx["amount"],
                            tx.get("category", "Uncategorized"),
                            tx.get("merchant", tx["description"]),
                            tx.get("source", "unknown"),
                            tx["hash"],
                        ),
                    )

                    if cursor.rowcount > 0:
                        count += 1

                conn.commit()
                return count

            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def update_transaction_category(tx_id: int, category: str):
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE transactions SET category = ? WHERE id = ?",
                (category, tx_id),
            )
            conn.commit()

    # ---------------- RULES ----------------

    @staticmethod
    def get_rules() -> List[Rule]:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM rules").fetchall()
            return [Rule(**dict(row)) for row in rows]

    @staticmethod
    def save_rule(pattern: str, category: str):
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO rules (pattern, category)
                VALUES (?, ?)
                """,
                (pattern, category),
            )
            conn.commit()

    @staticmethod
    def delete_rule(rule_id: int):
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM rules WHERE id = ?",
                (rule_id,),
            )
            conn.commit()

    # ---------------- PROFILE ----------------

    @staticmethod
    def get_profile(user_id: str) -> Optional[Profile]:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM profile WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if not row:
                return None
            allowed = {"user_id", "monthly_budget", "monthly_income", "fixed_costs",
                       "emergency_fund", "currency", "risk_tolerance", "goals_enabled"}
            data = {k: v for k, v in dict(row).items() if k in allowed}
            return Profile(**data)

    @staticmethod
    def update_profile(user_id: str, data: Dict[str, Any]):
        """Create or update a profile using columns supported by the database."""

        if not data:
            return

        # These columns must match the profile table in db.py.
        allowed_columns = {
            "monthly_income",
            "monthly_budget",
            "fixed_costs",
            "emergency_fund",
            "currency",
            "risk_tolerance",
            "goals_enabled",
        }

        invalid_columns = set(data.keys()) - allowed_columns

        if invalid_columns:
            raise ValueError(
                f"Invalid profile fields: {', '.join(sorted(invalid_columns))}"
            )

        keys = list(data.keys())
        values = list(data.values())

        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM profile WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if existing:
                set_clause = ", ".join(f"{key} = ?" for key in keys)

                conn.execute(
                    f"UPDATE profile SET {set_clause}, "
                    "updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    values + [user_id],
                )

            else:
                columns = ["user_id"] + keys
                placeholders = ", ".join("?" for _ in columns)
                column_names = ", ".join(columns)

                conn.execute(
                    f"""
                    INSERT INTO profile ({column_names})
                    VALUES ({placeholders})
                    """,
                    [user_id] + values,
                )

            conn.commit()

    # ---------------- GOALS ----------------

    @staticmethod
    def get_goals() -> List[Goal]:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM goals").fetchall()
            return [Goal(**dict(row)) for row in rows]

    @staticmethod
    def add_goal(goal: Dict[str, Any]) -> int:
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO goals
                (name, target_amount, current_amount, deadline)
                VALUES (?, ?, ?, ?)
                """,
                (
                    goal["name"],
                    goal["target_amount"],
                    goal["current_amount"],
                    goal["deadline"],
                ),
            )

            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def update_goal(goal_id: int, data: Dict[str, Any]):
        if not data:
            return

        allowed_columns = {
            "name",
            "target_amount",
            "current_amount",
            "deadline",
        }

        keys = list(data.keys())

        if set(keys) - allowed_columns:
            raise ValueError("Invalid goal fields")

        values = list(data.values())
        set_clause = ", ".join(f"{key} = ?" for key in keys)

        with get_db_connection() as conn:
            conn.execute(
                f"UPDATE goals SET {set_clause} WHERE id = ?",
                values + [goal_id],
            )
            conn.commit()

    @staticmethod
    def delete_goal(goal_id: int):
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM goals WHERE id = ?",
                (goal_id,),
            )
            conn.commit()

    # ---------------- SUBSCRIPTIONS ----------------

    @staticmethod
    def get_subscriptions() -> List[Subscription]:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions"
            ).fetchall()

            return [Subscription(**dict(row)) for row in rows]

    @staticmethod
    def update_subscription_unused(merchant: str, unused: bool):
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET is_unused = ?
                WHERE merchant = ?
                """,
                (unused, merchant),
            )
            conn.commit()

    # ---------------- GUARDRAILS ----------------

    @staticmethod
    def log_guardrail(
        input_text: str,
        action: str,
        reason: Optional[str] = None,
    ):
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO guardrail_logs (input, action, reason)
                VALUES (?, ?, ?)
                """,
                (input_text, action, reason),
            )
            conn.commit()

    @staticmethod
    def get_guardrail_logs() -> List[GuardrailLog]:
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM guardrail_logs
                ORDER BY timestamp DESC
                """
            ).fetchall()

            return [GuardrailLog(**dict(row)) for row in rows]
