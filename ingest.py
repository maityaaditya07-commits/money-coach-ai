import csv
import io
import hashlib
import re
import pdfplumber
from typing import List, Dict, Any, Tuple, Optional
from services.db_service import DBService
from services.sanitizer import PIISanitizer
from datetime import datetime

class IngestionService:
    @staticmethod
    def normalize_merchant(merchant: str) -> str:
        """
        Normalizes messy merchant names to a consistent form.
        Example: 'AMZN MKTP*2K4' -> 'Amazon'
        """
        if not merchant:
            return "Unknown"

        merchant = merchant.upper().strip()

        # Mapping for common Indian messy merchants
        mappings = {
            r"AMZN|AMAZON": "Amazon",
            r"FLIPKART|FK": "Flipkart",
            r"SWIGGY": "Swiggy",
            r"ZOMATO": "Zomato",
            r"CULT\.FIT|CULT": "Cult.fit",
            r"UBER": "Uber",
            r"OLA": "Ola",
            r"SPOTIFY": "Spotify",
            r"NETFLIX": "Netflix",
            r"BIGBASKET": "BigBasket",
            r"BLINKIT": "Blinkit",
            r"ELECTRICITY|BESCOM|TATA POWER": "Electricity",
        }

        for pattern, normalized in mappings.items():
            if re.search(pattern, merchant):
                return normalized

        return merchant.title()

    @staticmethod
    def generate_hash(date: str, description: str, amount: float) -> str:
        """
        Generates a unique hash for a transaction to prevent duplicates.
        """
        payload = f"{date}|{description.strip().lower()}|{amount:.2f}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @classmethod
    def process_csv(cls, content: bytes) -> List[Dict[str, Any]]:
        """
        Parses CSV content in memory.
        Expected format: Date, Description, Amount, Category, Merchant
        """
        decoded_content = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded_content))

        transactions = []
        for row in csv_reader:
            # Handle different possible header names
            date = row.get('Date') or row.get('date')
            desc = row.get('Description') or row.get('description')
            amt_str = row.get('Amount') or row.get('amount')
            cat = row.get('Category') or row.get('category') or "Uncategorized"
            merch = row.get('Merchant') or row.get('merchant') or desc

            if not all([date, desc, amt_str]):
                continue

            try:
                amount = float(amt_str)
            except ValueError:
                continue

            merchant = cls.normalize_merchant(merch)

            transactions.append({
                "date": date,
                "description": desc,
                "amount": amount,
                "category": cat,
                "merchant": merchant,
                "source": "csv",
                "hash": cls.generate_hash(date, desc, amount)
            })

        return transactions

    @classmethod
    def process_sms(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Parses a single bank/UPI SMS.
        Example: 'A/c XX1234 debited for Rs 450.00 on 2026-10-20 via UPI to Swiggy'
        """
        # Regex for amount
        amt_match = re.search(r'(?:Rs|INR)\s*([\d,]+\.?\d*)', text)
        if not amt_match:
            return None

        amount = float(amt_match.group(1).replace(',', ''))

        # Regex for date (YYYY-MM-DD or DD-MM-YYYY)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})', text)
        date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Extract merchant (look for "to [Merchant]" or "via [Merchant]")
        merch_match = re.search(r'(?:to|via)\s+([A-Za-z\s]+?)(?:\.|\s+Ref|Crt|on|$)', text)
        merchant_raw = merch_match.group(1).strip() if merch_match else "Unknown"
        merchant = cls.normalize_merchant(merchant_raw)

        # Determine if credit or debit
        is_credit = "credited" in text.lower()
        if not is_credit:
            amount = -abs(amount)

        return {
            "date": date,
            "description": text,
            "amount": amount,
            "category": "Uncategorized",
            "merchant": merchant,
            "source": "sms",
            "hash": cls.generate_hash(date, text, amount)
        }

    @classmethod
    def process_pdf(cls, content: bytes) -> List[Dict[str, Any]]:
        """
        Extracts transactions from PDF in memory.
        """
        transactions = []
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if not table:
                        continue

                    # Assume first row is header
                    headers = [h.lower() for h in table[0] if h]
                    for row in table[1:]:
                        # Map row to dictionary based on headers
                        row_data = {}
                        for i, val in enumerate(row):
                            if i < len(headers):
                                row_data[headers[i]] = val

                        # Extract core fields
                        date = row_data.get('date')
                        desc = row_data.get('description') or row_data.get('particulars')
                        amt_str = row_data.get('amount') or row_data.get('value')

                        if not all([date, desc, amt_str]):
                            continue

                        try:
                            # Clean amount string (remove commas, currency symbols)
                            clean_amt = re.sub(r'[^\d.]', '', amt_str)
                            amount = float(clean_amt)
                        except ValueError:
                            continue

                        merchant = cls.normalize_merchant(desc)

                        transactions.append({
                            "date": date,
                            "description": desc,
                            "amount": amount,
                            "category": "Uncategorized",
                            "merchant": merchant,
                            "source": "pdf",
                            "hash": cls.generate_hash(date, desc, amount)
                        })
        except Exception:
            # If extraction fails (e.g. scanned PDF), let the router handle the error
            raise RuntimeError("Could not extract transactions from PDF. The file may be scanned or image-based.")

        return transactions

    @classmethod
    def ingest(cls, transactions: List[Dict[str, Any]]):
        """
        Saves parsed transactions to DB atomically, ignoring duplicates.
        """
        return DBService.add_transactions_atomic(transactions)
