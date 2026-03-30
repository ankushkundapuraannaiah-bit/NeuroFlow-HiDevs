import bleach
import magic
from urllib.parse import urlparse
from typing import Dict, Any, List
import re

MAX_LENGTHS = {
    "query": 5000,
    "pipeline_name": 100,
    "document_filename": 255,
}

HTML_STRIP_TAGS = []

PRIVATE_IP_RANGES = [
    r'^10\.',
    r'^172\.(1[6-9]|2[0-9]|3[01])\.',
    r'^192\.168\.',
    r'^127\.',
    r'^169\.254\.',
    r'^::1$',
    r'^fc00::'
]

def sanitize_text(text: str, field: str) -> str:
    """Strip HTML and enforce max length."""
    if len(text) > MAX_LENGTHS.get(field, 10000):
        raise ValueError(f"{field} exceeds maximum length of {MAX_LENGTHS[field]}")
    return bleach.clean(text, tags=HTML_STRIP_TAGS, strip=True)

def validate_url(url: str) -> bool:
    """Block SSRF by rejecting private IPs/localhost."""
    parsed = urlparse(url)
    if parsed.netloc in ['localhost', '127.0.0.1']:
        return False
    
    for pattern in PRIVATE_IP_RANGES:
        if re.match(pattern, parsed.hostname or ''):
            return False
    
    return bool(parsed.scheme in ['http', 'https'])

def validate_file_mimetype(filename: str, content: bytes) -> bool:
    """Validate file type by magic bytes, not just extension."""
    allowed_types = {
        '.pdf': b'%PDF-',
        '.txt': b'',
        '.md': b'',
        '.docx': b'PK\x03\x04',
        '.html': b'<!DOCTYPE',
    }
    
    mime = magic.from_buffer(content, mime=True)
    ext = filename.lower().split('.')[-1]
    
    if mime not in ['application/pdf', 'text/plain', 'text/markdown', 'text/html', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        return False
    
    if ext in allowed_types and not content.startswith(allowed_types[ext]):
        return False
    
    return True