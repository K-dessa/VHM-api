import re
from typing import List, Optional
from difflib import SequenceMatcher


def normalize_company_name(company_name: str) -> str:
    """
    Normalize a company name for comparison purposes.
    
    Args:
        company_name: Company name to normalize
        
    Returns:
        Normalized company name
    """
    if not company_name:
        return ""
    
    # Convert to lowercase
    name = company_name.lower()
    
    # Remove common punctuation and extra whitespace
    name = re.sub(r'[.,;:()"\'-]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Normalize common legal forms
    legal_forms = {
        'besloten vennootschap': 'bv',
        'besloten vennootschap met beperkte aansprakelijkheid': 'bv',
        'naamloze vennootschap': 'nv',
        'vennootschap onder firma': 'vof',
        'commanditaire vennootschap': 'cv',
        'eenmanszaak': 'eenmanszaak',
        'maatschap': 'maatschap',
        'coöperatie': 'coöperatie',
        'vereniging': 'vereniging',
        'stichting': 'stichting'
    }
    
    # Replace full legal forms with abbreviations
    for full_form, abbrev in legal_forms.items():
        name = re.sub(r'\b' + full_form + r'\b', abbrev, name)
    
    # Standardize common abbreviations
    name = re.sub(r'\bb\.?v\.?\b', 'bv', name)
    name = re.sub(r'\bn\.?v\.?\b', 'nv', name)
    name = re.sub(r'\bv\.?o\.?f\.?\b', 'vof', name)
    name = re.sub(r'\bc\.?v\.?\b', 'cv', name)
    
    # Remove "the" articles
    name = re.sub(r'\bde\b|\bhet\b|\bthe\b', '', name)
    
    # Clean up whitespace again
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def extract_legal_forms(company_name: str) -> List[str]:
    """
    Extract legal forms from a company name.
    
    Args:
        company_name: Company name to analyze
        
    Returns:
        List of identified legal forms
    """
    if not company_name:
        return []
    
    name_lower = company_name.lower()
    legal_forms = []
    
    # Define patterns for legal forms
    patterns = {
        'bv': r'\bb\.?v\.?\b|besloten vennootschap',
        'nv': r'\bn\.?v\.?\b|naamloze vennootschap',
        'vof': r'\bv\.?o\.?f\.?\b|vennootschap onder firma',
        'cv': r'\bc\.?v\.?\b|commanditaire vennootschap',
        'eenmanszaak': r'\beenmanszaak\b',
        'maatschap': r'\bmaatschap\b',
        'stichting': r'\bstichting\b',
        'vereniging': r'\bvereniging\b',
        'coöperatie': r'\bcoöperatie\b|\bcoöp\b'
    }
    
    for form, pattern in patterns.items():
        if re.search(pattern, name_lower):
            legal_forms.append(form)
    
    return legal_forms


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two text strings.
    
    Args:
        text1: First text string
        text2: Second text string
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalize both texts
    norm_text1 = normalize_company_name(text1)
    norm_text2 = normalize_company_name(text2)
    
    if not norm_text1 or not norm_text2:
        return 0.0
    
    # Use SequenceMatcher for basic similarity
    similarity = SequenceMatcher(None, norm_text1, norm_text2).ratio()
    
    # Bonus for exact word matches
    words1 = set(norm_text1.split())
    words2 = set(norm_text2.split())
    
    if words1 and words2:
        word_overlap = len(words1.intersection(words2)) / len(words1.union(words2))
        # Weight word overlap more heavily
        similarity = (similarity * 0.7) + (word_overlap * 0.3)
    
    return similarity


def match_company_variations(text: str, company_name: str) -> bool:
    """
    Check if text contains variations of the company name.
    
    Args:
        text: Text to search in
        company_name: Company name to look for
        
    Returns:
        True if a variation is found
    """
    if not text or not company_name:
        return False
    
    text_normalized = normalize_company_name(text)
    company_normalized = normalize_company_name(company_name)
    
    # Exact match
    if company_normalized in text_normalized:
        return True
    
    # Check if main company name (without legal form) appears
    company_words = company_normalized.split()
    main_name_words = []
    
    # Remove legal forms from company name
    legal_form_words = {'bv', 'nv', 'vof', 'cv', 'eenmanszaak', 'maatschap', 
                       'stichting', 'vereniging', 'coöperatie', 'coöp'}
    
    for word in company_words:
        if word not in legal_form_words:
            main_name_words.append(word)
    
    if main_name_words:
        main_name = ' '.join(main_name_words)
        if len(main_name) >= 3 and main_name in text_normalized:
            return True
    
    # Check for partial matches of significant words (length >= 4)
    significant_words = [word for word in company_words if len(word) >= 4]
    if significant_words:
        matches = sum(1 for word in significant_words if word in text_normalized)
        # Consider it a match if at least 60% of significant words are found
        if matches / len(significant_words) >= 0.6:
            return True
    
    return False


def clean_text_content(text: str) -> str:
    """
    Clean and normalize text content from web scraping.
    
    Args:
        text: Raw text content
        
    Returns:
        Cleaned text content
    """
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove HTML entities that might have been missed
    text = re.sub(r'&\w+;', ' ', text)
    
    # Remove non-printable characters
    text = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '', text)
    
    # Clean up punctuation spacing
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'([.,;:!?])\s*', r'\1 ', text)
    
    return text.strip()


def extract_case_parties(text: str) -> List[str]:
    """
    Extract company/party names from legal case text.
    
    Args:
        text: Legal case text
        
    Returns:
        List of identified party names
    """
    if not text:
        return []
    
    parties = []
    
    # Pattern for Dutch legal entities
    patterns = [
        # BV/NV patterns
        r'([A-Z][a-zA-Z\s&,-]+\s+(?:B\.?V\.?|N\.?V\.?))',
        # VOF/CV patterns  
        r'([A-Z][a-zA-Z\s&,-]+\s+(?:V\.?O\.?F\.?|C\.?V\.?))',
        # Other entities
        r'((?:Stichting|Vereniging|Coöperatie)\s+[A-Z][a-zA-Z\s&,-]+)',
        # General company patterns (words starting with capital followed by legal form)
        r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:B\.?V\.?|N\.?V\.?|V\.?O\.?F\.?|C\.?V\.?))'
    ]
    
    text_lines = text.split('\n')
    
    for pattern in patterns:
        for line in text_lines[:20]:  # Check first 20 lines where parties are usually mentioned
            matches = re.findall(pattern, line, re.IGNORECASE)
            for match in matches:
                cleaned_match = clean_text_content(match).strip()
                if len(cleaned_match) > 5 and cleaned_match not in parties:
                    parties.append(cleaned_match)
    
    return parties[:10]  # Return at most 10 parties


def is_common_company_name(company_name: str) -> bool:
    """
    Check if a company name is too common to be reliable for matching.
    
    Args:
        company_name: Company name to check
        
    Returns:
        True if the name is too common
    """
    if not company_name:
        return True
    
    normalized = normalize_company_name(company_name)
    
    # Very short names are usually too generic
    if len(normalized) < 4:
        return True
    
    # Common generic terms
    common_terms = {
        'holding', 'investment', 'management', 'services', 'trading', 
        'consulting', 'finance', 'development', 'group', 'company',
        'beheer', 'diensten', 'handel', 'ontwikkeling', 'groep',
        'maatschappij', 'onderneming', 'bedrijf'
    }
    
    words = normalized.split()
    main_words = [w for w in words if w not in {'bv', 'nv', 'vof', 'cv'}]
    
    # If all main words are common terms, it's too generic
    if main_words and all(word in common_terms for word in main_words):
        return True
    
    return False