#!/usr/bin/env python3
"""
Trigger State Management Module

Handles state management and caching for the trigger system.
"""

import logging
import time
import threading
from typing import Dict, Any, Optional
from webui.db_handler import get_db_connection

logger = logging.getLogger(__name__)

class TriggerStateManager:
    """Manages state and caching for the trigger system."""

    def __init__(self, cache_ttl: int = 300):
        """
        Initialize the state manager.

        Args:
            cache_ttl: Time-to-live for cached data in seconds
        """
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()

    def get_cached(self, key: str) -> Optional[Any]:
        """
        Get cached value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/not found
        """
        with self._lock:
            if key in self._cache_timestamps:
                if time.time() - self._cache_timestamps[key] < self.cache_ttl:
                    return self._cache.get(key)
                else:
                    # Expired, remove from cache
                    self._invalidate(key)
            return None

    def set_cached(self, key: str, value: Any):
        """
        Set cached value with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            self._cache[key] = value
            self._cache_timestamps[key] = time.time()

    def _invalidate(self, key: str):
        """Remove key from cache."""
        with self._lock:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

    def invalidate_pattern(self, pattern: str):
        """
        Invalidate all cache keys matching a pattern.

        Args:
            pattern: Pattern to match (simple string contains check)
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                self._invalidate(key)

    def clear_expired(self):
        """Clear all expired cache entries."""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self._cache_timestamps.items()
                if current_time - timestamp >= self.cache_ttl
            ]
            for key in expired_keys:
                self._invalidate(key)

    def get_zone_nodes(self, zone_id: int) -> list:
        """
        Get cached list of nodes currently in a zone.

        Args:
            zone_id: Zone ID

        Returns:
            List of node IDs in the zone
        """
        cache_key = f"zone_nodes_{zone_id}"
        cached = self.get_cached(cache_key)

        if cached is not None:
            return cached

        # Load from database
        nodes = self._load_zone_nodes_from_db(zone_id)
        self.set_cached(cache_key, nodes)
        return nodes

    def _load_zone_nodes_from_db(self, zone_id: int) -> list:
        """Load current zone nodes from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id FROM node_zones
                WHERE zone_id = ? AND is_currently_in = 1
            """, (zone_id,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to load zone nodes from DB: {e}")
            return []
        finally:
            conn.close()

    def get_node_zones(self, node_id: str) -> list:
        """
        Get cached list of zones a node is currently in.

        Args:
            node_id: Node ID

        Returns:
            List of zone IDs the node is in
        """
        cache_key = f"node_zones_{node_id}"
        cached = self.get_cached(cache_key)

        if cached is not None:
            return cached

        # Load from database
        zones = self._load_node_zones_from_db(node_id)
        self.set_cached(cache_key, zones)
        return zones

    def _load_node_zones_from_db(self, node_id: str) -> list:
        """Load current node zones from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT zone_id FROM node_zones
                WHERE node_id = ? AND is_currently_in = 1
            """, (node_id,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to load node zones from DB: {e}")
            return []
        finally:
            conn.close()

    def update_zone_node_state(self, node_id: str, zone_id: int, is_inside: bool):
        """
        Update cached zone/node state and invalidate related caches.

        Args:
            node_id: Node ID
            zone_id: Zone ID
            is_inside: Whether node is inside zone
        """
        with self._lock:
            # Update zone nodes cache
            zone_nodes = self.get_zone_nodes(zone_id)
            if is_inside and node_id not in zone_nodes:
                zone_nodes.append(node_id)
            elif not is_inside and node_id in zone_nodes:
                zone_nodes.remove(node_id)
            self.set_cached(f"zone_nodes_{zone_id}", zone_nodes)

            # Update node zones cache
            node_zones = self.get_node_zones(node_id)
            if is_inside and zone_id not in node_zones:
                node_zones.append(zone_id)
            elif not is_inside and zone_id in node_zones:
                node_zones.remove(zone_id)
            self.set_cached(f"node_zones_{node_id}", node_zones)

    def get_trigger_stats(self) -> Dict[str, Any]:
        """
        Get trigger execution statistics.

        Returns:
            Dictionary with trigger statistics
        """
        cache_key = "trigger_stats"
        cached = self.get_cached(cache_key)

        if cached is not None:
            return cached

        # Load from database
        stats = self._load_trigger_stats_from_db()
        self.set_cached(cache_key, stats)
        return stats

    def _load_trigger_stats_from_db(self) -> Dict[str, Any]:
        """Load trigger statistics from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Total triggers executed
            cursor.execute("SELECT COUNT(*) FROM trigger_logs")
            total_triggers = cursor.fetchone()[0]

            # Triggers by event type
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM trigger_logs
                GROUP BY event_type
            """)
            event_counts = dict(cursor.fetchall())

            # Recent triggers (last 24 hours)
            cursor.execute("""
                SELECT COUNT(*) FROM trigger_logs
                WHERE timestamp > datetime('now', '-1 day')
            """)
            recent_triggers = cursor.fetchone()[0]

            # Most active zones
            cursor.execute("""
                SELECT z.name, COUNT(tl.id) as trigger_count
                FROM zones z
                LEFT JOIN trigger_logs tl ON z.name = tl.zone_name
                GROUP BY z.id, z.name
                ORDER BY trigger_count DESC
                LIMIT 10
            """)
            active_zones = cursor.fetchall()

            return {
                'total_triggers': total_triggers,
                'event_counts': event_counts,
                'recent_triggers': recent_triggers,
                'active_zones': active_zones
            }

        except Exception as e:
            logger.error(f"Failed to load trigger stats from DB: {e}")
            return {
                'total_triggers': 0,
                'event_counts': {},
                'recent_triggers': 0,
                'active_zones': []
            }
        finally:
            conn.close()

    def get_zone_stats(self, zone_id: int) -> Dict[str, Any]:
        """
        Get statistics for a specific zone.

        Args:
            zone_id: Zone ID

        Returns:
            Zone statistics
        """
        cache_key = f"zone_stats_{zone_id}"
        cached = self.get_cached(cache_key)

        if cached is not None:
            return cached

        # Load from database
        stats = self._load_zone_stats_from_db(zone_id)
        self.set_cached(cache_key, stats)
        return stats

    def _load_zone_stats_from_db(self, zone_id: int) -> Dict[str, Any]:
        """Load zone statistics from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Current nodes in zone
            cursor.execute("""
                SELECT COUNT(*) FROM node_zones
                WHERE zone_id = ? AND is_currently_in = 1
            """, (zone_id,))
            current_nodes = cursor.fetchone()[0]

            # Total visits (entries)
            cursor.execute("""
                SELECT COUNT(*) FROM node_zones
                WHERE zone_id = ?
            """, (zone_id,))
            total_visits = cursor.fetchone()[0]

            # Recent activity (last 24 hours)
            cursor.execute("""
                SELECT COUNT(*) FROM trigger_logs tl
                JOIN triggers t ON tl.trigger_id = t.id
                WHERE t.zone_id = ? AND tl.timestamp > datetime('now', '-1 day')
            """, (zone_id,))
            recent_activity = cursor.fetchone()[0]

            # Most frequent visitors
            cursor.execute("""
                SELECT node_id, COUNT(*) as visit_count
                FROM node_zones
                WHERE zone_id = ?
                GROUP BY node_id
                ORDER BY visit_count DESC
                LIMIT 5
            """, (zone_id,))
            frequent_visitors = cursor.fetchall()

            return {
                'current_nodes': current_nodes,
                'total_visits': total_visits,
                'recent_activity': recent_activity,
                'frequent_visitors': frequent_visitors
            }

        except Exception as e:
            logger.error(f"Failed to load zone stats from DB: {e}")
            return {
                'current_nodes': 0,
                'total_visits': 0,
                'recent_activity': 0,
                'frequent_visitors': []
            }
        finally:
            conn.close()

    def invalidate_zone_cache(self, zone_id: int):
        """Invalidate all cache entries related to a zone."""
        with self._lock:
            patterns = [f"zone_nodes_{zone_id}", f"zone_stats_{zone_id}"]
            for pattern in patterns:
                self.invalidate_pattern(pattern)

    def invalidate_node_cache(self, node_id: str):
        """Invalidate all cache entries related to a node."""
        with self._lock:
            patterns = [f"node_zones_{node_id}"]
            for pattern in patterns:
                self.invalidate_pattern(pattern)

    def invalidate_trigger_cache(self):
        """Invalidate trigger-related caches."""
        with self._lock:
            self.invalidate_pattern("trigger_stats")

    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about cache contents."""
        with self._lock:
            return {
                'cache_size': len(self._cache),
                'cache_keys': list(self._cache.keys()),
                'oldest_entry': min(self._cache_timestamps.values()) if self._cache_timestamps else None,
                'newest_entry': max(self._cache_timestamps.values()) if self._cache_timestamps else None
            }

# Global state manager instance
state_manager = TriggerStateManager()