import sqlite3
import json
import sys

def inspect_schema(db_path):
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
        create_sql = cursor.fetchone()
        create_sql = create_sql[0] if create_sql else None

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

def compare_schemas(schema1, schema2):
    differences = {
        'missing_tables_in_2': [],
        'extra_tables_in_2': [],
        'table_differences': {}
    }

    tables1 = set(schema1.keys())
    tables2 = set(schema2.keys())

    # Tables missing in schema2
    missing_in_2 = tables1 - tables2
    differences['missing_tables_in_2'] = list(missing_in_2)

    # Extra tables in schema2
    extra_in_2 = tables2 - tables1
    differences['extra_tables_in_2'] = list(extra_in_2)

    # Compare common tables
    common_tables = tables1 & tables2
    for table in common_tables:
        table_diff = compare_table(schema1[table], schema2[table])
        if table_diff:
            differences['table_differences'][table] = table_diff

    return differences

def compare_table(table1, table2):
    differences = {}

    # Compare columns
    columns1 = {col[1]: col for col in table1['columns']}  # col[1] is column name
    columns2 = {col[1]: col for col in table2['columns']}

    missing_cols_in_2 = set(columns1.keys()) - set(columns2.keys())
    extra_cols_in_2 = set(columns2.keys()) - set(columns1.keys())

    if missing_cols_in_2:
        differences['missing_columns'] = list(missing_cols_in_2)
    if extra_cols_in_2:
        differences['extra_columns'] = list(extra_cols_in_2)

    # Compare column definitions for common columns
    common_cols = set(columns1.keys()) & set(columns2.keys())
    col_diffs = {}
    for col in common_cols:
        if columns1[col] != columns2[col]:
            col_diffs[col] = {
                'schema1': columns1[col],
                'schema2': columns2[col]
            }
    if col_diffs:
        differences['column_differences'] = col_diffs

    # Compare create SQL
    if table1['create_sql'] != table2['create_sql']:
        differences['create_sql_diff'] = {
            'schema1': table1['create_sql'],
            'schema2': table2['create_sql']
        }

    # Compare indexes
    indexes1 = {idx[0]: idx for idx in table1['indexes']}
    indexes2 = {idx[0]: idx for idx in table2['indexes']}

    missing_idx_in_2 = set(indexes1.keys()) - set(indexes2.keys())
    extra_idx_in_2 = set(indexes2.keys()) - set(indexes1.keys())

    if missing_idx_in_2:
        differences['missing_indexes'] = list(missing_idx_in_2)
    if extra_idx_in_2:
        differences['extra_indexes'] = list(extra_idx_in_2)

    # Compare index definitions for common indexes
    common_idx = set(indexes1.keys()) & set(indexes2.keys())
    idx_diffs = {}
    for idx in common_idx:
        if indexes1[idx] != indexes2[idx]:
            idx_diffs[idx] = {
                'schema1': indexes1[idx],
                'schema2': indexes2[idx]
            }
    if idx_diffs:
        differences['index_differences'] = idx_diffs

    return differences

def compare_data(db1_path, db2_path):
    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    # Get all tables
    cursor1.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables1 = {row[0] for row in cursor1.fetchall()}

    cursor2.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables2 = {row[0] for row in cursor2.fetchall()}

    common_tables = tables1 & tables2

    data_differences = {}

    for table in common_tables:
        cursor1.execute(f"SELECT COUNT(*) FROM {table}")
        count1 = cursor1.fetchone()[0]

        cursor2.execute(f"SELECT COUNT(*) FROM {table}")
        count2 = cursor2.fetchone()[0]

        if count1 != count2:
            data_differences[table] = {
                'count_schema1': count1,
                'count_schema2': count2
            }

    conn1.close()
    conn2.close()

    return data_differences

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python inspect_schema.py <db1_path> <db2_path>")
        sys.exit(1)

    db1_path = sys.argv[1]
    db2_path = sys.argv[2]

    schema1 = inspect_schema(db1_path)
    schema2 = inspect_schema(db2_path)

    schema_diff = compare_schemas(schema1, schema2)
    data_diff = compare_data(db1_path, db2_path)

    report = {
        'schema_differences': schema_diff,
        'data_differences': data_diff
    }

    print(json.dumps(report, indent=2, default=str))