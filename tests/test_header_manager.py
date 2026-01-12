import pytest
from unittest.mock import patch, mock_open, MagicMock
import core.header_manager
from core.header_manager import HeaderManager

class TestHeaderManager:
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        # Reset singleton state before and after each test
        HeaderManager._instance = None
        HeaderManager._profiles_pool = []
        HeaderManager._user_agents_pool = []
        HeaderManager._ua_fallback_lib = None
        yield
        HeaderManager._instance = None
        HeaderManager._profiles_pool = []
        HeaderManager._user_agents_pool = []
        HeaderManager._ua_fallback_lib = None

    def test_singleton_pattern(self):
        """Test that HeaderManager follows singleton pattern."""
        hm1 = HeaderManager()
        hm2 = HeaderManager()
        assert hm1 is hm2

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='[{"user_agent": "TestUA", "headers": {"Accept": "test"}}]')
    def test_load_profiles(self, mock_file, mock_exists):
        """Test loading profiles from JSON file."""
        mock_exists.return_value = True
        
        hm = HeaderManager()
        
        assert len(HeaderManager._profiles_pool) == 1
        headers = HeaderManager._profiles_pool[0]
        assert headers["User-Agent"] == "TestUA"
        assert headers["Accept"] == "test"

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='UA1\nUA2\n')
    def test_load_user_agents_txt(self, mock_file, mock_exists):
        """Test loading user agents from text file when profiles fail."""
        mock_exists.side_effect = [False, True]
        
        hm = HeaderManager()
        
        assert len(HeaderManager._user_agents_pool) == 2
        assert "UA1" in HeaderManager._user_agents_pool
        assert "UA2" in HeaderManager._user_agents_pool

    def test_get_random_headers_from_profiles(self):
        """Test getting headers when profiles are loaded."""
        with patch.object(HeaderManager, '_load_profiles') as mock_load:
             HeaderManager._profiles_pool = [{"User-Agent": "ProfileUA", "Header": "Value"}]
             hm = HeaderManager()
             
             headers = hm.get_random_headers()
             assert headers["User-Agent"] == "ProfileUA"
             assert headers["Header"] == "Value"

    def test_get_random_headers_from_ua_pool(self):
        """Test getting headers when only raw UAs are loaded."""
        with patch.object(HeaderManager, '_load_profiles') as mock_load, \
             patch.object(HeaderManager, '_load_user_agents_txt') as mock_load_txt:
            
            HeaderManager._profiles_pool = []
            HeaderManager._user_agents_pool = ["RawUA"]
            hm = HeaderManager()
            
            headers = hm.get_random_headers()
            assert headers["User-Agent"] == "RawUA"
            assert "Accept" in headers

    def test_fallback_generation(self):
        """Test fallback to fake_useragent lib."""
        with patch.object(core.header_manager, 'UserAgent') as MockUA, \
             patch.object(HeaderManager, '_load_profiles'), \
             patch.object(HeaderManager, '_load_user_agents_txt'):
            
            mock_instance = MagicMock()
            mock_instance.random = "FallbackUA"
            MockUA.return_value = mock_instance
            
            HeaderManager._instance = None
            hm = HeaderManager()
            
            # Ensure pools are empty (mocked load methods ensure they stay empty if initialized empty)
            HeaderManager._profiles_pool = []
            HeaderManager._user_agents_pool = []

            headers = hm.get_random_headers()
            assert headers["User-Agent"] == "FallbackUA"

    def test_ultimate_fallback(self):
        """Test ultimate fallback when nothing is available."""
        with patch.object(core.header_manager, 'UserAgent') as MockUA, \
             patch.object(HeaderManager, '_load_profiles'), \
             patch.object(HeaderManager, '_load_user_agents_txt'):
             
            MockUA.side_effect = Exception("Boom")
            
            HeaderManager._instance = None
            hm = HeaderManager()
            
            HeaderManager._profiles_pool = []
            HeaderManager._user_agents_pool = []
            
            assert HeaderManager._ua_fallback_lib is None
            
            headers = hm.get_random_headers()
            assert headers["User-Agent"] == "Mozilla/5.0"