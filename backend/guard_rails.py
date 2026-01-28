import re
from typing import List, Set
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict

# -------------------------------------------------------------------------
# Content Filtering Guard Rails
# -------------------------------------------------------------------------

class ContentFilter:
    def __init__(self):
        self.blocked_patterns = [
            r'(?i)(?:credit\s*card|bank\s*account|social\s*security|ssn|password|login)',
            r'(?i)(?:hack|exploit|vulnerability|attack|malware|virus)',
            r'(?i)(?:illegal|fraud|scam|phishing|spam)',
            r'(?i)(?:violence|threat|harm|kill|hurt)',
            r'(?i)(?:sex|porn|explicit|nude|adult)',
        ]
        
        self.warning_patterns = [
            r'(?i)(?:personal\s*information|private\s*data|confidential)',
            r'(?i)(?:financial|money|payment|transaction)',
            r'(?i)(?:security\s*breach|data\s*leak)',
        ]
    
    def contains_blocked_content(self, text: str) -> bool:
        """Check if text contains blocked patterns"""
        for pattern in self.blocked_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def contains_warning_content(self, text: str) -> bool:
        """Check if text contains warning patterns"""
        for pattern in self.warning_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def filter_response(self, response: str) -> str:
        """Filter LLM responses for sensitive content"""
        if self.contains_blocked_content(response):
            return "I'm sorry, I cannot provide information on that topic. Please contact support for assistance."
        
        if self.contains_warning_content(response):
            return response + "\n\nNote: For security reasons, please avoid sharing sensitive personal information in this chat."
        
        return response

# -------------------------------------------------------------------------
# Rate Limiting Guard Rails
# -------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window  # seconds
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def is_rate_limited(self, identifier: str) -> bool:
        """Check if user has exceeded rate limit"""
        async with self.lock:
            now = datetime.now()
            
            # Clean up old requests
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if now - req_time < timedelta(seconds=self.time_window)
            ]
            
            # Check if limit exceeded
            if len(self.requests[identifier]) >= self.max_requests:
                return True
            
            # Record new request
            self.requests[identifier].append(now)
            return False

# -------------------------------------------------------------------------
# Input Validation Guard Rails
# -------------------------------------------------------------------------

class InputValidator:
    def __init__(self):
        self.max_length = 1000  # characters
        self.min_length = 2     # characters
    
    def validate_input(self, text: str) -> dict:
        """Validate user input and return validation result"""
        if not text or text.strip() == "":
            return {"valid": False, "message": "Please provide a message."}
        
        if len(text) < self.min_length:
            return {"valid": False, "message": "Message is too short."}
        
        if len(text) > self.max_length:
            return {"valid": False, "message": "Message is too long. Please keep it under 1000 characters."}
        
        # Check for excessive repetition
        if self._has_excessive_repetition(text):
            return {"valid": False, "message": "Message contains excessive repetition."}
        
        return {"valid": True, "message": ""}
    
    def _has_excessive_repetition(self, text: str) -> bool:
        """Check for excessive character or word repetition"""
        # Simple repetition check
        words = text.split()
        if len(words) > 10:
            # Check if any word repeats too many times
            word_counts = {}
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
                if word_counts[word] > 10:  # More than 10 repetitions
                    return True
        
        return False

# -------------------------------------------------------------------------
# Global Instances
# -------------------------------------------------------------------------

content_filter = ContentFilter()
rate_limiter = RateLimiter(max_requests=15, time_window=60)  # 15 requests per minute
input_validator = InputValidator()