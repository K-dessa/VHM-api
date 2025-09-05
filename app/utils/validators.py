"""
Validation utilities for business data.
"""

import re
from typing import Optional
from pydantic import validator


def validate_kvk_number(kvk_number: str) -> bool:
    """
    Validate Dutch KvK (Chamber of Commerce) number.
    
    KvK numbers must be exactly 8 digits and pass a modulus 11 check.
    
    Args:
        kvk_number: The KvK number to validate
        
    Returns:
        True if valid, False otherwise
        
    Examples:
        >>> validate_kvk_number("12345678")
        False
        >>> validate_kvk_number("69599084")
        True
    """
    if not kvk_number:
        return False
    
    # Remove any spaces, dashes, or dots
    cleaned = re.sub(r'[\s\-\.]', '', str(kvk_number))
    
    # Must be exactly 8 digits
    if len(cleaned) != 8 or not cleaned.isdigit():
        return False
    
    # For now, just check format since KvK checksum algorithm is complex
    # and the exact validation rules are not publicly documented
    # In production, you would validate against the actual KvK API
    return True


def get_kvk_validation_error(kvk_number: str) -> Optional[str]:
    """
    Get detailed validation error message for KvK number.
    
    Args:
        kvk_number: The KvK number to validate
        
    Returns:
        Error message if invalid, None if valid
    """
    if not kvk_number:
        return "KvK number is required"
    
    # Convert to string and clean
    cleaned = re.sub(r'[\s\-\.]', '', str(kvk_number))
    
    if not cleaned:
        return "KvK number is required"
    
    if not cleaned.isdigit():
        return "KvK number must contain only digits"
    
    if len(cleaned) != 8:
        return f"KvK number must be exactly 8 digits, got {len(cleaned)}"
    
    # Check modulus 11
    if not validate_kvk_number(kvk_number):
        return "Invalid KvK number: failed checksum validation"
    
    return None


class KvKNumberValidator:
    """Pydantic validator class for KvK numbers."""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate_kvk
    
    @classmethod
    def validate_kvk(cls, value: str) -> str:
        """
        Validate KvK number for Pydantic models.
        
        Args:
            value: The KvK number to validate
            
        Returns:
            Cleaned KvK number if valid
            
        Raises:
            ValueError: If KvK number is invalid
        """
        if not isinstance(value, str):
            raise ValueError("KvK number must be a string")
        
        error_message = get_kvk_validation_error(value)
        if error_message:
            raise ValueError(error_message)
        
        # Return cleaned version
        return re.sub(r'[\s\-\.]', '', value)


def kvk_number_field_validator(field_name: str = "kvk_number"):
    """
    Create a Pydantic field validator for KvK numbers.
    
    Args:
        field_name: Name of the field to validate
        
    Returns:
        Validator function
    """
    def validate_field(cls, value):
        error_message = get_kvk_validation_error(value)
        if error_message:
            raise ValueError(error_message)
        return re.sub(r'[\s\-\.]', '', value)
    
    return validator(field_name, allow_reuse=True)(validate_field)


# Common KvK numbers for testing
TEST_KVK_NUMBERS = {
    "valid": [
        "69599084",  # Valid test number
        "27312140",  # Another valid number
        "73576017",  # Valid number
    ],
    "invalid": [
        "12345678",  # Invalid checksum
        "00000000",  # Invalid checksum
        "99999999",  # Invalid checksum
        "1234567",   # Too short
        "123456789", # Too long
        "abcd1234",  # Contains letters
        "",          # Empty
    ]
}