import sqlite3
import json

def inspect_schema(db_path='webui/dashboard.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    schema = {}
    
    for table in tables:
        table_name = table[0]
        
        # Get table info (columns)
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        # Get create statement
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        create_sql = cursor.fetchone()[0]
        
        # Get indexes
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?", (table_name,))
        indexes = cursor.fetchall()
        
        schema[table_name] = {
            'columns': columns,
            'create_sql': create_sql,
            'indexes': indexes
        }
    
    conn.close()
    return schema

if __name__ == '__main__':
    schema = inspect_schema()
    print(json.dumps(schema, indent=2, default=str))