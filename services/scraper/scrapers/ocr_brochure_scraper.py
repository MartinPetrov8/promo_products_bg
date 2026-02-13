#!/usr/bin/env python3
"""
OCR Brochure Scraper - Extracts products from grocery store brochure images
Uses GPT-4 Vision API for OCR and structured extraction.

Supported sources:
- Publitas flipbooks (Billa, others)
- broshura.bg PDFs
- Direct image URLs
"""

import base64
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
MODEL = "gpt-4o-mini"  # or "gpt-4o" for better accuracy
MAX_PAGES = 50
RATE_LIMIT_DELAY = 1.0  # seconds between API calls


@dataclass
class ExtractedProduct:
    """Product extracted from brochure via OCR"""
    name: str
    price: float
    old_price: Optional[float] = None
    unit: Optional[str] = None
    discount_pct: Optional[int] = None
    brand: Optional[str] = None
    source_page: int = 0
    source_brochure: str = ""
    extracted_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OCRBrochureScraper:
    """
    Scrapes grocery brochures using OCR.
    
    Workflow:
    1. Download PDF from Publitas or other source
    2. Extract pages as images
    3. Send each image to GPT-4 Vision
    4. Parse structured product data
    """
    
    def __init__(self, output_dir: Path = None):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable required")
        
        self.output_dir = output_dir or Path(__file__).parent.parent.parent.parent / "data" / "brochures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.products: List[ExtractedProduct] = []
        self.stats = {
            'pages_processed': 0,
            'products_extracted': 0,
            'api_calls': 0,
            'errors': 0
        }
    
    def download_publitas_pdf(self, publitas_url: str) -> Optional[Path]:
        """
        Download PDF from Publitas flipbook URL.
        
        Args:
            publitas_url: URL like https://view.publitas.com/billa-bulgaria/...
        
        Returns:
            Path to downloaded PDF or None if failed
        """
        logger.info(f"Fetching Publitas page: {publitas_url}")
        
        try:
            response = requests.get(publitas_url, timeout=30)
            response.raise_for_status()
            html = response.text
            
            # Find PDF URL in HTML
            pdf_match = re.search(r'publitas\.com/(\d+)/(\d+)/pdfs/([a-f0-9-]+)\.pdf', html)
            if not pdf_match:
                logger.error("Could not find PDF URL in Publitas page")
                return None
            
            group_id, pub_id, pdf_id = pdf_match.groups()
            pdf_url = f"https://view.publitas.com/{group_id}/{pub_id}/pdfs/{pdf_id}.pdf"
            
            # Download PDF
            slug = publitas_url.rstrip('/').split('/')[-1]
            pdf_path = self.output_dir / f"{slug}.pdf"
            
            logger.info(f"Downloading PDF: {pdf_url}")
            pdf_response = requests.get(pdf_url, timeout=120)
            pdf_response.raise_for_status()
            
            with open(pdf_path, 'wb') as f:
                f.write(pdf_response.content)
            
            logger.info(f"Saved PDF: {pdf_path} ({len(pdf_response.content) / 1024 / 1024:.1f} MB)")
            return pdf_path
            
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
    
    def extract_pages(self, pdf_path: Path) -> List[Path]:
        """
        Extract pages from PDF as JPEG images.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            List of paths to extracted page images
        """
        pages_dir = self.output_dir / "pages" / pdf_path.stem
        pages_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Extracting pages from {pdf_path}")
        
        # Use pdfimages to extract
        result = subprocess.run(
            ['pdfimages', '-j', str(pdf_path), str(pages_dir / 'page')],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            logger.error(f"pdfimages failed: {result.stderr}")
            return []
        
        # Get sorted list of extracted images
        images = sorted(pages_dir.glob('*.jpg'))
        logger.info(f"Extracted {len(images)} page images")
        
        return images
    
    def ocr_page(self, image_path: Path) -> List[Dict]:
        """
        Extract products from a single brochure page using GPT-4 Vision.
        
        Args:
            image_path: Path to page image
        
        Returns:
            List of product dictionaries
        """
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = """Extract ALL grocery products from this Bulgarian store brochure page.

For each product, extract:
- name: Product name in Bulgarian (include brand if visible)
- price: Current promotional price in лв (the lower/highlighted price)
- old_price: Original price if shown (crossed out or smaller)
- unit: Unit of measure (кг, л, бр, г, мл, опаковка)
- discount_pct: Percentage discount if shown (e.g., -30%)

Return ONLY a valid JSON array, no markdown:
[{"name":"...","price":X.XX,"old_price":X.XX,"unit":"...","discount_pct":XX}]

Rules:
- All prices should be in BGN (лв)
- If price unclear, skip that product
- Include brand in product name if visible
- If no products visible, return: []"""

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ],
            "max_tokens": 3000
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            self.stats['api_calls'] += 1
            
            if response.status_code != 200:
                logger.error(f"API error {response.status_code}: {response.text[:200]}")
                self.stats['errors'] += 1
                return []
            
            content = response.json()['choices'][0]['message']['content'].strip()
            
            # Clean markdown if present
            if content.startswith('```'):
                content = content.split('\n', 1)[1].rsplit('\n', 1)[0]
            
            products = json.loads(content)
            return products if isinstance(products, list) else []
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            self.stats['errors'] += 1
            return []
        except Exception as e:
            logger.error(f"OCR error: {e}")
            self.stats['errors'] += 1
            return []
    
    def process_brochure(self, pdf_path: Path, max_pages: int = None) -> List[ExtractedProduct]:
        """
        Process entire brochure PDF and extract all products.
        
        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum pages to process (None = all)
        
        Returns:
            List of extracted products
        """
        max_pages = max_pages or MAX_PAGES
        now = datetime.now(timezone.utc).isoformat()
        
        # Extract pages
        page_images = self.extract_pages(pdf_path)
        if not page_images:
            return []
        
        # Process each page
        all_products = []
        for i, image_path in enumerate(page_images[:max_pages]):
            logger.info(f"Processing page {i+1}/{min(len(page_images), max_pages)}: {image_path.name}")
            
            products = self.ocr_page(image_path)
            self.stats['pages_processed'] += 1
            
            # Convert to ExtractedProduct
            for p in products:
                product = ExtractedProduct(
                    name=p.get('name', ''),
                    price=float(p.get('price', 0)),
                    old_price=float(p['old_price']) if p.get('old_price') else None,
                    unit=p.get('unit'),
                    discount_pct=int(p['discount_pct']) if p.get('discount_pct') else None,
                    source_page=i + 1,
                    source_brochure=pdf_path.name,
                    extracted_at=now
                )
                all_products.append(product)
            
            self.stats['products_extracted'] += len(products)
            logger.info(f"  Found {len(products)} products")
            
            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)
        
        self.products.extend(all_products)
        return all_products
    
    def save_results(self, output_path: Path = None) -> Path:
        """Save extracted products to JSON file."""
        output_path = output_path or self.output_dir / "extracted_products.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in self.products], f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.products)} products to {output_path}")
        return output_path
    
    def get_stats(self) -> Dict:
        """Get scraping statistics."""
        return {
            **self.stats,
            'total_products': len(self.products)
        }


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='OCR Brochure Scraper')
    parser.add_argument('--url', help='Publitas brochure URL')
    parser.add_argument('--pdf', help='Local PDF file path')
    parser.add_argument('--max-pages', type=int, default=50, help='Max pages to process')
    parser.add_argument('--output', help='Output JSON path')
    args = parser.parse_args()
    
    scraper = OCRBrochureScraper()
    
    if args.url:
        pdf_path = scraper.download_publitas_pdf(args.url)
        if not pdf_path:
            print("Failed to download PDF")
            return
    elif args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"PDF not found: {pdf_path}")
            return
    else:
        print("Provide --url or --pdf")
        return
    
    products = scraper.process_brochure(pdf_path, max_pages=args.max_pages)
    
    output_path = Path(args.output) if args.output else None
    scraper.save_results(output_path)
    
    stats = scraper.get_stats()
    print(f"\n=== OCR SCRAPE COMPLETE ===")
    print(f"Pages processed: {stats['pages_processed']}")
    print(f"Products extracted: {stats['products_extracted']}")
    print(f"API calls: {stats['api_calls']}")
    print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
