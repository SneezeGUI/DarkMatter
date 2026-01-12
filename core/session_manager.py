import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List

from .models import SessionData


class SessionManager:
    """
    Manages session persistence for traffic bot engines.
    Stores cookies and session metadata per domain in a JSON file.
    Thread-safe and uses debouncing for writes to avoid disk thrashing.
    """

    def __init__(self, storage_path: str = "resources/sessions.json"):
        # Resolve absolute path relative to project root
        self.project_root = Path(__file__).parent.parent
        self.storage_path = self.project_root / storage_path
        
        # In-memory storage: domain -> SessionData
        self._sessions: Dict[str, SessionData] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Debouncing for save
        self._save_timer: Optional[threading.Timer] = None
        self._debounce_seconds = 2.0
        
        # Load immediately
        self._load()

    def _load(self):
        """Load sessions from disk."""
        with self._lock:
            if not self.storage_path.exists():
                logging.debug(f"No session file found at {self.storage_path}, starting fresh.")
                return

            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Validate version if needed, currently just v1
                sessions_dict = data.get("sessions", {})
                
                for domain, s_data in sessions_dict.items():
                    try:
                        self._sessions[domain] = SessionData(
                            domain=domain,
                            cookies=s_data.get("cookies", []),
                            last_used=s_data.get("last_used", 0.0),
                            created=s_data.get("created", 0.0)
                        )
                    except Exception as e:
                        logging.warning(f"Failed to load session for {domain}: {e}")
                        
                logging.info(f"Loaded {len(self._sessions)} sessions from {self.storage_path}")
                
            except Exception as e:
                logging.error(f"Failed to load sessions: {e}")

    def _save_to_disk(self):
        """Write current sessions to disk."""
        with self._lock:
            try:
                # Ensure directory exists
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Convert SessionData objects to dicts
                sessions_out = {}
                for domain, session in self._sessions.items():
                    sessions_out[domain] = {
                        "cookies": session.cookies,
                        "last_used": session.last_used,
                        "created": session.created
                    }
                
                output = {
                    "sessions": sessions_out,
                    "version": 1
                }
                
                # Write to temp file then rename for atomic write
                temp_path = self.storage_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2)
                
                temp_path.replace(self.storage_path)
                logging.debug("Sessions saved to disk.")
                
            except Exception as e:
                logging.error(f"Failed to save sessions: {e}")
            finally:
                self._save_timer = None

    def _schedule_save(self):
        """Schedule a save operation (debounced)."""
        with self._lock:
            if self._save_timer:
                self._save_timer.cancel()
            
            self._save_timer = threading.Timer(self._debounce_seconds, self._save_to_disk)
            self._save_timer.daemon = True
            self._save_timer.start()

    def get_session(self, domain: str) -> Optional[SessionData]:
        """
        Retrieve session data for a domain.
        Updates last_used timestamp.
        """
        with self._lock:
            session = self._sessions.get(domain)
            if session:
                session.last_used = time.time()
                self._schedule_save()
                return session
            return None

    def save_session(self, domain: str, cookies: list[dict]):
        """
        Save or update session for a domain.
        
        Args:
            domain: The domain key (e.g., 'example.com')
            cookies: List of cookie dictionaries
        """
        with self._lock:
            now = time.time()
            if domain in self._sessions:
                session = self._sessions[domain]
                session.cookies = cookies
                session.last_used = now
            else:
                self._sessions[domain] = SessionData(
                    domain=domain,
                    cookies=cookies,
                    last_used=now,
                    created=now
                )
            
            self._schedule_save()

    def clear_sessions(self, domain: Optional[str] = None):
        """
        Clear sessions.
        
        Args:
            domain: If provided, clear only that domain. If None, clear all.
        """
        with self._lock:
            if domain:
                if domain in self._sessions:
                    del self._sessions[domain]
                    self._schedule_save()
            else:
                self._sessions.clear()
                self._schedule_save()

    def get_all_domains(self) -> list[str]:
        """Return list of all domains with active sessions."""
        with self._lock:
            return list(self._sessions.keys())

    def cleanup_expired(self, max_age_days: int = 30):
        """
        Remove sessions that haven't been used in max_age_days.
        """
        with self._lock:
            now = time.time()
            threshold = now - (max_age_days * 86400)
            
            expired = [
                d for d, s in self._sessions.items() 
                if s.last_used < threshold
            ]
            
            if expired:
                for domain in expired:
                    del self._sessions[domain]
                
                logging.info(f"Cleaned up {len(expired)} expired sessions.")
                self._schedule_save()
