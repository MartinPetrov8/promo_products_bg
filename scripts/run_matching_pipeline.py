#!/usr/bin/env python3
"""
Full Matching Pipeline Runner
Runs all phases: Token → Transliteration → Embeddings
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

def run_script(name):
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print('='*60 + "\n")
    
    result = subprocess.run(
        [sys.executable, SCRIPTS_DIR / name],
        capture_output=False
    )
    return result.returncode == 0

def get_match_stats():
    import sqlite3
    conn = sqlite3.connect(SCRIPTS_DIR.parent / "data/promobg.db")
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM store_products WHERE deleted_at IS NULL')
    total = cur.fetchone()[0]
    
    cur.execute('SELECT match_type, COUNT(*) FROM product_off_matches GROUP BY match_type')
    by_type = dict(cur.fetchall())
    
    cur.execute('SELECT COUNT(*) FROM product_off_matches')
    matched = cur.fetchone()[0]
    
    conn.close()
    return total, matched, by_type

def main():
    print("=" * 60)
    print("FULL MATCHING PIPELINE")
    print("=" * 60)
    
    # Get initial stats
    total, matched_before, _ = get_match_stats()
    print(f"\nInitial state: {matched_before}/{total} matched ({matched_before/total*100:.1f}%)")
    
    # Phase 1: Transliteration
    if not run_script("phase1_transliteration.py"):
        print("Phase 1 failed!")
        return
    
    # Phase 2: Embeddings
    if not run_script("phase2_embeddings.py"):
        print("Phase 2 failed!")
        return
    
    # Final stats
    total, matched_after, by_type = get_match_stats()
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"\nTotal products: {total}")
    print(f"Matched before: {matched_before} ({matched_before/total*100:.1f}%)")
    print(f"Matched after:  {matched_after} ({matched_after/total*100:.1f}%)")
    print(f"New matches:    {matched_after - matched_before}")
    
    print("\nBreakdown by type:")
    for match_type, count in sorted(by_type.items()):
        print(f"  {match_type}: {count}")
    
    print("\n✓ Pipeline complete!")

if __name__ == '__main__':
    main()
