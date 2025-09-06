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


def clean_text(text: str) -> str:
    """Clean and normalize text by removing extra whitespace."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip())


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract keywords from text."""
    if not text:
        return []
    
    # Simple keyword extraction - split by whitespace and filter
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Remove common stop words
    stop_words = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
        'after', 'above', 'below', 'between', 'among', 'is', 'are', 'was',
        'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
        'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
        'can', 'this', 'that', 'these', 'those', 'a', 'an', 'de', 'het',
        'van', 'en', 'op', 'in', 'voor', 'met', 'aan', 'bij', 'uit', 'over',
        'onder', 'tussen', 'door', 'naar', 'tot', 'zonder', 'tegen', 'rond'
    }
    
    # Filter out stop words and short words
    keywords = [word for word in words if word not in stop_words and len(word) >= 3]
    
    # Count frequency and return most common
    word_count = {}
    for word in keywords:
        word_count[word] = word_count.get(word, 0) + 1
    
    # Sort by frequency and return top keywords
    sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
    return [word for word, count in sorted_words[:max_keywords]]


