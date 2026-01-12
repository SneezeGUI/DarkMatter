import pytest
from unittest.mock import MagicMock, patch, call
from core.proxy_manager import ThreadedProxyManager
from core.models import ProxyConfig, ProxyCheckResult
from tests.fixtures.mock_responses import build_proxy_config, build_proxy_check_result

class TestProxyHealthIntegration:
    @pytest.fixture
    def manager(self):
        # Patch SourceHealthTracker before initializing manager
        with patch("core.proxy_manager.SourceHealthTracker") as mock_tracker_cls:
            mock_tracker = mock_tracker_cls.return_value
            mgr = ThreadedProxyManager()
            # Ensure we attach the mock instance to the manager
            mgr.health_tracker = mock_tracker
            yield mgr

    @patch("core.proxy_manager.std_requests.get")
    def test_scrape_records_stats(self, mock_get, manager):
        """Verify scrape records 'scraped' count to tracker."""
        source_url = "http://source1.com/proxies"
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Mock 2 proxies found
        mock_response.text = "1.1.1.1:8080\n2.2.2.2:9090"
        mock_get.return_value = mock_response

        proxies = manager.scrape(
            sources=[source_url],
            protocols=["http"],
            max_threads=1
        )

        assert len(proxies) == 2
        assert proxies[0].source == source_url
        assert proxies[1].source == source_url

        # Verify record_check was called
        manager.health_tracker.record_check.assert_called_with(
            source_url,
            scraped=2,
            alive=0,
            dead=0,
            avg_score=0.0,
            avg_speed=0.0
        )

    def test_check_proxies_records_health(self, manager):
        """Verify check_proxies records alive/dead stats to tracker."""
        source1 = "http://s1.com"
        source2 = "http://s2.com"

        # 3 proxies:
        # P1 from S1 (Alive)
        # P2 from S1 (Dead)
        # P3 from S2 (Alive)
        p1 = build_proxy_config(host="1.1.1.1", port=80, source=source1)
        p2 = build_proxy_config(host="2.2.2.2", port=80, source=source1)
        p3 = build_proxy_config(host="3.3.3.3", port=80, source=source2)
        
        proxies = [p1, p2, p3]

        def side_effect(proxy, *args, **kwargs):
            if proxy.host == "1.1.1.1":
                res = build_proxy_check_result(host=proxy.host, port=proxy.port, status="Active", speed=100)
                res.proxy.source = proxy.source
                res.score = 10.0
                return res
            elif proxy.host == "2.2.2.2":
                res = build_proxy_check_result(host=proxy.host, port=proxy.port, status="Dead", speed=0)
                res.proxy.source = proxy.source
                return res
            elif proxy.host == "3.3.3.3":
                res = build_proxy_check_result(host=proxy.host, port=proxy.port, status="Active", speed=200)
                res.proxy.source = proxy.source
                res.score = 5.0
                return res
            return None

        with patch.object(manager, "_test_proxy", side_effect=side_effect):
             results = manager.check_proxies(
                 proxies=proxies,
                 target_url="http://test.com",
                 timeout_ms=1000,
                 real_ip="127.0.0.1",
                 on_progress=None,
                 concurrency=1
             )

        assert len(results) == 2  # P1 and P3 are active

        # Verify calls to record_check
        # We expect two calls, one for each source
        
        # Check S1: 1 alive, 1 dead (Total 2)
        # avg_score = 10.0, avg_speed = 100.0
        call1 = call(
            source1, scraped=0, alive=1, dead=1, avg_score=10.0, avg_speed=100.0
        )
        
        # Check S2: 1 alive, 0 dead (Total 1)
        # avg_score = 5.0, avg_speed = 200.0
        call2 = call(
            source2, scraped=0, alive=1, dead=0, avg_score=5.0, avg_speed=200.0
        )
        
        manager.health_tracker.record_check.assert_has_calls([call1, call2], any_order=True)
