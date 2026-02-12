#!/usr/bin/env python3
"""
Initialize the PromoBG database.

Usage:
    python init_db.py              # Initialize with default path
    python init_db.py --path /custom/path/db.sqlite
    python init_db.py --check      # Just check health
    python init_db.py --cleanup    # Clean old data
"""

import argparse
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.database.db import Database, get_db, DEFAULT_DB_PATH
from services.database.monitor import DatabaseMonitor


def main():
    parser = argparse.ArgumentParser(description='Initialize PromoBG database')
    parser.add_argument('--path', type=str, help='Custom database path')
    parser.add_argument('--check', action='store_true', help='Check database health')
    parser.add_argument('--cleanup', action='store_true', help='Clean old data')
    parser.add_argument('--days', type=int, default=90, help='Days to keep for cleanup')
    
    args = parser.parse_args()
    
    # Get or create database
    db_path = args.path or str(DEFAULT_DB_PATH)
    print(f"Database path: {db_path}")
    
    db = Database(db_path)
    
    if args.check:
        # Just check health
        monitor = DatabaseMonitor(db)
        print(monitor.get_summary())
        return
    
    if args.cleanup:
        # Clean old data
        monitor = DatabaseMonitor(db)
        print(f"Cleaning data older than {args.days} days...")
        results = monitor.cleanup_old_data(days_to_keep=args.days)
        print(f"Deleted: {results}")
        print(monitor.get_summary())
        return
    
    # Initialize schema
    print("Initializing database schema...")
    db.init_schema()
    
    # Check health
    monitor = DatabaseMonitor(db)
    print("\n" + monitor.get_summary())
    
    print("\n✅ Database initialized successfully!")
    print(f"   Path: {db_path}")
    print(f"   Size: {db.get_size_mb():.2f} MB")


if __name__ == '__main__':
    main()
