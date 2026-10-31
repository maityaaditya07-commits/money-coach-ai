from typing import List, Dict, Any
from services.db_service import DBService
from db import get_db_connection

class CategorizerService:
    # Default fallback categories
    DEFAULT_MAPPINGS = {
        "Swiggy": "Food",
        "Zomato": "Food",
        "Cult.fit": "Health",
        "Netflix": "Entertainment",
        "Spotify": "Entertainment",
        "Uber": "Transport",
        "Ola": "Transport",
        "Amazon": "Shopping",
        "Flipkart": "Shopping",
        "BigBasket": "Groceries",
        "Blinkit": "Groceries",
        "Electricity": "Utilities",
        "Rent": "Housing",
    }

    @classmethod
    def categorize(cls, merchant: str, description: str) -> str:
        """
        Assigns a category to a transaction based on learned rules,
        then default mappings, then "Uncategorized".
        """
        # 1. Check learned rules in DB
        rules = DBService.get_rules()
        for rule in rules:
            if rule.pattern.lower() in merchant.lower() or rule.pattern.lower() in description.lower():
                return rule.category

        # 2. Check default mappings
        for pattern, category in cls.DEFAULT_MAPPINGS.items():
            if pattern.lower() in merchant.lower():
                return category

        return "Uncategorized"

    @classmethod
    def apply_category_correction(cls, tx_id: int, new_category: str) -> Dict[str, Any]:
        """
        Learns from a category correction:
        1. Updates the specific transaction.
        2. Creates a rule for the merchant.
        3. Updates all other transactions matching that merchant.
        """
        # Fetch the transaction to get the merchant
        with get_db_connection() as conn:
            row = conn.execute("SELECT merchant FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not row:
                raise ValueError("Transaction not found")
            merchant = row['merchant']

        # 1. Update the specific transaction
        DBService.update_transaction_category(tx_id, new_category)

        # 2. Persist the rule
        DBService.save_rule(merchant, new_category)

        # 3. Update all other transactions matching this merchant
        with get_db_connection() as conn:
            cursor = conn.execute(
                "UPDATE transactions SET category = ? WHERE merchant = ? AND category != ?",
                (new_category, merchant, new_category)
            )
            affected_count = cursor.rowcount
            conn.commit()

        return {
            "rule": f"{merchant} -> {new_category}",
            "affected_count": affected_count,
            "transactions_updated": affected_count + 1
        }

    @classmethod
    def categorize_batch(cls, transactions: List[Dict[str, Any]]):
        """
        Categorizes a list of raw transactions.
        """
        for tx in transactions:
            tx['category'] = cls.categorize(tx['merchant'], tx['description'])
        return transactions
