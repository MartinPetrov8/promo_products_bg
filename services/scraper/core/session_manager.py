"""
Session Management with Anti-Detection Features

Features:
- User-agent rotation with matching headers
- Cookie persistence across sessions
- Session rotation on detection/errors
- Human-like request patterns
"""

import os
import json
import time
import random
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from threading import Lock
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# Real browser user agents (updated for 2025-2026)
USER_AGENTS = {
    'chrome_windows': [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ],
    'chrome_mac': [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ],
    'firefox_windows': [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    ],
    'safari_mac': [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ],
    'edge': [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ],
    'chrome_android': [
        "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    ],
}


def get_chrome_headers(user_agent: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Get headers that match Chrome browser"""
    # Extract version from UA
    version = "120"
    if "Chrome/" in user_agent:
        try:
            version = user_agent.split("Chrome/")[1].split(".")[0]
        except:
            pass
    
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": f'"Not_A Brand";v="8", "Chromium";v="{version}", "Google Chrome";v="{version}"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }
    
    if referer:
        headers["Referer"] = referer
    
    return headers


def get_firefox_headers(user_agent: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Get headers that match Firefox browser"""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "bg,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Connection": "keep-alive",
    }
    
    if referer:
        headers["Referer"] = referer
    
    return headers


def get_safari_headers(user_agent: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Get headers that match Safari browser"""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "bg-BG,bg;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    if referer:
        headers["Referer"] = referer
    
    return headers


@dataclass
class SessionConfig:
    """Configuration for a browser session"""
    max_requests: int = 100          # Rotate after N requests
    max_age_seconds: int = 1800      # Rotate after N seconds (30 min)
    rotate_on_errors: List[int] = field(default_factory=lambda: [403, 429, 503])
    cookie_persistence: bool = True


class BrowserSession:
    """
    A single browser session with consistent identity.
    """
    
    def __init__(
        self,
        session_id: str,
        user_agent: str,
        headers: Dict[str, str],
        config: SessionConfig
    ):
        self.session_id = session_id
        self.user_agent = user_agent
        self.headers = headers
        self.config = config
        
        self.session = requests.Session()
        self.session.headers.update(headers)
        
        # Configure retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.request_count = 0
        self.created_at = time.time()
        self.last_used = time.time()
        self.error_count = 0
    
    @property
    def should_rotate(self) -> bool:
        """Check if session should be rotated"""
        if self.request_count >= self.config.max_requests:
            return True
        if time.time() - self.created_at >= self.config.max_age_seconds:
            return True
        return False
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Make GET request"""
        self.request_count += 1
        self.last_used = time.time()
        return self.session.get(url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Make POST request"""
        self.request_count += 1
        self.last_used = time.time()
        return self.session.post(url, **kwargs)
    
    def record_error(self, status_code: int):
        """Record an error"""
        self.error_count += 1
        if status_code in self.config.rotate_on_errors:
            # Force rotation
            self.request_count = self.config.max_requests
    
    @property
    def stats(self) -> Dict:
        return {
            'session_id': self.session_id,
            'user_agent': self.user_agent[:50] + '...',
            'request_count': self.request_count,
            'error_count': self.error_count,
            'age_seconds': int(time.time() - self.created_at),
            'should_rotate': self.should_rotate,
        }


class SessionManager:
    """
    Manages browser sessions with rotation and cookie persistence.
    """
    
    def __init__(
        self,
        cookie_dir: Optional[str] = None,
        config: Optional[SessionConfig] = None
    ):
        self.cookie_dir = Path(cookie_dir) if cookie_dir else Path("./data/cookies")
        self.cookie_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or SessionConfig()
        
        self.sessions: Dict[str, BrowserSession] = {}
        self._lock = Lock()
        self._session_counter = 0
    
    def _create_session(self, domain: str) -> BrowserSession:
        """Create a new browser session"""
        self._session_counter += 1
        session_id = f"{domain}_{self._session_counter}_{int(time.time())}"
        
        # Randomly select browser type (weighted towards Chrome)
        browser_weights = [
            ('chrome_windows', 0.5),
            ('chrome_mac', 0.15),
            ('firefox_windows', 0.15),
            ('safari_mac', 0.1),
            ('edge', 0.1),
        ]
        
        browser_type = random.choices(
            [b[0] for b in browser_weights],
            weights=[b[1] for b in browser_weights]
        )[0]
        
        user_agent = random.choice(USER_AGENTS[browser_type])
        
        # Get matching headers
        if 'chrome' in browser_type or 'edge' in browser_type:
            headers = get_chrome_headers(user_agent)
        elif 'firefox' in browser_type:
            headers = get_firefox_headers(user_agent)
        else:
            headers = get_safari_headers(user_agent)
        
        session = BrowserSession(
            session_id=session_id,
            user_agent=user_agent,
            headers=headers,
            config=self.config
        )
        
        # Load persisted cookies if available
        if self.config.cookie_persistence:
            self._load_cookies(session, domain)
        
        logger.debug(f"Created new session: {session_id} ({browser_type})")
        return session
    
    def get_session(self, domain: str) -> BrowserSession:
        """Get or create session for domain"""
        with self._lock:
            session = self.sessions.get(domain)
            
            if session is None or session.should_rotate:
                if session:
                    # Save cookies before rotating
                    self._save_cookies(session, domain)
                    logger.info(f"Rotating session for {domain} (requests: {session.request_count})")
                
                session = self._create_session(domain)
                self.sessions[domain] = session
            
            return session
    
    def rotate_session(self, domain: str) -> BrowserSession:
        """Force rotate session for domain"""
        with self._lock:
            old_session = self.sessions.get(domain)
            if old_session:
                self._save_cookies(old_session, domain)
            
            new_session = self._create_session(domain)
            self.sessions[domain] = new_session
            logger.info(f"Force rotated session for {domain}")
            return new_session
    
    def _cookie_path(self, domain: str) -> Path:
        """Get cookie file path for domain"""
        safe_domain = domain.replace(".", "_").replace(":", "_")
        return self.cookie_dir / f"{safe_domain}_cookies.json"
    
    def _save_cookies(self, session: BrowserSession, domain: str):
        """Save session cookies to disk (JSON format for security)"""
        try:
            cookie_path = self._cookie_path(domain)
            # Convert cookies to JSON-serializable dict
            cookies_dict = {k: v for k, v in session.session.cookies.items()}
            with open(cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies_dict, f)
            logger.debug(f"Saved cookies for {domain}")
        except Exception as e:
            logger.warning(f"Failed to save cookies for {domain}: {e}")
    
    def _load_cookies(self, session: BrowserSession, domain: str):
        """Load cookies from disk (JSON format for security)"""
        try:
            cookie_path = self._cookie_path(domain)
            if cookie_path.exists():
                with open(cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    session.session.cookies.update(cookies)
                logger.debug(f"Loaded cookies for {domain}")
        except Exception as e:
            logger.warning(f"Failed to load cookies for {domain}: {e}")
    
    def report_error(self, domain: str, status_code: int):
        """Report error for domain session"""
        with self._lock:
            session = self.sessions.get(domain)
            if session:
                session.record_error(status_code)
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats for all sessions"""
        return {domain: session.stats for domain, session in self.sessions.items()}
    
    def save_all_cookies(self):
        """Save all session cookies"""
        for domain, session in self.sessions.items():
            self._save_cookies(session, domain)


# Default session manager
default_session_manager = SessionManager()
