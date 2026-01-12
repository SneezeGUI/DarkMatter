import json
import logging
import os
import random

from fake_useragent import UserAgent


class HeaderManager:
    _instance = None
    _profiles_pool = []  # Stores full header profiles from header_profiles.json
    _user_agents_pool = [] # Stores raw user agents from user-agents.txt
    _ua_fallback_lib = None # For fake_useragent library fallback

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._load_profiles()
            if not cls._profiles_pool: # Only try user-agents.txt if profiles failed
                cls._load_user_agents_txt()
            try:
                cls._ua_fallback_lib = UserAgent()
            except Exception:
                cls._ua_fallback_lib = None
        return cls._instance

    @classmethod
    def _load_profiles(cls):
        path = "resources/user-agents/header_profiles.json"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                    for entry in data:
                        # Ensure 'user_agent' is present and merge into 'headers' if separate
                        ua = entry.get("user_agent", "")
                        headers = entry.get("headers", {})
                        if ua and "User-Agent" not in headers:
                            headers["User-Agent"] = ua

                        # Store the combined headers (profile)
                        if headers and "User-Agent" in headers:
                            cls._profiles_pool.append(headers)
            except Exception as e:
                logging.warning(f"Error loading header profiles: {e}")

    @classmethod
    def _load_user_agents_txt(cls):
        path = "resources/user-agents/user-agents.txt"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        ua = line.strip()
                        if ua:
                            cls._user_agents_pool.append(ua)
            except Exception as e:
                logging.warning(f"Error loading user-agents.txt: {e}")

    @classmethod
    def get_random_headers(cls):
        """Returns a dict of headers."""
        if cls._profiles_pool:
            return random.choice(cls._profiles_pool)

        if cls._user_agents_pool:
            ua = random.choice(cls._user_agents_pool)
            return {
                "User-Agent": ua,
                "Accept": "*/*",
                "Connection": "keep-alive"
            }

        # Fallback generation using fake_useragent lib
        ua = cls._ua_fallback_lib.random if cls._ua_fallback_lib else "Mozilla/5.0"
        return {
            "User-Agent": ua,
            "Accept": "*/*",
            "Connection": "keep-alive"
        }
