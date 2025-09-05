import re
from typing import Dict, Optional, List
from urllib.parse import urlparse
import structlog

logger = structlog.get_logger(__name__)


def parse_robots_rules(robots_txt: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Parse robots.txt content into structured rules.
    
    Args:
        robots_txt: Raw robots.txt content
        
    Returns:
        Dictionary with user agents as keys and rules as values
    """
    if not robots_txt:
        return {}
    
    rules = {}
    current_user_agents = []
    
    for line in robots_txt.split('\n'):
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
        
        # Parse directives
        if ':' in line:
            directive, value = line.split(':', 1)
            directive = directive.strip().lower()
            value = value.strip()
            
            if directive == 'user-agent':
                current_user_agents = [value]
            elif directive in ['disallow', 'allow', 'crawl-delay', 'sitemap']:
                for user_agent in current_user_agents:
                    if user_agent not in rules:
                        rules[user_agent] = []
                    rules[user_agent].append({
                        'directive': directive,
                        'value': value
                    })
    
    return rules


def is_path_allowed(url: str, user_agent: str, robots_txt: str = None) -> bool:
    """
    Check if a path is allowed for the given user agent.
    
    Args:
        url: URL or path to check
        user_agent: User agent string
        robots_txt: Optional robots.txt content
        
    Returns:
        True if path is allowed, False otherwise
    """
    try:
        if not robots_txt:
            # If no robots.txt, assume allowed
            return True
        
        # Parse the URL to get the path
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        if not path:
            path = '/'
        
        rules = parse_robots_rules(robots_txt)
        
        # Check rules for specific user agent first
        applicable_rules = rules.get(user_agent, [])
        
        # If no specific rules, check for wildcard
        if not applicable_rules:
            applicable_rules = rules.get('*', [])
        
        # Default is allowed
        allowed = True
        
        # Process rules in order (disallow rules typically come first)
        for rule in applicable_rules:
            directive = rule['directive']
            pattern = rule['value']
            
            if directive == 'disallow':
                if _path_matches_pattern(path, pattern):
                    allowed = False
            elif directive == 'allow':
                if _path_matches_pattern(path, pattern):
                    allowed = True
        
        return allowed
        
    except Exception as e:
        logger.warning("Error checking robots.txt compliance", 
                      url=url, user_agent=user_agent, error=str(e))
        # Default to allowed on error
        return True


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """
    Check if a path matches a robots.txt pattern.
    
    Args:
        path: URL path to check
        pattern: robots.txt pattern
        
    Returns:
        True if path matches pattern
    """
    if not pattern:
        return False
    
    # Empty pattern means root
    if pattern == '/':
        return True
    
    # Convert robots.txt pattern to regex
    # * matches any sequence of characters
    # $ at end means exact match
    
    regex_pattern = re.escape(pattern)
    regex_pattern = regex_pattern.replace(r'\*', '.*')
    
    if pattern.endswith('$'):
        regex_pattern = regex_pattern[:-2] + '$'  # Remove escaped $ and add real $
    else:
        # If no $ at end, pattern matches if path starts with it
        regex_pattern = '^' + regex_pattern
    
    try:
        return bool(re.match(regex_pattern, path))
    except re.error:
        # If regex is invalid, fall back to simple string matching
        return path.startswith(pattern)


def get_crawl_delay(robots_txt: str, user_agent: str = '*') -> Optional[int]:
    """
    Extract crawl delay from robots.txt for a user agent.
    
    Args:
        robots_txt: robots.txt content
        user_agent: User agent to check for
        
    Returns:
        Crawl delay in seconds, or None if not specified
    """
    if not robots_txt:
        return None
    
    try:
        rules = parse_robots_rules(robots_txt)
        
        # Check rules for specific user agent first
        applicable_rules = rules.get(user_agent, [])
        
        # If no specific rules, check for wildcard
        if not applicable_rules:
            applicable_rules = rules.get('*', [])
        
        # Look for crawl-delay directive
        for rule in applicable_rules:
            if rule['directive'] == 'crawl-delay':
                try:
                    return int(float(rule['value']))
                except ValueError:
                    continue
        
        return None
        
    except Exception as e:
        logger.warning("Error parsing crawl delay", error=str(e))
        return None


