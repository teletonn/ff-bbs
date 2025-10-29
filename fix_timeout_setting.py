#!/usr/bin/env python3
"""
Fix script to correct the invalid timeout_minutes setting in the database.
"""

import sqlite3
import sys
import os

def fix_timeout_setting():
    """Fix the invalid timeout_minutes setting in the database."""
    db_path = '/home/al/code/ff-bbs/webui/dashboard.db'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current value
    cursor.execute("SELECT key, value, description FROM settings WHERE key = 'node.inactivity_timeout_minutes'")
    result = cursor.fetchone()
    
    if result:
        key, value, description = result
        print(f"Found problematic setting:")
        print(f"  Key: {key}")
        print(f"  Current Value: '{value}'")
        print(f"  Description: {description}")
        
        # Check if value is invalid
        try:
            int(value)
            print("✓ Setting is already valid")
            return True
        except (ValueError, TypeError):
            print("✗ Setting is invalid, fixing...")
            
            # Fix the setting with a proper default value
            cursor.execute("""
                UPDATE settings 
                SET value = ?, description = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE key = ?
            """, ('30', 'Timeout in minutes for node offline detection', key))
            
            if cursor.rowcount > 0:
                print("✓ Successfully updated setting to valid value '30'")
                conn.commit()
                return True
            else:
                print("✗ Failed to update setting")
                return False
    else:
        print("Setting 'node.inactivity_timeout_minutes' not found in database")
        print("This is normal for a fresh installation")
        return True
    
    conn.close()

if __name__ == '__main__':
    print("=== TIMEOUT SETTING FIX ===")
    success = fix_timeout_setting()
    if success:
        print("\n=== FIX COMPLETED SUCCESSFULLY ===")
        print("The timeout setting has been corrected.")
        print("The application should no longer show timeout parsing warnings.")
    else:
        print("\n=== FIX FAILED ===")
        print("There was an issue fixing the timeout setting.")
    sys.exit(0 if success else 1)