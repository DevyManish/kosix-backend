import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Any
import json
import os


def schema_tool(user_query: str = "") -> str:
    """
    Retrieves comprehensive PostgreSQL database schema metadata including tables, columns, 
    relationships, and query guidelines. This tool must be called before generating any SQL query.
    
    Args:
        user_query: Optional context about what the user is asking for (not required)
        
    Returns:
        JSON string containing complete database schema metadata
    """
    # Get connection string from environment variable
    connection_string = 'postgresql://neondb_owner:npg_0GWBFxyae4OM@ep-damp-dream-a1218z6h-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
    
    try:
        metadata = getMetaData(connection_string)
        return json.dumps(metadata, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Failed to retrieve schema: {str(e)}",
            "status": "error"
        })


def getMetaData(connection_string: str) -> Dict[str, Any]:
    """
    Extract comprehensive metadata from a PostgreSQL database.
    
    Args:
        connection_string: Full PostgreSQL connection string
        
    Returns:
        Dictionary containing database metadata
    """
    conn = None

    print(f"[DEBUG] : {connection_string}")

    try:
        # Connect to the database
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        metadata = {
            "database": {},
            "security": {},
            "schemas": [],
            "tables": [],
            "relationships": [],
            "business_definitions": [],
            "synonyms": {},
            "query_guidelines": {}
        }
        
        # Get database information
        metadata["database"] = _get_database_info(cursor)
        
        # Get security settings (defaults)
        metadata["security"] = _get_security_defaults()
        
        # Get all schemas (excluding system schemas)
        cursor.execute("""
            SELECT 
                schema_name,
                pg_catalog.obj_description(
                    (SELECT oid FROM pg_namespace WHERE nspname = schema_name), 
                    'pg_namespace'
                ) as description
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            AND schema_name NOT LIKE 'pg_temp_%'
            AND schema_name NOT LIKE 'pg_toast_temp_%'
            ORDER BY schema_name
        """)
        schemas_info = cursor.fetchall()
        available_schemas = []
        
        for schema_row in schemas_info:
            schema_name = schema_row['schema_name']
            available_schemas.append(schema_name)
            metadata["schemas"].append({
                "name": schema_name,
                "description": schema_row['description'] or f"Schema {schema_name}"
            })
        
        # Get all tables from all user schemas
        tables_info = _get_tables(cursor, available_schemas)
        
        for table_info in tables_info:
            table_data = {
                "schema": table_info["schema"],
                "table_name": table_info["table_name"],
                "description": table_info["description"] or f"Table {table_info['table_name']}",
                "row_count_estimate": table_info["row_count"],
                "primary_key": _get_primary_keys(cursor, table_info["schema"], table_info["table_name"]),
                "columns": _get_columns(cursor, table_info["schema"], table_info["table_name"]),
                "indexes": _get_indexes(cursor, table_info["schema"], table_info["table_name"]),
                "foreign_keys": _get_foreign_keys(cursor, table_info["schema"], table_info["table_name"])
            }
            metadata["tables"].append(table_data)
        
        # Get relationships
        metadata["relationships"] = _get_relationships(cursor)
        
        # Set default query guidelines
        metadata["query_guidelines"] = {
            "default_limit": 1000,
            "require_explicit_joins": True,
            "group_by_rules": "All non-aggregated columns must be in GROUP BY",
            "date_filter_preference": "created_at"
        }
        
        cursor.close()
        return metadata
        
    except Exception as e:
        raise Exception(f"Error extracting metadata: {str(e)}")
    finally:
        if conn:
            conn.close()


def _get_database_info(cursor) -> Dict[str, Any]:
    """Get database-level information"""
    cursor.execute("""
        SELECT 
            current_database() as name,
            version() as version,
            current_setting('TimeZone') as timezone
    """)
    result = cursor.fetchone()
    
    # Extract PostgreSQL version
    version_str = result["version"]
    version_num = version_str.split()[1].split('.')[0]
    
    return {
        "name": result["name"],
        "description": f"Primary analytics database for {result['name']}",
        "dialect": "postgresql",
        "dialect_version": version_num,
        "timezone": result["timezone"],
        "default_schema": "public"
    }


def _get_security_defaults() -> Dict[str, Any]:
    """Return default security settings"""
    return {
        "access_mode": "read_only",
        "allowed_operations": ["SELECT"],
        "blocked_operations": ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"],
        "row_limit": 1000,
        "timeout_ms": 30000,
        "pii_policy": {
            "allow_pii": False,
            "pii_columns": []
        }
    }


def _get_tables(cursor, schemas: List[str] = None) -> List[Dict[str, Any]]:
    """Get list of all tables in the database"""
    if schemas is None:
        schemas = ['public']
    
    # Create a placeholder string for the IN clause
    schema_placeholders = ','.join(['%s'] * len(schemas))
    
    query = f"""
        SELECT 
            t.table_schema as schema,
            t.table_name,
            obj_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass) as description,
            COALESCE(s.n_live_tup, 0) as row_count
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s 
            ON s.schemaname = t.table_schema 
            AND s.relname = t.table_name
        WHERE t.table_schema IN ({schema_placeholders})
        AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_schema, t.table_name
    """
    
    cursor.execute(query, tuple(schemas))
    return cursor.fetchall()


def _get_primary_keys(cursor, schema: str, table_name: str) -> List[str]:
    """Get primary key columns for a table"""
    cursor.execute("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass
        AND i.indisprimary
        ORDER BY a.attnum
    """, (f"{schema}.{table_name}",))
    
    return [row["attname"] for row in cursor.fetchall()]


def _get_columns(cursor, schema: str, table_name: str) -> List[Dict[str, Any]]:
    """Get column information for a table"""
    cursor.execute("""
        SELECT 
            c.column_name,
            c.data_type,
            c.udt_name,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.is_nullable,
            col_description((c.table_schema || '.' || c.table_name)::regclass, c.ordinal_position) as description
        FROM information_schema.columns c
        WHERE c.table_schema = %s
        AND c.table_name = %s
        ORDER BY c.ordinal_position
    """, (schema, table_name))
    
    columns = []
    for row in cursor.fetchall():
        data_type = row["data_type"].upper()
        
        # Format data type with precision/scale if applicable
        if data_type == "NUMERIC" and row["numeric_precision"]:
            data_type = f"DECIMAL({row['numeric_precision']},{row['numeric_scale']})"
        elif data_type == "CHARACTER VARYING" and row["character_maximum_length"]:
            data_type = f"VARCHAR({row['character_maximum_length']})"
        elif row["udt_name"] in ["int4", "int8"]:
            data_type = "INTEGER"
        elif row["udt_name"] == "text":
            data_type = "TEXT"
        elif row["udt_name"] == "timestamp":
            data_type = "TIMESTAMP"
        
        column = {
            "name": row["column_name"],
            "data_type": data_type,
            "nullable": row["is_nullable"] == "YES",
            "description": row["description"] or f"Column {row['column_name']}"
        }
        
        columns.append(column)
    
    return columns


def _get_indexes(cursor, schema: str, table_name: str) -> List[Dict[str, Any]]:
    """Get index information for a table"""
    cursor.execute("""
        SELECT
            i.relname as index_name,
            array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as columns,
            ix.indisunique as is_unique
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE t.relname = %s
        AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = %s)
        AND NOT ix.indisprimary
        GROUP BY i.relname, ix.indisunique
    """, (table_name, schema))
    
    indexes = []
    for row in cursor.fetchall():
        indexes.append({
            "name": row["index_name"],
            "columns": row["columns"],
            "unique": row["is_unique"]
        })
    
    return indexes


def _get_foreign_keys(cursor, schema: str, table_name: str) -> List[Dict[str, Any]]:
    """Get foreign key constraints for a table"""
    cursor.execute("""
        SELECT
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = %s
        AND tc.table_name = %s
    """, (schema, table_name))
    
    foreign_keys = []
    for row in cursor.fetchall():
        foreign_keys.append({
            "column": row["column_name"],
            "references": {
                "table": row["foreign_table_name"],
                "column": row["foreign_column_name"]
            }
        })
    
    return foreign_keys


def _get_relationships(cursor) -> List[Dict[str, Any]]:
    """Get all foreign key relationships in the database"""
    cursor.execute("""
        SELECT
            tc.table_schema,
            tc.table_name AS from_table,
            kcu.column_name AS from_column,
            ccu.table_schema AS ref_schema,
            ccu.table_name AS to_table,
            ccu.column_name AS to_column
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    """)
    
    relationships = []
    for row in cursor.fetchall():
        relationships.append({
            "from_table": row["from_table"],
            "from_column": row["from_column"],
            "to_table": row["to_table"],
            "to_column": row["to_column"],
            "relationship_type": "many_to_one",
            "description": f"Each {row['from_table']} belongs to one {row['to_table']}"
        })
    
    return relationships