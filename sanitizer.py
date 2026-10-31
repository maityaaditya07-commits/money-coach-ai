import re
from typing import Tuple

class PIISanitizer:
    # Basic regex patterns for common PII
    # Account Numbers: typically 9-18 digits
    ACCOUNT_PATTERN = r'\b\d{9,18}\b'
    # Emails
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    # Phone Numbers (Simple Indian format: +91 or 10 digits)
    PHONE_PATTERN = r'(\+91[\s-]?\d{10}|\b\d{10}\b)'
    # PAN Card (India)
    PAN_PATTERN = r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b'

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, list]:
        """
        Sanitizes PII from text and returns the sanitized text and a list of detected PII types.
        """
        if not text:
            return "", []

        detected = []
        sanitized_text = text

        # Sanitize Account Numbers
        if re.search(cls.ACCOUNT_PATTERN, sanitized_text):
            sanitized_text = re.sub(cls.ACCOUNT_PATTERN, "[ACCOUNT_NUMBER]", sanitized_text)
            detected.append("ACCOUNT_NUMBER")

        # Sanitize Emails
        if re.search(cls.EMAIL_PATTERN, sanitized_text):
            sanitized_text = re.sub(cls.EMAIL_PATTERN, "[EMAIL]", sanitized_text)
            detected.append("EMAIL")

        # Sanitize Phone Numbers
        if re.search(cls.PHONE_PATTERN, sanitized_text):
            sanitized_text = re.sub(cls.PHONE_PATTERN, "[PHONE_NUMBER]", sanitized_text)
            detected.append("PHONE_NUMBER")

        # Sanitize PAN
        if re.search(cls.PAN_PATTERN, sanitized_text):
            sanitized_text = re.sub(cls.PAN_PATTERN, "[PAN_CARD]", sanitized_text)
            detected.append("PAN_CARD")

        return sanitized_text, detected
