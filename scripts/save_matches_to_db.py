#!/usr/bin/env python3
"""Save matches from JSON to database"""

import sqlite3
import json
from datetime import datetime

DB_PATH = 'data/promobg.db'
MATCHES_FILE = 'cross_store_matches_final.json'

def save_matches():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Load matches
    with open(MATCHES_FILE) as f:
        data = json.load(f)
    
    # Clear existing matches
    cur.execute('DELETE FROM cross_store_matches')
    
    # Insert new matches
    for match in data['matches']:
        p1, p2 = match['products'][0], match['products'][1]
        
        kaufland_id = None
        lidl_id = None
        billa_id = None
        
        for p in match['products']:
            if p['store'] == 'Kaufland':
                kaufland_id = p['id']
            elif p['store'] == 'Lidl':
                lidl_id = p['id']
            elif p['store'] == 'Billa':
                billa_id = p['id']
        
        cur.execute('''
            INSERT INTO cross_store_matches (
                kaufland_product_id, lidl_product_id, billa_product_id,
                canonical_name, canonical_brand,
                match_type, confidence, store_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            kaufland_id, lidl_id, billa_id,
            match.get('common_words', p1['clean_name']),
            match.get('brand'),
            'name_similarity',
            0.9,
            2
        ))
    
    conn.commit()
    
    # Verify
    cur.execute('SELECT COUNT(*) FROM cross_store_matches')
    print(f"Saved {cur.fetchone()[0]} matches to database")
    
    conn.close()

if __name__ == '__main__':
    save_matches()
