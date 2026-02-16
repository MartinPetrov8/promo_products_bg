#!/bin/bash
# Daily Scraper for PromoBG
# Run via cron: 0 6 * * * /path/to/daily_scrape.sh

set -e

cd /host-workspace/promo_products_bg

echo "=== PromoBG Daily Scrape $(date) ==="

# Create logs dir if needed
mkdir -p logs

# Run scraper
python3 services/scraper/run_scraper.py --output data/scraped_$(date +%Y%m%d).json 2>&1 | tee logs/scrape_$(date +%Y%m%d).log

# Run standardization
python3 standardization/cleaner_final.py 2>&1 | tee -a logs/scrape_$(date +%Y%m%d).log

# Run matcher
python3 scripts/cross_store_matcher_v7.py 2>&1 | tee -a logs/scrape_$(date +%Y%m%d).log

# Update frontend data
python3 << 'PYTHON'
import json
import hashlib
from datetime import datetime, timezone

with open('standardized_final.json') as f:
    products = json.load(f)

with open('cross_store_matches_final.json') as f:
    matches = json.load(f)['matches']

for p in products:
    p['name'] = p['clean_name']
    if p.get('discount_pct') is None:
        p['discount_pct'] = 0
    if 'group_id' in p:
        del p['group_id']

groups = {}
for i, m in enumerate(matches):
    gid = f"g_{hashlib.md5(str(i).encode()).hexdigest()[:8]}"
    p1, p2 = m['products']
    
    for p in products:
        if p['id'] == p1['id'] or p['id'] == p2['id']:
            p['group_id'] = gid
    
    prices = [p1['price'], p2['price']]
    groups[gid] = {
        'canonical_name': m.get('brand') or p1['clean_name'].split()[0],
        'brand': m.get('brand'),
        'category': m['category'],
        'product_ids': [p1['id'], p2['id']],
        'stores': m['stores'],
        'min_price': min(prices),
        'max_price': max(prices),
        'savings': round(abs(p1['price'] - p2['price']), 2)
    }

output = {
    'meta': {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'total_products': len(products),
        'cross_store_groups': len(groups),
        'total_savings': round(sum(g['savings'] for g in groups.values()), 2),
        'stores': ['Kaufland', 'Lidl', 'Billa'],
        'version': 'daily'
    },
    'products': products,
    'groups': groups,
    'off': {}
}

with open('docs/data/products.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f"✓ Frontend updated: {len(groups)} matches")
PYTHON

# Commit and push
git add -A
git commit -m "Daily update $(date +%Y-%m-%d)" || echo "No changes to commit"
git push origin main || echo "Push failed"

echo "=== Scrape complete ==="
