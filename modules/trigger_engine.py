#!/usr/bin/env python3
"""
Trigger Engine Module

Handles position processing, zone detection with hysteresis, and trigger matching logic.
"""

import logging
import time
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from webui.db_handler import get_db_connection

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Represents a geographic position."""
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    timestamp: Optional[float] = None

@dataclass
class Zone:
    """Represents a geographic zone."""
    id: int
    name: str
    latitude: float
    longitude: float
    radius: float
    active: bool = True

@dataclass
class Trigger:
    """Represents a zone trigger."""
    id: int
    name: str
    zone_id: int
    event_type: str  # 'enter' or 'exit'
    action_type: str
    action_payload: str
    active: bool = True

class TriggerEngine:
    """Main trigger engine for processing position updates and zone events."""

    def __init__(self, hysteresis_distance: float = 10.0):
        """
        Initialize the trigger engine.

        Args:
            hysteresis_distance: Distance in meters to prevent trigger oscillation
        """
        self.hysteresis_distance = hysteresis_distance
        self.node_positions: Dict[str, Position] = {}  # node_id -> last known position
        self.node_zone_states: Dict[str, Dict[int, bool]] = {}  # node_id -> {zone_id -> is_inside}
        self.zones: Dict[int, Zone] = {}
        self.triggers: Dict[int, Trigger] = {}

        self._load_zones()
        self._load_triggers()

    def _load_zones(self):
        """Load active zones from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, latitude, longitude, radius, active
                FROM zones
                WHERE active = 1
            """)
            rows = cursor.fetchall()

            self.zones.clear()
            for row in rows:
                zone = Zone(
                    id=row[0],
                    name=row[1],
                    latitude=row[2],
                    longitude=row[3],
                    radius=row[4],
                    active=bool(row[5])
                )
                self.zones[zone.id] = zone

            logger.info(f"Loaded {len(self.zones)} active zones")

        except Exception as e:
            logger.error(f"Failed to load zones: {e}")
        finally:
            conn.close()

    def _load_triggers(self):
        """Load active triggers from database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, zone_id, event_type, action_type, action_payload, active
                FROM triggers
                WHERE active = 1
            """)
            rows = cursor.fetchall()

            self.triggers.clear()
            for row in rows:
                trigger = Trigger(
                    id=row[0],
                    name=row[1],
                    zone_id=row[2],
                    event_type=row[3],
                    action_type=row[4],
                    action_payload=row[5],
                    active=bool(row[6])
                )
                self.triggers[trigger.id] = trigger

            logger.info(f"Loaded {len(self.triggers)} active triggers")

        except Exception as e:
            logger.error(f"Failed to load triggers: {e}")
        finally:
            conn.close()

    def reload_configuration(self):
        """Reload zones and triggers from database."""
        self._load_zones()
        self._load_triggers()

    def calculate_distance(self, pos1: Position, pos2: Position) -> float:
        """
        Calculate distance between two positions using Haversine formula.

        Returns:
            Distance in meters
        """
        # Convert to radians
        lat1_rad = math.radians(pos1.latitude)
        lon1_rad = math.radians(pos1.longitude)
        lat2_rad = math.radians(pos2.latitude)
        lon2_rad = math.radians(pos2.longitude)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        # Earth's radius in meters
        earth_radius = 6371000
        distance = earth_radius * c

        return distance

    def is_position_in_zone(self, position: Position, zone: Zone) -> bool:
        """
        Check if a position is inside a zone.

        Args:
            position: Position to check
            zone: Zone to check against

        Returns:
            True if position is inside zone
        """
        zone_center = Position(zone.latitude, zone.longitude)
        distance = self.calculate_distance(position, zone_center)
        return distance <= zone.radius

    def process_position_update(self, node_id: str, position: Position) -> List[Dict[str, Any]]:
        """
        Process a position update for a node and detect zone events.

        Args:
            node_id: Node identifier
            position: New position

        Returns:
            List of triggered events
        """
        events = []

        # Store current position
        self.node_positions[node_id] = position

        # Initialize zone states for this node if not exists
        if node_id not in self.node_zone_states:
            self.node_zone_states[node_id] = {}

        # Check each active zone
        for zone in self.zones.values():
            current_in_zone = self.is_position_in_zone(position, zone)
            previous_in_zone = self.node_zone_states[node_id].get(zone.id, False)

            # Apply hysteresis to prevent oscillation
            if current_in_zone != previous_in_zone:
                # Check if we need to apply hysteresis
                hysteresis_needed = self._should_apply_hysteresis(node_id, zone, position, current_in_zone)

                if not hysteresis_needed:
                    # Zone state changed
                    event_type = 'enter' if current_in_zone else 'exit'

                    # Update state
                    self.node_zone_states[node_id][zone.id] = current_in_zone

                    # Update database
                    self._update_node_zone_state(node_id, zone.id, current_in_zone, position.timestamp)

                    # Find matching triggers
                    matching_triggers = self._find_matching_triggers(zone.id, event_type)

                    for trigger in matching_triggers:
                        event = {
                            'trigger_id': trigger.id,
                            'node_id': node_id,
                            'event_type': event_type,
                            'zone': zone,
                            'trigger': trigger,
                            'position': position
                        }
                        events.append(event)

                        # Log the trigger event
                        self._log_trigger_event(trigger, node_id, event_type, zone.name, position)

        return events

    def _should_apply_hysteresis(self, node_id: str, zone: Zone, position: Position, current_in_zone: bool) -> bool:
        """
        Determine if hysteresis should be applied to prevent trigger oscillation.

        Returns:
            True if hysteresis should be applied (ignore the state change)
        """
        # If no previous position, don't apply hysteresis
        if node_id not in self.node_positions:
            return False

        previous_position = self.node_positions[node_id]
        zone_center = Position(zone.latitude, zone.longitude)

        # Calculate distances from zone center
        prev_distance = self.calculate_distance(previous_position, zone_center)
        curr_distance = self.calculate_distance(position, zone_center)

        # If we're entering and previous position was within hysteresis distance of boundary
        if current_in_zone and prev_distance > zone.radius and prev_distance <= zone.radius + self.hysteresis_distance:
            return True

        # If we're exiting and current position is within hysteresis distance of boundary
        if not current_in_zone and curr_distance < zone.radius and curr_distance >= zone.radius - self.hysteresis_distance:
            return True

        return False

    def _update_node_zone_state(self, node_id: str, zone_id: int, is_inside: bool, timestamp: Optional[float]):
        """Update node zone state in database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            if is_inside:
                # Insert or update entry record
                cursor.execute("""
                    INSERT INTO node_zones (node_id, zone_id, entered_at, last_seen, is_currently_in)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(node_id, zone_id) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        is_currently_in = 1
                """, (node_id, zone_id, timestamp, timestamp))
            else:
                # Update exit time
                cursor.execute("""
                    UPDATE node_zones
                    SET is_currently_in = 0, last_seen = ?
                    WHERE node_id = ? AND zone_id = ?
                """, (timestamp, node_id, zone_id))

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to update node zone state: {e}")
        finally:
            conn.close()

    def _find_matching_triggers(self, zone_id: int, event_type: str) -> List[Trigger]:
        """Find triggers that match the zone and event type."""
        matching = []
        for trigger in self.triggers.values():
            if trigger.zone_id == zone_id and trigger.event_type == event_type and trigger.active:
                matching.append(trigger)
        return matching

    def _log_trigger_event(self, trigger: Trigger, node_id: str, event_type: str,
                          zone_name: str, position: Position):
        """Log trigger event to database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trigger_logs
                (trigger_id, node_id, event_type, zone_name, node_name)
                VALUES (?, ?, ?, ?, ?)
            """, (trigger.id, node_id, event_type, zone_name, node_id))

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to log trigger event: {e}")
        finally:
            conn.close()

    def get_node_current_zones(self, node_id: str) -> List[Zone]:
        """Get list of zones a node is currently in."""
        zones = []
        if node_id in self.node_zone_states:
            for zone_id, is_inside in self.node_zone_states[node_id].items():
                if is_inside and zone_id in self.zones:
                    zones.append(self.zones[zone_id])
        return zones

    def get_zone_nodes(self, zone_id: int) -> List[str]:
        """Get list of nodes currently in a zone."""
        nodes = []
        for node_id, zone_states in self.node_zone_states.items():
            if zone_states.get(zone_id, False):
                nodes.append(node_id)
        return nodes

    def cleanup_old_states(self, max_age_hours: int = 24):
        """Clean up old node zone states to prevent memory leaks."""
        cutoff_time = time.time() - (max_age_hours * 3600)

        # Remove old positions
        to_remove = []
        for node_id, position in self.node_positions.items():
            if position.timestamp and position.timestamp < cutoff_time:
                to_remove.append(node_id)

        for node_id in to_remove:
            del self.node_positions[node_id]
            if node_id in self.node_zone_states:
                del self.node_zone_states[node_id]

        logger.debug(f"Cleaned up states for {len(to_remove)} old nodes")