#!/usr/bin/env python3
"""
Database migration script for Kingdom Auto Finance.
Executes SQL migrations with safety checks.

Usage:
    python backend/migrations/run_migration.py

Requirements:
    pip install psycopg2-binary (or psycopg2)
"""
import os
import sys
from pathlib import Path
from typing import Optional

# Add parent directories to path for imports
script_dir = Path(__file__).parent
backend_dir = script_dir.parent
root_dir = backend_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(root_dir))

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("✗ Error: psycopg2 is not installed")
    print("  Please install it: pip install psycopg2-binary")
    sys.exit(1)


def get_connection_string() -> str:
    """Build PostgreSQL connection string from Supabase URL."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_password = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_PASSWORD")
    
    if not supabase_url:
        raise ValueError(
            "Missing required environment variable: SUPABASE_URL\n"
            "Example: https://puwcyhbjchkfvvaccacg.supabase.co"
        )
    
    # Extract project ID from Supabase URL
    # Format: https://{project_id}.supabase.co
    project_id = supabase_url.replace("https://", "").replace("http://", "").split(".")[0]
    
    # Supabase PostgreSQL connection details
    # Format: postgresql://postgres:[password]@db.{project_id}.supabase.co:5432/postgres
    db_host = f"db.{project_id}.supabase.co"
    db_port = 5432
    db_name = "postgres"
    db_user = "postgres"
    
    # Get password from environment
    db_password = os.getenv("SUPABASE_DB_PASSWORD")
    
    if not db_password:
        print("\n⚠️  WARNING: SUPABASE_DB_PASSWORD not set!")
        print("   This is your database password, not the service role key.")
        print("   Find it in: Supabase Dashboard → Settings → Database → Connection String")
        print("\n   For now, the migration SQL will be displayed for manual execution.")
        return None
    
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def get_connection():
    """Create PostgreSQL connection."""
    conn_string = get_connection_string()
    
    if not conn_string:
        return None
    
    try:
        conn = psycopg2.connect(conn_string)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except psycopg2.Error as e:
        print(f"✗ Failed to connect to database: {e}")
        return None


def check_table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (table_name,))
        return cursor.fetchone()[0]
    except Exception:
        return False


def run_migration(sql_file: Path) -> None:
    """Execute SQL migration file."""
    print(f"🚀 Starting migration: {sql_file.name}")
    print("=" * 60)
    
    # Read SQL file
    if not sql_file.exists():
        raise FileNotFoundError(f"Migration file not found: {sql_file}")
    
    sql_content = sql_file.read_text()
    print(f"✓ Loaded migration file ({len(sql_content)} bytes)")
    
    # Get database connection
    try:
        conn = get_connection()
        if not conn:
            # No connection available, show manual instructions
            print("\n📋 Manual Migration Required")
            print("=" * 60)
            print("\nCopy the following SQL and paste it into:")
            print("Supabase Dashboard → SQL Editor → New Query\n")
            print("-" * 60)
            print(sql_content)
            print("-" * 60)
            print("\nOr run this file directly:")
            print(f"  {sql_file.absolute()}")
            return
        
        cursor = conn.cursor()
        print("✓ Connected to PostgreSQL database")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Check existing tables
    print("\n📊 Checking existing tables...")
    tables_to_check = ["users", "audit_log", "jobs"]
    existing_tables = []
    
    for table in tables_to_check:
        exists = check_table_exists(cursor, table)
        status = "EXISTS" if exists else "NOT FOUND"
        print(f"  - {table}: {status}")
        if exists:
            existing_tables.append(table)
    
    if len(existing_tables) == len(tables_to_check):
        print("\n✅ All tables already exist! No migration needed.")
        cursor.close()
        conn.close()
        return
    
    # Execute migration
    print(f"\n⚙️  Executing migration SQL...")
    print("  (This will create missing tables and indexes)")
    
    try:
        # Execute the entire SQL file
        cursor.execute(sql_content)
        
        print(f"\n✓ Migration completed!")
        
    except psycopg2.Error as e:
        print(f"\n✗ Migration failed: {e}")
        cursor.close()
        conn.close()
        sys.exit(1)
    
    # Verify tables exist after migration
    print("\n✅ Verifying tables after migration...")
    all_exist = True
    for table in tables_to_check:
        exists = check_table_exists(cursor, table)
        status = "✓" if exists else "✗"
        print(f"  {status} {table}")
        if not exists:
            all_exist = False
    
    cursor.close()
    conn.close()
    
    if all_exist:
        print("\n🎉 Migration successful! All tables are ready.")
        print("\n📝 Default Admin Account:")
        print("   Email: admin@kingdomautofinance.com")
        print("   Password: Kingdom2025!$$")
        print("   ⚠️  CHANGE THIS PASSWORD AFTER FIRST LOGIN!")
    else:
        print("\n⚠️  Warning: Some tables were not created.")
    
    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    sql_file = Path(__file__).parent / "001_initial_tables.sql"
    
    try:
        run_migration(sql_file)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
