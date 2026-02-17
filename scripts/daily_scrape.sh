#!/bin/bash
# Daily Scraper for PromoBG (v2 - Pipeline Based)
# Run via cron: 0 6 * * * /path/to/daily_scrape.sh

set -e

cd /host-workspace/promo_products_bg

echo "=== PromoBG Daily Scrape $(date) ==="

# Create dirs if needed
mkdir -p logs raw_scrapes

# Run the pipeline (daily = sync + match + export, no scrape)
# Use --full to include scraping
python3 scripts/pipeline.py --daily 2>&1 | tee logs/scrape_$(date +%Y%m%d).log

# Commit and push
git add -A
git commit -m "Daily update $(date +%Y-%m-%d)" || echo "No changes to commit"
git push origin main || echo "Push failed"

echo "=== Scrape complete ==="
