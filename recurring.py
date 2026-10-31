from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from services.db_service import DBService
from db import get_db_connection
from decimal import Decimal

class RecurringService:
    @staticmethod
    def detect_subscriptions() -> List[Dict[str, Any]]:
        """
        Detects likely recurring payments based on merchant, amount, and date patterns.
        """
        txs = DBService.get_transactions(limit=2000)
        merchant_txs = defaultdict(list)
        for tx in txs:
            merchant_txs[tx.merchant].append(tx)

        subscriptions = []

        for merchant, tx_list in merchant_txs.items():
            if len(tx_list) < 2:
                continue

            # Group by amount
            amount_groups = defaultdict(list)
            for tx in tx_list:
                amount_groups[tx.amount].append(tx)

            for amount, txs_with_amt in amount_groups.items():
                if len(txs_with_amt) < 2:
                    continue

                # Check for periodicity (roughly monthly or weekly)
                sorted_txs = sorted(txs_with_amt, key=lambda x: x.date)
                dates = []
                for tx in sorted_txs:
                    d = tx.date
                    if isinstance(d, str):
                        dates.append(datetime.strptime(d, "%Y-%m-%d"))
                    else:
                        dates.append(datetime.combine(d, datetime.min.time()))


                diffs = []
                for i in range(1, len(dates)):
                    diffs.append((dates[i] - dates[i-1]).days)

                # Monthly: diffs approx 28-32 days
                is_monthly = all(25 <= d <= 35 for d in diffs)
                # Weekly: diffs approx 6-8 days
                is_weekly = all(6 <= d <= 8 for d in diffs)

                if is_monthly or is_weekly:
                    cycle = "monthly" if is_monthly else "weekly"
                    last_date = sorted_txs[-1].date
                    if isinstance(last_date, str):
                        last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                    else:
                        last_dt = datetime.combine(last_date, datetime.min.time())
                    next_dt = last_dt + timedelta(days=30 if is_monthly else 7)

                    # Check for price increase
                    first_amt = sorted_txs[0].amount
                    last_amt = sorted_txs[-1].amount
                    alert = None
                    if last_amt > first_amt:
                        alert = f"Price increased from {first_amt} to {last_amt}"

                    last_billed_str = (
                        last_date if isinstance(last_date, str)
                        else last_date.strftime("%Y-%m-%d")
                    )

                    subscriptions.append({
                        "merchant": merchant,
                        "amount": float(amount),
                        "billing_cycle": cycle,
                        "last_billed_date": last_billed_str,
                        "is_unused": False,  # Default to False, updated by user
                        "alert": alert
                    })

        return subscriptions

    @classmethod
    def sync_subscriptions(cls):
        """
        Updates the subscriptions table based on detected patterns.
        """
        detected = cls.detect_subscriptions()
        for sub in detected:
            # Update or insert
            with get_db_connection() as conn:
                # Preserve is_unused flag if it exists
                existing = conn.execute(
                    "SELECT is_unused FROM subscriptions WHERE merchant = ?",
                    (sub['merchant'],)
                ).fetchone()

                is_unused = existing['is_unused'] if existing else 0

                conn.execute("""
                    INSERT OR REPLACE INTO subscriptions (merchant, amount, billing_cycle, last_billed_date, is_unused, alert)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sub['merchant'], sub['amount'], sub['billing_cycle'], sub['last_billed_date'], is_unused, sub['alert']))
                conn.commit()

        return detected
