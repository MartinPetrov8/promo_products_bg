#!/usr/bin/env python3
"""
Production Scraper Runner

Uses the full infrastructure with:
- Multi-tier fallback
- Circuit breakers
- Adaptive rate limiting
- Health monitoring
- Error recovery
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core import ScraperOrchestrator, ScraperTier, HealthStatus
from core.orchestrator import StoreConfig
from config import default_config, STORE_URLS

# Import scrapers
from scrapers.kaufland_scraper import scrape_kaufland
from scrapers.lidl_scraper import scrape_lidl  
from scrapers.billa_scraper import scrape_billa

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/scraper_{datetime.now():%Y%m%d}.log')
    ]
)
logger = logging.getLogger(__name__)


def alert_callback(scraper_id: str, status: str, context: dict):
    """
    Alert callback for critical issues.
    
    In production, this would send WhatsApp/Telegram alerts.
    """
    message = f"""
🚨 SCRAPER ALERT: {scraper_id}
Status: {status}
Error Rate: {context.get('error_rate', 'N/A')}
Consecutive Failures: {context.get('consecutive_failures', 0)}
Last Error: {context.get('last_error', 'N/A')}
Current Tier: {context.get('current_tier', 'N/A')}
    """.strip()
    
    logger.critical(message)
    
    # TODO: Send via OpenClaw message tool
    # For now, just log it
    print(f"\n{'='*50}")
    print(message)
    print(f"{'='*50}\n")


def create_orchestrator() -> ScraperOrchestrator:
    """Create and configure the orchestrator"""
    
    # Ensure directories exist
    Path('./data').mkdir(exist_ok=True)
    Path('./data/cache').mkdir(exist_ok=True)
    Path('./data/cookies').mkdir(exist_ok=True)
    Path('./logs').mkdir(exist_ok=True)
    
    orchestrator = ScraperOrchestrator(
        data_dir='./data',
        alert_callback=alert_callback
    )
    
    # Register Kaufland
    orchestrator.register_store(StoreConfig(
        store_id='kaufland',
        display_name='Kaufland',
        tiers=[
            ScraperTier(
                name='direct',
                scraper_func=scrape_kaufland,
                priority=1,
                description='Direct scrape from kaufland.bg'
            ),
            # TODO: Add Tier 2 aggregator scraper
        ],
        min_products=400,
    ))
    
    # Register Lidl
    orchestrator.register_store(StoreConfig(
        store_id='lidl',
        display_name='Lidl',
        tiers=[
            ScraperTier(
                name='direct',
                scraper_func=scrape_lidl,
                priority=1,
                description='Direct scrape from lidl.bg'
            ),
        ],
        min_products=20,
    ))
    
    # Register Billa
    orchestrator.register_store(StoreConfig(
        store_id='billa',
        display_name='Billa',
        tiers=[
            ScraperTier(
                name='direct',
                scraper_func=scrape_billa,
                priority=1,
                description='Direct scrape from ssbbilla.site'
            ),
        ],
        min_products=100,
    ))
    
    return orchestrator


def run_full_scrape(output_file: Optional[str] = None) -> dict:
    """Run full scrape of all stores"""
    
    logger.info("=" * 60)
    logger.info("Starting full scrape run")
    logger.info("=" * 60)
    
    orchestrator = create_orchestrator()
    
    # Scrape all stores
    results = orchestrator.scrape_all()
    
    # Combine all products
    all_products = []
    for store_id, result in results.items():
        if result.get('success'):
            products = result.get('products', [])
            all_products.extend(products)
            logger.info(
                f"✅ {store_id}: {len(products)} products "
                f"(Tier {result.get('tier_used', '?')}: {result.get('tier_name', '?')})"
            )
        else:
            logger.error(f"❌ {store_id}: FAILED - {result.get('error', 'Unknown error')}")
    
    # Save combined results
    output_path = output_file or f'./data/all_products.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(all_products)} products to {output_path}")
    
    # Print health summary
    print("\n" + orchestrator.get_health_summary())
    
    # Return summary
    return {
        'total_products': len(all_products),
        'stores': {
            store_id: {
                'success': r.get('success'),
                'products': len(r.get('products', [])),
                'tier': r.get('tier_name'),
                'from_cache': r.get('from_cache', False),
            }
            for store_id, r in results.items()
        },
        'output_file': output_path,
    }


def run_single_store(store_id: str) -> dict:
    """Run scrape for a single store"""
    
    logger.info(f"Scraping single store: {store_id}")
    
    orchestrator = create_orchestrator()
    
    if store_id not in orchestrator.store_configs:
        logger.error(f"Unknown store: {store_id}")
        return {'success': False, 'error': f'Unknown store: {store_id}'}
    
    result = orchestrator.scrape_store(store_id)
    
    if result.get('success'):
        products = result.get('products', [])
        output_path = f'./data/{store_id}_products.json'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ {store_id}: {len(products)} products saved to {output_path}")
    else:
        logger.error(f"❌ {store_id}: FAILED")
    
    return result


def show_health():
    """Show health status of all scrapers"""
    orchestrator = create_orchestrator()
    
    # We need some data to show health
    print("\n📊 Scraper Health Report")
    print("=" * 50)
    
    report = orchestrator.get_health_report()
    
    print(json.dumps(report, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description='Production Scraper Runner')
    parser.add_argument(
        '--store',
        type=str,
        help='Scrape single store (kaufland, lidl, billa)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path'
    )
    parser.add_argument(
        '--health',
        action='store_true',
        help='Show health status'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.health:
        show_health()
    elif args.store:
        result = run_single_store(args.store)
        print(json.dumps(result, indent=2, default=str))
    else:
        result = run_full_scrape(args.output)
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
