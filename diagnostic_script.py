#!/usr/bin/env python3
"""
Diagnostic script to identify invalid timeout_minutes settings in the database.
"""

import sqlite3
import sys
import os

def check_database_settings():
    """Check current database settings for timeout-related issues."""
    db_path = '/home/al/code/ff-bbs/webui/dashboard.db'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check all timeout-related settings
    cursor.execute("SELECT key, value, description FROM settings WHERE key LIKE '%timeout%'")
    timeout_settings = cursor.fetchall()
    
    print("=== TIMEOUT-RELATED SETTINGS ===")
    for key, value, description in timeout_settings:
        print(f"Key: {key}")
        print(f"Value: '{value}'")
        print(f"Description: {description}")
        print(f"Type: {type(value)}")
        
        # Test if the value can be converted to int
        try:
            int_val = int(value)
            print(f"✓ Valid integer: {int_val}")
        except (ValueError, TypeError) as e:
            print(f"✗ Invalid integer: {e}")
        print("-" * 50)
    
    # Check all settings
    cursor.execute("SELECT key, value FROM settings")
    all_settings = cursor.fetchall()
    
    print(f"\n=== ALL SETTINGS ({len(all_settings)} total) ===")
    for key, value in all_settings:
        if 'timeout' in key.lower() or 'node' in key.lower():
            print(f"{key}: '{value}'")
    
    # Check if the problematic setting exists
    cursor.execute("SELECT key, value FROM settings WHERE key = 'node.inactivity_timeout_minutes'")
    result = cursor.fetchone()
    
    if result:
        key, value = result
        print(f"\n=== PROBLEMATIC SETTING FOUND ===")
        print(f"Key: {key}")
        print(f"Value: '{value}'")
        print(f"Can be converted to int? ", end="")
        try:
            int(value)
            print("Yes")
        except (ValueError, TypeError):
            print("No - THIS IS THE PROBLEM!")
    else:
        print("\n=== SETTING NOT FOUND ===")
        print("The 'node.inactivity_timeout_minutes' setting doesn't exist in the database")
    
    conn.close()

if __name__ == '__main__':
    check_database_settings()