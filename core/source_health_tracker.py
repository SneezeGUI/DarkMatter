import json
import logging
import threading
import time
from pathlib import Path

from .models import SourceHealth


class SourceHealthTracker:
    """
    Tracks reliability and health statistics for proxy sources.
    Thread-safe and uses debouncing for disk persistence.
    """

    def __init__(self, storage_path: str = "resources/source_health.json", max_history: int = 10):
        # Resolve absolute path relative to project root
        self.project_root = Path(__file__).parent.parent
        self.storage_path = self.project_root / storage_path

        self.max_history = max_history

        # In-memory storage: source_url -> SourceHealth
        self._sources: dict[str, SourceHealth] = {}

        # Thread safety
        self._lock = threading.RLock()

        # Debouncing for save
        self._save_timer: threading.Timer | None = None
        self._debounce_seconds = 2.0

        # Load immediately
        self._load_from_disk()

    def _load_from_disk(self):
        """Load source health data from disk."""
        with self._lock:
            if not self.storage_path.exists():
                logging.debug(f"No source health file found at {self.storage_path}, starting fresh.")
                return

            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    data = json.load(f)

                sources_dict = data.get("sources", {})

                for url, s_data in sources_dict.items():
                    try:
                        self._sources[url] = SourceHealth(
                            url=url,
                            total_scraped=s_data.get("total_scraped", 0),
                            total_alive=s_data.get("total_alive", 0),
                            total_dead=s_data.get("total_dead", 0),
                            avg_score=s_data.get("avg_score", 0.0),
                            avg_speed_ms=s_data.get("avg_speed_ms", 0.0),
                            last_check=s_data.get("last_check", 0.0),
                            created=s_data.get("created", time.time()),
                            check_history=s_data.get("check_history", [])
                        )
                    except Exception as e:
                        logging.warning(f"Failed to load health data for {url}: {e}")

                logging.info(f"Loaded health data for {len(self._sources)} sources")

            except Exception as e:
                logging.error(f"Failed to load source health data: {e}")

    def _save_to_disk(self):
        """Write current data to disk."""
        with self._lock:
            try:
                # Ensure directory exists
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)

                # Convert SourceHealth objects to dicts
                sources_out = {}
                for url, health in self._sources.items():
                    sources_out[url] = {
                        "total_scraped": health.total_scraped,
                        "total_alive": health.total_alive,
                        "total_dead": health.total_dead,
                        "avg_score": health.avg_score,
                        "avg_speed_ms": health.avg_speed_ms,
                        "last_check": health.last_check,
                        "created": health.created,
                        "check_history": health.check_history
                    }

                output = {
                    "sources": sources_out,
                    "version": 1,
                    "updated": time.time()
                }

                # Write to temp file then rename for atomic write
                temp_path = self.storage_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2)

                temp_path.replace(self.storage_path)
                logging.debug("Source health data saved to disk.")

            except Exception as e:
                logging.error(f"Failed to save source health data: {e}")
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

    def record_check(self, source_url: str, scraped: int, alive: int, dead: int, avg_score: float, avg_speed: float):
        """
        Record results of a proxy check for a specific source.
        Updates rolling averages and history.
        """
        with self._lock:
            now = time.time()

            if source_url not in self._sources:
                self._sources[source_url] = SourceHealth(url=source_url, created=now)

            source = self._sources[source_url]

            # Update history
            check_summary = {
                "timestamp": now,
                "scraped": scraped,
                "alive": alive,
                "dead": dead,
                "avg_score": avg_score,
                "avg_speed": avg_speed
            }
            source.check_history.insert(0, check_summary)
            source.check_history = source.check_history[:self.max_history]

            # Calculate rolling averages
            # Formula: new_avg = (old_avg * old_count + new_value * new_count) / total_count
            # Here we treat each check as a weighted update based on number of proxies found?
            # Or just update based on number of checks?
            # The prompt implies: "new_avg = (old_avg * old_count + new_value * new_count) / (old_count + new_count)"
            # But what is 'count'? Is it number of checks or number of proxies?
            # Assuming 'count' refers to the total number of alive proxies accumulated,
            # as score/speed are properties of alive proxies.

            if alive > 0:
                current_total_alive = source.total_alive
                new_total_alive = current_total_alive + alive

                # Update avg score
                if new_total_alive > 0:
                    source.avg_score = (
                        (source.avg_score * current_total_alive) + (avg_score * alive)
                    ) / new_total_alive

                    # Update avg speed
                    source.avg_speed_ms = (
                        (source.avg_speed_ms * current_total_alive) + (avg_speed * alive)
                    ) / new_total_alive

            # Update totals
            source.total_scraped += scraped
            source.total_alive += alive
            source.total_dead += dead
            source.last_check = now

            self._schedule_save()

    def get_health(self, source_url: str) -> SourceHealth | None:
        """Get health data for a specific source."""
        with self._lock:
            return self._sources.get(source_url)

    def get_all_sources(self) -> list[SourceHealth]:
        """Get list of all tracked sources."""
        with self._lock:
            return list(self._sources.values())

    def get_success_rate(self, source_url: str) -> float:
        """Calculate success rate (alive / total_scraped) for a source."""
        with self._lock:
            source = self._sources.get(source_url)
            if not source or source.total_scraped == 0:
                return 0.0
            return source.total_alive / source.total_scraped

    def get_healthy_sources(self, min_success_rate: float = 0.3) -> list[str]:
        """Get list of source URLs that meet minimum success rate."""
        with self._lock:
            healthy = []
            for url in self._sources:
                if self.get_success_rate(url) >= min_success_rate:
                    healthy.append(url)
            return healthy

    def get_source_ranking(self) -> list[tuple[str, float]]:
        """
        Get sources ranked by quality score.
        Score is a combination of success rate and average proxy score.
        Returns list of (url, calculated_score) tuples, sorted descending.
        """
        with self._lock:
            rankings = []
            for url, source in self._sources.items():
                success_rate = self.get_success_rate(url)

                # If no alive proxies yet, score is 0
                if success_rate == 0:
                    rankings.append((url, 0.0))
                    continue

                # Combine success rate and proxy quality score
                # Normalize proxy score (assuming 0-100 typical range for high quality, but can be higher)
                # Let's verify score definition in models/proxy_manager.
                # Proxy score = 1000 / latency. So 100ms = 10, 500ms = 2.
                # Higher is better.

                # Simple ranking metric: success_rate * avg_score
                # This balances quantity (reliability of source) with quality (speed of proxies)
                ranking_score = success_rate * source.avg_score
                rankings.append((url, ranking_score))

            # Sort by score descending
            rankings.sort(key=lambda x: x[1], reverse=True)
            return rankings

    def clear_source(self, source_url: str):
        """Remove a source from tracking."""
        with self._lock:
            if source_url in self._sources:
                del self._sources[source_url]
                self._schedule_save()

    def clear_all(self):
        """Clear all tracking data."""
        with self._lock:
            self._sources.clear()
            self._schedule_save()

    def cleanup_stale(self, max_age_days: int = 30):
        """Remove sources not checked in N days."""
        with self._lock:
            now = time.time()
            threshold = now - (max_age_days * 86400)

            stale = [
                url for url, s in self._sources.items()
                if s.last_check < threshold and s.last_check > 0
            ]

            if stale:
                for url in stale:
                    del self._sources[url]
                logging.info(f"Cleaned up {len(stale)} stale sources.")
                self._schedule_save()
