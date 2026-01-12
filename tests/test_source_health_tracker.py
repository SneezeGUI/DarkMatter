import time

import pytest

from core.source_health_tracker import SourceHealthTracker


@pytest.fixture
def health_tracker():
    test_filename = "test_source_health_pytest.json"
    tracker = SourceHealthTracker(f"resources/{test_filename}")
    # Ensure clean state
    tracker.clear_all()
    yield tracker

    # Cleanup
    if tracker.storage_path.exists():
        tracker.storage_path.unlink()
    if tracker.storage_path.with_suffix(".tmp").exists():
        tracker.storage_path.with_suffix(".tmp").unlink()

def test_record_check(health_tracker):
    url = "http://test.com"

    # Initial check
    health_tracker.record_check(url, scraped=100, alive=50, dead=50, avg_score=10.0, avg_speed=100.0)

    health = health_tracker.get_health(url)
    assert health is not None
    assert health.total_scraped == 100
    assert health.total_alive == 50
    assert health.avg_score == 10.0
    assert len(health.check_history) == 1

    # Second check to test averaging
    # New avg = (10 * 50 + 20 * 50) / 100 = 15.0
    health_tracker.record_check(url, scraped=100, alive=50, dead=50, avg_score=20.0, avg_speed=200.0)

    health = health_tracker.get_health(url)
    assert health.total_scraped == 200
    assert health.total_alive == 100
    assert health.avg_score == 15.0
    assert health.avg_speed_ms == 150.0
    assert len(health.check_history) == 2

def test_persistence(health_tracker):
    url = "http://persist.com"
    health_tracker.record_check(url, scraped=10, alive=5, dead=5, avg_score=5.0, avg_speed=50.0)

    # Force save
    health_tracker._save_to_disk()

    # Load in new instance
    # Calculate relative path from project root for initialization
    relative_path = str(health_tracker.storage_path.relative_to(health_tracker.project_root))
    new_tracker = SourceHealthTracker(relative_path)

    health = new_tracker.get_health(url)
    assert health is not None
    assert health.total_alive == 5
    assert health.avg_score == 5.0
    assert len(health.check_history) == 1

def test_ranking_and_cleanup(health_tracker):
    url1 = "http://good.com"
    url2 = "http://bad.com"

    # Good source: 100% success, high score
    health_tracker.record_check(url1, scraped=10, alive=10, dead=0, avg_score=100.0, avg_speed=50.0)

    # Bad source: 10% success, low score
    health_tracker.record_check(url2, scraped=10, alive=1, dead=9, avg_score=10.0, avg_speed=500.0)

    rankings = health_tracker.get_source_ranking()
    assert len(rankings) == 2
    assert rankings[0][0] == url1
    assert rankings[1][0] == url2

    # Test cleanup
    # Manually age the good source
    health = health_tracker.get_health(url1)
    health.last_check = time.time() - (31 * 86400)

    health_tracker.cleanup_stale(max_age_days=30)

    assert health_tracker.get_health(url1) is None
    assert health_tracker.get_health(url2) is not None

def test_history_limit(health_tracker):
    url = "http://history.com"

    # Add 15 checks, limit is default 10
    for _i in range(15):
        health_tracker.record_check(url, 1, 1, 0, 1.0, 1.0)

    health = health_tracker.get_health(url)
    assert len(health.check_history) == 10
