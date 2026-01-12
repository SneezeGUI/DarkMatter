import threading
import time
from pathlib import Path
import pytest
from core.session_manager import SessionManager
from core.models import SessionData


@pytest.fixture
def session_manager():
    # Create manager pointing to temp file
    # We need to hack the path resolution since the class uses relative path from project root
    # But we can pass a relative path that resolves to our temp path if we trick it,
    # OR we can just modify the storage_path after init if we want to be invasive,
    # OR better: The class resolves `storage_path` relative to project root.
    # So if we pass an absolute path, `project_root / absolute_path` might be weird.
    
    # Let's check the code:
    # self.project_root = Path(__file__).parent.parent
    # self.storage_path = self.project_root / storage_path
    
    # If we want to use a specific absolute path, we might need to adjust the class or use a relative path.
    # Since we can't easily control project_root in the test without mocking, 
    # we will rely on creating a test file inside the project structure or mocking Path.
    
    # Easier: Just use a test path inside resources and clean it up.
    test_filename = "test_sessions_pytest.json"
    manager = SessionManager(f"resources/{test_filename}")
    yield manager
    
    # Cleanup
    if manager.storage_path.exists():
        manager.storage_path.unlink()
    if manager.storage_path.with_suffix(".tmp").exists():
        manager.storage_path.with_suffix(".tmp").unlink()

def test_save_and_get_session(session_manager):
    domain = "example.com"
    cookies = [{"name": "test", "value": "123"}]
    
    session_manager.save_session(domain, cookies)
    
    session = session_manager.get_session(domain)
    assert session is not None
    assert session.domain == domain
    assert session.cookies == cookies
    assert session.created > 0
    assert session.last_used > 0

def test_persistence(session_manager):
    domain = "persist.com"
    cookies = [{"name": "p", "value": "999"}]
    
    session_manager.save_session(domain, cookies)
    
    # Force save immediately (bypass debounce for test)
    session_manager._save_to_disk()
    
    # Create new manager instance to test load
    # We need to use the same path
    relative_path = str(session_manager.storage_path.relative_to(session_manager.project_root))
    new_manager = SessionManager(relative_path)
    
    loaded_session = new_manager.get_session(domain)
    assert loaded_session is not None
    assert loaded_session.cookies == cookies

def test_cleanup_expired(session_manager):
    domain = "expired.com"
    cookies = []
    
    session_manager.save_session(domain, cookies)
    
    # Manually age the session
    session = session_manager.get_session(domain)
    session.last_used = time.time() - (31 * 86400) # 31 days ago
    
    session_manager.cleanup_expired(max_age_days=30)
    
    assert session_manager.get_session(domain) is None

def test_get_all_domains(session_manager):
    session_manager.save_session("d1.com", [])
    session_manager.save_session("d2.com", [])
    
    domains = session_manager.get_all_domains()
    assert len(domains) == 2
    assert "d1.com" in domains
    assert "d2.com" in domains

def test_debouncing(session_manager):
    # This test is a bit tricky with time, but we can verify timer exists
    session_manager.save_session("debounce.com", [])
    assert session_manager._save_timer is not None
    assert session_manager._save_timer.is_alive()
    
    # Cancel it to avoid side effects
    session_manager._save_timer.cancel()
