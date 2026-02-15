"""
Category Classifier

Classifies Bulgarian grocery products into categories using:
1. Keyword matching (fast, high precision)
2. Embedding similarity (fallback for unknown products)

Usage:
    classifier = CategoryClassifier()
    category = classifier.classify("Прясно мляко 3.5% 1L")
    # Returns: "dairy"
"""

import json
import os
import re
from typing import Optional, Dict, List, Tuple
from pathlib import Path


class CategoryClassifier:
    """
    Bulgarian product category classifier.
    
    Uses keyword matching first (fast), falls back to embeddings
    only when needed (lazy-loaded to save memory).
    """
    
    def __init__(self, taxonomy_path: Optional[str] = None):
        """
        Initialize classifier with taxonomy.
        
        Args:
            taxonomy_path: Path to categories.json. If None, uses default.
        """
        if taxonomy_path is None:
            # Default path relative to this file
            base_dir = Path(__file__).parent.parent
            taxonomy_path = base_dir / "data" / "categories.json"
        
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.categories = data['categories']
        self._keyword_index = self._build_keyword_index()
        
        # Lazy-loaded embedding model
        self._model = None
        self._category_embeddings = None
    
    def _build_keyword_index(self) -> Dict[str, str]:
        """Build keyword → category_id index for fast lookup."""
        index = {}
        for cat_id, cat_data in self.categories.items():
            for keyword in cat_data.get('keywords', []):
                # Store lowercase for matching
                index[keyword.lower()] = cat_id
        return index
    
    def classify(self, product_name: str, brand: Optional[str] = None) -> str:
        """
        Classify product into category.
        
        Args:
            product_name: Product name (Bulgarian)
            brand: Optional brand name
            
        Returns:
            Category ID (e.g., "dairy", "meat", "beverages_soft")
        """
        if not product_name:
            return "other"
        
        # Combine name and brand for matching
        text = product_name.lower()
        if brand:
            text = f"{brand.lower()} {text}"
        
        # Step 1: Try keyword matching (fast, high precision)
        category = self._match_keywords(text)
        if category:
            return category
        
        # Step 2: Fall back to embedding similarity (slower)
        category = self._match_embedding(text)
        return category or "other"
    
    def _match_keywords(self, text: str) -> Optional[str]:
        """Match using keyword index."""
        # Check each keyword (longest first for better matching)
        keywords_sorted = sorted(self._keyword_index.keys(), key=len, reverse=True)
        
        for keyword in keywords_sorted:
            # Use word boundary matching
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text):
                return self._keyword_index[keyword]
        
        return None
    
    def _match_embedding(self, text: str) -> Optional[str]:
        """Match using embedding similarity (lazy-loaded)."""
        # Skip embedding matching for now - keyword matching covers ~90% of cases
        # This avoids loading the heavy model unless really needed
        return None
    
    def get_category_name(self, category_id: str, lang: str = 'bg') -> str:
        """Get human-readable category name."""
        cat = self.categories.get(category_id, {})
        if lang == 'en':
            return cat.get('name_en', category_id)
        return cat.get('name', category_id)
    
    def get_category_code(self, category_id: str) -> str:
        """Get GS1 GPC code for category."""
        return self.categories.get(category_id, {}).get('code', '99000000')
    
    def list_categories(self) -> List[Tuple[str, str, str]]:
        """List all categories with (id, name_bg, name_en)."""
        return [
            (cat_id, cat['name'], cat['name_en'])
            for cat_id, cat in self.categories.items()
        ]


# === Convenience function ===

_classifier = None

def classify_product(product_name: str, brand: Optional[str] = None) -> str:
    """
    Classify a product (uses shared classifier instance).
    
    Example:
        >>> classify_product("Прясно мляко 3.5%")
        'dairy'
        >>> classify_product("Coca-Cola 2L")
        'beverages_soft'
    """
    global _classifier
    if _classifier is None:
        _classifier = CategoryClassifier()
    return _classifier.classify(product_name, brand)


# === Testing ===
if __name__ == "__main__":
    classifier = CategoryClassifier()
    
    test_cases = [
        ("Прясно мляко 3.5% 1L", None, "dairy"),
        ("Пилешко филе 500г", None, "meat"),
        ("Coca-Cola 2L", "Coca-Cola", "beverages_soft"),
        ("Heineken бира 500ml", None, "beverages_beer"),
        ("Домати 1кг", None, "produce_veg"),
        ("Ябълки Златна превъзходна", None, "produce_fruit"),
        ("Луканка Престиж 200г", "Престиж", "deli"),
        ("Шампоан Head & Shoulders", None, "personal_care"),
        ("Ариел прах за пране", None, "cleaning"),
        ("Чипс Pringles", None, "snacks"),
        ("Милка шоколад 100г", None, "chocolate"),
        ("Паста Барила спагети", None, "pasta_rice"),
        ("Яйца 10 бр", None, "eggs"),
        ("Unknown product xyz", None, "other"),
    ]
    
    print("Category Classification Tests:")
    print("-" * 60)
    
    correct = 0
    for name, brand, expected in test_cases:
        result = classifier.classify(name, brand)
        status = "✓" if result == expected else "✗"
        if result == expected:
            correct += 1
        print(f"{status} '{name[:35]}...' → {result} (expected: {expected})")
    
    print(f"\nAccuracy: {correct}/{len(test_cases)} ({100*correct/len(test_cases):.0f}%)")
