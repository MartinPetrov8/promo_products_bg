"""
Category Classifier

Classifies products into GS1 GPC categories using:
1. Keyword matching (fast, high precision for common products)
2. Embedding similarity (slower, better coverage for edge cases)

Example:
    classifier = CategoryClassifier()
    category = classifier.classify("Прясно мляко 3.5% 1L")
    # Returns: '10303400' (Milk)
"""

import os
import json
import re
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path


class CategoryClassifier:
    """
    Bulgarian-aware product category classifier.
    
    Two-phase classification:
    1. Fast keyword matching for common products
    2. Embedding-based similarity for edge cases (optional)
    """
    
    def __init__(self, taxonomy_path: Optional[str] = None, use_embeddings: bool = False):
        """
        Initialize classifier with GS1 GPC taxonomy.
        
        Args:
            taxonomy_path: Path to gs1_gpc_taxonomy.json
            use_embeddings: Whether to use embedding-based fallback
        """
        self.taxonomy_path = taxonomy_path or self._find_taxonomy()
        self.taxonomy = self._load_taxonomy()
        self.keyword_index = self._build_keyword_index()
        self.use_embeddings = use_embeddings
        self.model = None
        self.category_embeddings = None
    
    def _find_taxonomy(self) -> str:
        """Find taxonomy file in common locations."""
        candidates = [
            '/host-workspace/projects/promo_products/repo/data/gs1_gpc_taxonomy.json',
            'data/gs1_gpc_taxonomy.json',
            '../data/gs1_gpc_taxonomy.json',
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        raise FileNotFoundError("gs1_gpc_taxonomy.json not found")
    
    def _load_taxonomy(self) -> Dict:
        """Load GS1 GPC taxonomy from JSON file."""
        with open(self.taxonomy_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _build_keyword_index(self) -> Dict[str, str]:
        """
        Build inverted index from keywords to category codes.
        
        Returns:
            Dict mapping keyword → category_code
        """
        index = {}
        
        def process_category(code: str, cat: Dict, parent_code: Optional[str] = None):
            # Get keywords for this category
            keywords = cat.get('keywords_bg', [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                # Store most specific category (longest code)
                if keyword_lower not in index or len(code) > len(index[keyword_lower]):
                    index[keyword_lower] = code
            
            # Process children
            if 'children' in cat:
                for child_code, child_cat in cat['children'].items():
                    if isinstance(child_cat, dict):
                        process_category(child_code, child_cat, code)
                    else:
                        # Leaf node with just a name string
                        pass
        
        categories = self.taxonomy.get('categories', {})
        for code, cat in categories.items():
            process_category(code, cat)
        
        return index
    
    def classify(self, product_name: str, brand: Optional[str] = None) -> Optional[str]:
        """
        Classify product into GS1 GPC category.
        
        Args:
            product_name: Product name (ideally cleaned/normalized)
            brand: Optional brand name for context
            
        Returns:
            GS1 GPC category code or None if no match
            
        Example:
            >>> classify("Прясно мляко 3.5% 1L")
            '10303400'
        """
        # Combine name and brand for matching
        text = product_name.lower()
        if brand:
            text = f"{brand.lower()} {text}"
        
        # Phase 1: Keyword matching
        best_match = None
        best_match_len = 0
        
        for keyword, code in self.keyword_index.items():
            if keyword in text:
                # Prefer longer keyword matches (more specific)
                if len(keyword) > best_match_len:
                    best_match = code
                    best_match_len = len(keyword)
        
        if best_match:
            return best_match
        
        # Phase 2: Embedding-based (if enabled)
        if self.use_embeddings:
            return self._classify_by_embedding(text)
        
        return None
    
    def _classify_by_embedding(self, text: str) -> Optional[str]:
        """
        Classify using embedding similarity.
        
        This is slower but handles edge cases better.
        """
        if self.model is None:
            self._load_embedding_model()
        
        if self.model is None:
            return None
        
        try:
            import numpy as np
            
            # Encode product text
            product_embedding = self.model.encode(text)
            
            # Find most similar category
            similarities = np.dot(self.category_embeddings, product_embedding)
            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]
            
            # Only return if confidence is high enough
            if best_score >= 0.5:
                return self.category_codes[best_idx]
            
        except Exception as e:
            print(f"Embedding classification failed: {e}")
        
        return None
    
    def _load_embedding_model(self):
        """Load embedding model and pre-compute category embeddings."""
        try:
            from sentence_transformers import SentenceTransformer
            
            # Use multilingual model that supports Bulgarian
            cache_path = '/host-workspace/.model-cache'
            os.makedirs(cache_path, exist_ok=True)
            os.environ['TRANSFORMERS_CACHE'] = cache_path
            os.environ['HF_HOME'] = cache_path
            
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            
            # Pre-compute category embeddings
            self.category_codes = []
            category_texts = []
            
            def collect_categories(code: str, cat: Dict):
                name_bg = cat.get('name_bg', cat.get('name', ''))
                keywords = cat.get('keywords_bg', [])
                text = f"{name_bg} {' '.join(keywords)}"
                self.category_codes.append(code)
                category_texts.append(text)
                
                if 'children' in cat:
                    for child_code, child_cat in cat['children'].items():
                        if isinstance(child_cat, dict):
                            collect_categories(child_code, child_cat)
            
            categories = self.taxonomy.get('categories', {})
            for code, cat in categories.items():
                collect_categories(code, cat)
            
            self.category_embeddings = self.model.encode(category_texts)
            
        except ImportError:
            print("sentence-transformers not installed, embedding classification disabled")
            self.model = None
    
    def get_category_name(self, code: str) -> str:
        """
        Get human-readable category name.
        
        Args:
            code: GS1 GPC category code
            
        Returns:
            Category name in Bulgarian
        """
        def find_category(code: str, categories: Dict) -> Optional[Dict]:
            for cat_code, cat in categories.items():
                if cat_code == code:
                    return cat
                if isinstance(cat, dict) and 'children' in cat:
                    result = find_category(code, cat['children'])
                    if result:
                        return result
            return None
        
        cat = find_category(code, self.taxonomy.get('categories', {}))
        if cat and isinstance(cat, dict):
            return cat.get('name_bg', cat.get('name', 'Unknown'))
        return 'Unknown'
    
    def get_parent_code(self, code: str) -> Optional[str]:
        """Get parent category code."""
        if len(code) > 8:
            return code[:-2] + '00'
        elif len(code) == 8:
            return code[:-6] + '000000'
        return None
    
    def classify_batch(self, products: List[Dict[str, Any]]) -> List[Tuple[str, Optional[str]]]:
        """
        Classify multiple products.
        
        Args:
            products: List of dicts with 'name' and optional 'brand'
            
        Returns:
            List of (product_id, category_code) tuples
        """
        results = []
        for product in products:
            name = product.get('name', '')
            brand = product.get('brand')
            product_id = product.get('id', '')
            
            category = self.classify(name, brand)
            results.append((product_id, category))
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get classifier statistics."""
        return {
            'keyword_count': len(self.keyword_index),
            'category_count': len(self.category_codes) if hasattr(self, 'category_codes') else 0,
            'embeddings_enabled': self.use_embeddings and self.model is not None,
        }


# === Convenience Functions ===

_classifier = None

def get_classifier() -> CategoryClassifier:
    """Get or create singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = CategoryClassifier()
    return _classifier


def classify_product(name: str, brand: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to classify a single product.
    
    Example:
        >>> classify_product("Прясно мляко 3.5%")
        '10303400'
    """
    return get_classifier().classify(name, brand)


# === Testing ===
if __name__ == "__main__":
    print("Category Classifier Tests:")
    print("=" * 60)
    
    classifier = CategoryClassifier()
    print(f"Loaded {classifier.get_stats()['keyword_count']} keywords")
    print()
    
    test_products = [
        ("Прясно мляко 3.5% 1L", None, "10303400"),  # Milk
        ("Coca-Cola 2L", None, "10504900"),  # Soft Drinks
        ("Пилешки бутчета 1kg", None, "10202700"),  # Poultry
        ("Моцарела 125г", None, "10303500"),  # Cheese
        ("Кисело мляко 400г", None, "10303600"),  # Yogurt
        ("Червени ябълки", None, "10101500"),  # Fresh Fruits
        ("Шампоан за коса 400мл", None, "20100000"),  # Hair Care
        ("Перилен препарат 2L", None, "30100000"),  # Laundry
        ("Бира Каменица 500ml", None, "10505200"),  # Beer
        ("Слънчогледово олио 1L", None, "10801000"),  # Oils
    ]
    
    for name, brand, expected in test_products:
        result = classifier.classify(name, brand)
        status = "✓" if result == expected else "✗"
        cat_name = classifier.get_category_name(result) if result else "None"
        print(f"{status} '{name[:30]}...'")
        print(f"   → {result} ({cat_name})")
        if result != expected:
            expected_name = classifier.get_category_name(expected)
            print(f"   Expected: {expected} ({expected_name})")
        print()
