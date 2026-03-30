import re
from typing import List, Tuple

SECRET_PATTERNS = [
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
    # Generic API keys
    (r"(?:api|secret|token|key|password)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+_-]{20,}[\"']", "api_key"),
    # Private key headers
    (r"-----BEGIN (?:RSA|EC|DSA|PGP) PRIVATE KEY-----", "private_key"),
    # JWT tokens
    (r"[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+", "jwt_token"),
    # Bearer tokens
    (r"bearer\s+[A-Za-z0-9-_]{20,}", "bearer_token"),
]

def detect_and_redact_secrets(text: str) -> Tuple[str, List[Dict]]:
    """Redact secrets and return redaction log."""
    redactions = []
    redacted_text = text
    
    for pattern, secret_type in SECRET_PATTERNS:
        for match in re.finditer(pattern, redacted_text, re.IGNORECASE):
            redactions.append({
                "type": secret_type,
                "redacted_value": match.group(0),
                "start": match.start(),
                "end": match.end()
            })
            redacted_text = (
                redacted_text[:match.start()] +
                "[REDACTED]" +
                redacted_text[match.end():]
            )
    
    return redacted_text, redactions