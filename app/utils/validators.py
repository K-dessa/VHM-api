"""
Validation utilities for business data.
"""

import re
from typing import Optional
from pydantic import validator


def validate_company_name(name: str) -> bool:
    """Validate company name format."""
    if not name or len(name.strip()) < 2:
        return False
    return True


def validate_website(url: str) -> bool:
    """Validate website URL format."""
    if not url:
        return False
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$'
    return bool(re.match(pattern, url))


def validate_kvk_number(kvk: str) -> bool:
    """Validate Dutch KVK number format."""
    if not kvk:
        return False
    # KVK numbers are 8 digits
    pattern = r'^\d{8}$'
    return bool(re.match(pattern, kvk))


def validate_postal_code(postal_code: str) -> bool:
    """Validate Dutch postal code format."""
    if not postal_code:
        return False
    # Dutch postal code: 1234 AB
    pattern = r'^\d{4}\s?[A-Z]{2}$'
    return bool(re.match(pattern, postal_code.upper()))


def clean_company_name(name: str) -> str:
    """Clean and normalize company name."""
    if not name:
        return ""
    
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', name.strip())
    
    # Remove common suffixes that might cause issues
    suffixes = ['BV', 'NV', 'VOF', 'CV', 'Eenmanszaak', 'Stichting', 'Vereniging']
    for suffix in suffixes:
        if cleaned.upper().endswith(f' {suffix}'):
            cleaned = cleaned[:-len(f' {suffix}')].strip()
    
    return cleaned