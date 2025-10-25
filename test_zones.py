#!/usr/bin/env python3
"""
Test script for zone creation and updating functionality.
"""
import sys
import os
sys.path.append('webui')

# Import functions directly to avoid relative import issues
import sqlite3
import json
import time
import logging
import functools

# Copy the necessary functions from db_handler.py
def get_db_connection(db_name='dashboard.db'):
    """Get database connection with WAL mode ensured."""
    db_path = os.path.join('webui', db_name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # Ensure WAL mode is set on every connection
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    journal_mode = cursor.fetchone()[0]
    if journal_mode != 'wal':
        print(f"Failed to set WAL mode on {db_name}, current mode: {journal_mode}")
    return conn

def create_zone(name, latitude, longitude, radius, description='', active=1):
    """Create a new geo-zone."""
    conn = get_db_connection()
    try:
        # Convert boolean to integer if necessary
        if isinstance(active, bool):
            active = 1 if active else 0
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO zones (name, latitude, longitude, radius, description, active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, latitude, longitude, radius, description, active)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_zone(zone_id, name=None, latitude=None, longitude=None, radius=None, description=None, active=None):
    """Update a zone."""
    conn = get_db_connection()
    try:
        if not any([name, latitude, longitude, radius, description, active is not None]):
            return False

        set_parts = []
        values = []
        if name is not None:
            set_parts.append("name = ?")
            values.append(name)
        if latitude is not None:
            set_parts.append("latitude = ?")
            values.append(latitude)
        if longitude is not None:
            set_parts.append("longitude = ?")
            values.append(longitude)
        if radius is not None:
            set_parts.append("radius = ?")
            values.append(radius)
        if description is not None:
            set_parts.append("description = ?")
            values.append(description)
        if active is not None:
            set_parts.append("active = ?")
            values.append(1 if active else 0)

        values.append(zone_id)
        query = f"UPDATE zones SET {', '.join(set_parts)} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_zones():
    """Get all geo-zones."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM zones ORDER BY name")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        zones = [dict(zip(columns, row)) for row in rows]
        return zones
    finally:
        conn.close()

def get_zone(zone_id):
    """Get a single zone by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM zones WHERE id = ?", (zone_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def delete_zone(zone_id):
    """Delete a zone."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # First check if zone exists
        cursor.execute("SELECT id FROM zones WHERE id = ?", (zone_id,))
        if not cursor.fetchone():
            return False

        cursor.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def check_db_directly():
    """Check zones table directly in database."""
    conn = sqlite3.connect('webui/dashboard.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, latitude, longitude, radius, active, created_at, updated_at FROM zones ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print("\n=== Database Direct Check ===")
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}, Desc: {row[2]}, Lat: {row[3]}, Lng: {row[4]}, Radius: {row[5]}, Active: {row[6]}, Created: {row[7]}, Updated: {row[8]}")
    conn.close()

def main():
    print("Testing zone creation and updating functionality...")

    # Test 1: Create a test zone
    print("\n=== Test 1: Creating test zone ===")
    zone_id = create_zone(
        name="Test Zone",
        latitude=55.7558,
        longitude=37.6173,
        radius=500,
        description="Test zone for debugging",
        active=True
    )
    print(f"Created zone with ID: {zone_id}")

    # Verify creation
    zone = get_zone(zone_id)
    print(f"Retrieved zone: {zone}")

    # Check database directly
    check_db_directly()

    # Test 2: Update the zone
    print("\n=== Test 2: Updating test zone ===")
    success = update_zone(
        zone_id=zone_id,
        name="Updated Test Zone",
        latitude=55.7559,
        longitude=37.6174,
        radius=1000,
        description="Updated test zone",
        active=False
    )
    print(f"Update success: {success}")

    # Verify update
    zone = get_zone(zone_id)
    print(f"Retrieved updated zone: {zone}")

    # Check database directly
    check_db_directly()

    # Test 3: Toggle active status
    print("\n=== Test 3: Toggling active status ===")
    success = update_zone(zone_id=zone_id, active=True)
    print(f"Toggle active success: {success}")

    # Verify toggle
    zone = get_zone(zone_id)
    print(f"Retrieved zone after toggle: {zone}")

    # Check database directly
    check_db_directly()

    # Test 4: Get all zones
    print("\n=== Test 4: Getting all zones ===")
    all_zones = get_zones()
    print(f"All zones count: {len(all_zones)}")
    for z in all_zones[-3:]:  # Show last 3 zones
        print(f"Zone: {z}")

    # Cleanup
    print("\n=== Cleanup: Deleting test zone ===")
    success = delete_zone(zone_id)
    print(f"Delete success: {success}")

    # Final check
    check_db_directly()

    print("\n=== Test completed ===")

if __name__ == "__main__":
    main()