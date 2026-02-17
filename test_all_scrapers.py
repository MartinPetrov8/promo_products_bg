#!/usr/bin/env python3
"""
Test all 3 scrapers and generate comprehensive report
"""
import sys
import logging
from scrapers.kaufland.scraper import KauflandScraper
from scrapers.billa.scraper import BillaScraper
from scrapers.lidl.scraper import LidlScraper

logging.basicConfig(level=logging.INFO)

def analyze_products(products, store_name):
    """Generate statistics for a list of products."""
    total = len(products)
    
    with_brand = sum(1 for p in products if p.brand)
    with_qty = sum(1 for p in products if p.quantity_value)
    with_desc = sum(1 for p in products if p.raw_description)
    with_old = sum(1 for p in products if p.old_price_bgn)
    with_disc = sum(1 for p in products if p.discount_pct)
    
    return {
        'store': store_name,
        'total': total,
        'brand_count': with_brand,
        'brand_pct': 100 * with_brand / total if total > 0 else 0,
        'quantity_count': with_qty,
        'quantity_pct': 100 * with_qty / total if total > 0 else 0,
        'description_count': with_desc,
        'description_pct': 100 * with_desc / total if total > 0 else 0,
        'old_price_count': with_old,
        'old_price_pct': 100 * with_old / total if total > 0 else 0,
        'discount_count': with_disc,
        'discount_pct': 100 * with_disc / total if total > 0 else 0,
        'products': products
    }

def print_report(stats_list):
    """Print comprehensive report."""
    print("\n" + "="*80)
    print("SCRAPER IMPROVEMENT TEST RESULTS")
    print("="*80)
    
    # Summary table
    print(f"\n{'Store':<15} {'Products':>10} {'Brand %':>10} {'Qty %':>10} {'Desc %':>10} {'Old Price %':>12} {'Discount %':>12}")
    print("-"*80)
    
    for stats in stats_list:
        print(f"{stats['store']:<15} "
              f"{stats['total']:>10} "
              f"{stats['brand_pct']:>9.1f}% "
              f"{stats['quantity_pct']:>9.1f}% "
              f"{stats['description_pct']:>9.1f}% "
              f"{stats['old_price_pct']:>11.1f}% "
              f"{stats['discount_pct']:>11.1f}%")
    
    # Detailed samples
    for stats in stats_list:
        print("\n" + "="*80)
        print(f"{stats['store']} - SAMPLE PRODUCTS (first 5)")
        print("="*80)
        
        for i, p in enumerate(stats['products'][:5], 1):
            qty = f"{p.quantity_value} {p.quantity_unit}" if p.quantity_value else '-'
            old = f"(was {p.old_price_bgn:.2f})" if p.old_price_bgn else ''
            disc = f"-{p.discount_pct}%" if p.discount_pct else ''
            brand = p.brand or '-'
            desc = (p.raw_description[:50] + '...') if p.raw_description and len(p.raw_description) > 50 else (p.raw_description or '-')
            
            print(f"\n[{i}] {p.raw_name}")
            print(f"    Brand:       {brand}")
            print(f"    Price:       {p.price_bgn:.2f}лв {old} {disc}")
            print(f"    Quantity:    {qty}")
            print(f"    Description: {desc}")

def main():
    results = []
    
    print("Testing Kaufland scraper...")
    kaufland = KauflandScraper()
    kaufland_products = kaufland.scrape()
    results.append(analyze_products(kaufland_products, "Kaufland"))
    
    print("\nTesting Billa scraper...")
    billa = BillaScraper()
    billa_products = billa.scrape()
    results.append(analyze_products(billa_products, "Billa"))
    
    print("\nTesting Lidl scraper...")
    lidl = LidlScraper()
    lidl_products = lidl.scrape()
    results.append(analyze_products(lidl_products, "Lidl"))
    
    print_report(results)

if __name__ == '__main__':
    main()
