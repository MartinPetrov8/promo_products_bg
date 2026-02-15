"""
Product Processor

Main orchestrator that transforms raw product data into StandardProduct.
Combines brand extraction, quantity parsing, and name normalization.

Usage:
    processor = ProductProcessor()
    
    # Transform single product
    product = processor.transform(raw_data, store="Billa")
    
    # Apply fixes to existing database
    processor.apply_fixes_to_database(db_path)
"""

import sqlite3
from typing import Dict, Any, Optional, Iterator, List
from decimal import Decimal
from datetime import datetime

from .schema import StandardProduct
from .brand_extractor import extract_brand, is_house_brand
from .quantity_parser import parse_quantity
from .name_normalizer import clean_name, normalize_name


class ProductProcessor:
    """
    Processes raw product data into standardized format.
    
    Handles store-specific transformations and applies all
    standardization modules in the correct order.
    """
    
    def __init__(self):
        self.stats = {
            'processed': 0,
            'brands_extracted': 0,
            'quantities_parsed': 0,
            'names_cleaned': 0,
            'errors': 0,
        }
    
    def transform(
        self,
        raw_data: Dict[str, Any],
        store: str,
        store_product_id: Optional[str] = None
    ) -> StandardProduct:
        """
        Transform raw product data into StandardProduct.
        
        Args:
            raw_data: Raw product data from scraper
            store: Store name ("Kaufland", "Lidl", "Billa")
            store_product_id: Override product ID if not in raw_data
            
        Returns:
            Standardized product
        """
        self.stats['processed'] += 1
        
        # Get raw values
        raw_name = raw_data.get('name', '')
        raw_brand = raw_data.get('brand')
        raw_unit = raw_data.get('unit', '')
        raw_quantity = raw_data.get('quantity')
        raw_price = raw_data.get('price')
        raw_old_price = raw_data.get('old_price') or raw_data.get('originalPrice')
        
        # Step 1: Clean name (remove prefixes, HTML, etc.)
        cleaned_name = clean_name(raw_name, store)
        if cleaned_name != raw_name:
            self.stats['names_cleaned'] += 1
        
        # Step 2: Extract brand if not provided
        brand = raw_brand
        if not brand or brand.strip() == '':
            brand = extract_brand(cleaned_name, store)
            if brand:
                self.stats['brands_extracted'] += 1
        
        # Step 3: Parse quantity
        quantity_value = raw_quantity
        quantity_unit = raw_unit
        
        if not quantity_value or (raw_unit and '<' in raw_unit):
            # Parse from name + unit field
            text = f"{cleaned_name} {raw_unit}"
            parsed_qty, parsed_unit = parse_quantity(text)
            if parsed_qty:
                quantity_value = parsed_qty
                quantity_unit = parsed_unit
                self.stats['quantities_parsed'] += 1
        
        # Step 4: Create normalized name
        normalized = normalize_name(cleaned_name)
        
        # Step 5: Parse price
        price = None
        if raw_price:
            try:
                price = Decimal(str(raw_price))
            except:
                pass
        
        old_price = None
        if raw_old_price:
            try:
                old_price = Decimal(str(raw_old_price))
            except:
                pass
        
        # Step 6: Determine if house brand
        is_house = is_house_brand(brand, store) if brand else False
        
        # Step 7: Create StandardProduct
        product = StandardProduct(
            store=store,
            store_product_id=store_product_id or raw_data.get('id', ''),
            name=cleaned_name,
            normalized_name=normalized,
            brand=brand,
            is_house_brand=is_house,
            quantity_value=quantity_value,
            quantity_unit=quantity_unit,
            price=price,
            old_price=old_price,
            image_url=raw_data.get('image') or raw_data.get('imageUrl'),
            barcode=raw_data.get('barcode') or raw_data.get('ean'),
            raw_data=raw_data,
        )
        
        return product
    
    def transform_batch(
        self,
        raw_products: List[Dict[str, Any]],
        store: str
    ) -> Iterator[StandardProduct]:
        """
        Transform multiple products.
        
        Args:
            raw_products: List of raw product data
            store: Store name
            
        Yields:
            StandardProduct instances
        """
        for raw in raw_products:
            try:
                yield self.transform(raw, store)
            except Exception as e:
                self.stats['errors'] += 1
                print(f"Error processing product: {e}")
                continue
    
    def apply_fixes_to_database(
        self,
        db_path: str,
        dry_run: bool = False
    ) -> Dict[str, int]:
        """
        Apply standardization fixes to existing database.
        
        Updates:
        - normalized_name (for Billa: strip prefixes)
        - brand (extract from names where missing)
        - quantity/unit (re-parse where HTML present)
        
        Args:
            db_path: Path to SQLite database
            dry_run: If True, don't commit changes
            
        Returns:
            Dictionary of update counts per store
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        stats = {store: {'brand_added': 0, 'qty_fixed': 0, 'name_cleaned': 0}
                 for store in ['Kaufland', 'Lidl', 'Billa']}
        
        for store in ['Kaufland', 'Lidl', 'Billa']:
            print(f"\nProcessing {store}...")
            
            # Get products for this store
            cur.execute("""
                SELECT p.id, p.name, p.brand, p.quantity, p.unit, p.normalized_name
                FROM products p
                JOIN store_products sp ON p.id = sp.product_id
                JOIN stores s ON sp.store_id = s.id
                WHERE s.name = ? AND sp.deleted_at IS NULL
            """, (store,))
            
            for row in cur.fetchall():
                updates = []
                params = []
                
                original_name = row['name']
                cleaned = clean_name(original_name, store)
                
                # Update normalized_name if we cleaned it
                if cleaned != original_name:
                    norm = normalize_name(cleaned)
                    updates.append("normalized_name = ?")
                    params.append(norm)
                    stats[store]['name_cleaned'] += 1
                
                # Add brand if missing
                if not row['brand'] or row['brand'].strip() == '':
                    brand = extract_brand(cleaned, store)
                    if brand:
                        updates.append("brand = ?")
                        params.append(brand)
                        stats[store]['brand_added'] += 1
                
                # Fix quantity if missing or has HTML
                unit = row['unit'] or ''
                if not row['quantity'] or '<' in unit:
                    text = cleaned + ' ' + unit
                    qty, parsed_unit = parse_quantity(text)
                    if qty and qty < 100000:  # Sanity check
                        updates.append("quantity = ?")
                        params.append(qty)
                        updates.append("unit = ?")
                        params.append(parsed_unit)
                        stats[store]['qty_fixed'] += 1
                
                # Apply updates
                if updates and not dry_run:
                    params.append(row['id'])
                    sql = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"
                    cur.execute(sql, params)
            
            print(f"  ✓ {store}: {sum(stats[store].values())} updates")
        
        if not dry_run:
            conn.commit()
        
        conn.close()
        return stats
    
    def get_stats(self) -> Dict[str, int]:
        """Return processing statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset processing statistics."""
        self.stats = {
            'processed': 0,
            'brands_extracted': 0,
            'quantities_parsed': 0,
            'names_cleaned': 0,
            'errors': 0,
        }


# === Convenience Functions ===

def standardize_product(
    raw_data: Dict[str, Any],
    store: str
) -> StandardProduct:
    """
    Convenience function to standardize a single product.
    
    Example:
        product = standardize_product({
            'name': 'King оферта - Hochland сирене 200г',
            'price': 3.99
        }, store='Billa')
    """
    processor = ProductProcessor()
    return processor.transform(raw_data, store)


# === Testing ===
if __name__ == "__main__":
    print("ProductProcessor Tests:")
    print("=" * 60)
    
    processor = ProductProcessor()
    
    test_products = [
        {
            'raw': {
                'name': 'King оферта - Hochland крема сирене 200 г',
                'price': 3.99,
                'id': '12345'
            },
            'store': 'Billa',
        },
        {
            'raw': {
                'name': 'K-Classic Прясно мляко 3.5% 1L',
                'price': 2.49,
                'id': '67890'
            },
            'store': 'Kaufland',
        },
        {
            'raw': {
                'name': 'Pilos кисело мляко',
                'unit': '<ul><li>400 г</li></ul>',
                'price': 1.29,
                'id': '11111'
            },
            'store': 'Lidl',
        },
    ]
    
    for test in test_products:
        product = processor.transform(test['raw'], test['store'], test['raw']['id'])
        print(f"\nStore: {product.store}")
        print(f"  Name: {product.name}")
        print(f"  Brand: {product.brand} (house: {product.is_house_brand})")
        print(f"  Quantity: {product.quantity_value} {product.quantity_unit}")
        print(f"  Price: {product.price}")
        print(f"  Normalized: {product.normalized_name}")
    
    print(f"\nStats: {processor.get_stats()}")
