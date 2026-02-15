#!/usr/bin/env python3
"""
Lidl Playwright Scraper - Stealthy, human-like browser automation
Manual stealth implementation (no playwright-stealth dependency)
"""

import asyncio
import json
import random
import time
import logging
import re
import os
from datetime import datetime
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/host-workspace/.playwright-browsers'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from playwright.async_api import async_playwright


async def apply_stealth(page):
    """Apply stealth settings to avoid bot detection"""
    
    # Override webdriver detection
    await page.add_init_script("""
        // Overwrite the 'webdriver' property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        // Overwrite plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Overwrite languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['bg-BG', 'bg', 'en-US', 'en'],
        });
        
        // Chrome runtime
        window.chrome = {
            runtime: {},
        };
        
        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)


class LidlPlaywrightScraper:
    """Stealthy Lidl scraper using Playwright"""
    
    def __init__(self, headless=True):
        self.headless = headless
        self.products = []
        self.seen_urls = set()
        self.seen_names = set()
        self.base_url = "https://www.lidl.bg"
        self.output_file = Path(__file__).parent.parent / "data" / "lidl_products.json"
        
        self.stats = {
            'pages_visited': 0,
            'products_found': 0,
            'errors': 0,
            'start_time': None
        }
    
    async def random_delay(self, min_sec=2.0, max_sec=5.0):
        """Human-like delay"""
        delay = random.gauss((min_sec + max_sec) / 2, (max_sec - min_sec) / 4)
        delay = max(min_sec, min(max_sec, delay))
        await asyncio.sleep(delay)
    
    async def human_scroll(self, page):
        """Simulate human scrolling"""
        total_height = await page.evaluate("document.body.scrollHeight")
        current = 0
        
        while current < total_height:
            scroll = random.randint(200, 500)
            current += scroll
            await page.evaluate(f"window.scrollTo(0, {current})")
            await asyncio.sleep(random.uniform(0.2, 0.5))
        
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.3)
    
    async def extract_products(self, page):
        """Extract products from rendered page"""
        
        # Wait for content
        await asyncio.sleep(2)
        
        # Scroll to load lazy content
        await self.human_scroll(page)
        await asyncio.sleep(1)
        
        # Try to extract products using multiple strategies
        products = await page.evaluate('''() => {
            const results = [];
            
            // Strategy 1: Find all potential product containers
            const containers = document.querySelectorAll(
                '[class*="product"], [class*="Product"], ' +
                '[class*="tile"], [class*="Tile"], ' +
                '[class*="item"], [class*="Item"], ' +
                '[class*="grid"] > div, [class*="Grid"] > div, ' +
                'article'
            );
            
            containers.forEach(el => {
                // Look for price indicators
                const priceEl = el.querySelector(
                    '[class*="price"], [class*="Price"], ' +
                    '[class*="cost"], [class*="Cost"], ' +
                    '[data-price], .pricefield'
                );
                
                // Look for title/name
                const nameEl = el.querySelector(
                    '[class*="title"], [class*="Title"], ' +
                    '[class*="name"], [class*="Name"], ' +
                    'h2, h3, h4, [class*="heading"]'
                );
                
                // Look for link
                const linkEl = el.querySelector('a[href*="/p/"], a[href*="/c/"]');
                
                // Only add if we found meaningful content
                if (priceEl || (nameEl && nameEl.textContent.trim().length > 3)) {
                    const name = nameEl ? nameEl.textContent.trim() : '';
                    const priceText = priceEl ? priceEl.textContent.trim() : el.textContent;
                    
                    // Extract price from text
                    const priceMatch = priceText.match(/(\\d+)[.,](\\d+)/);
                    const price = priceMatch ? parseFloat(priceMatch[1] + '.' + priceMatch[2]) : null;
                    
                    if (name && name.length > 2 && name.length < 200) {
                        results.push({
                            name: name,
                            price: price,
                            price_text: priceText.substring(0, 50),
                            url: linkEl ? linkEl.href : '',
                        });
                    }
                }
            });
            
            // Strategy 2: Look for structured data
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            scripts.forEach(script => {
                try {
                    const data = JSON.parse(script.textContent);
                    if (data['@type'] === 'Product') {
                        const offers = data.offers || {};
                        const price = offers.price || (Array.isArray(offers) ? offers[0]?.price : null);
                        results.push({
                            name: data.name || '',
                            price: price ? parseFloat(price) : null,
                            url: data.url || '',
                            brand: data.brand?.name || data.brand || '',
                            source: 'jsonld'
                        });
                    }
                    if (data['@graph']) {
                        data['@graph'].forEach(item => {
                            if (item['@type'] === 'Product') {
                                const offers = item.offers || {};
                                results.push({
                                    name: item.name || '',
                                    price: offers.price ? parseFloat(offers.price) : null,
                                    url: item.url || '',
                                    source: 'jsonld'
                                });
                            }
                        });
                    }
                } catch {}
            });
            
            return results;
        }''')
        
        return products
    
    async def get_category_urls(self, page):
        """Get category URLs"""
        logger.info("Getting category URLs...")
        
        await page.goto(f"{self.base_url}/bg/c/oferti", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await self.human_scroll(page)
        
        urls = await page.evaluate('''() => {
            const links = new Set();
            document.querySelectorAll('a').forEach(a => {
                const href = a.href;
                if (href.includes('/c/') && href.includes('lidl.bg')) {
                    links.add(href.split('?')[0].split('#')[0]);
                }
            });
            return Array.from(links);
        }''')
        
        # Also get individual offer pages
        offer_urls = await page.evaluate('''() => {
            const links = new Set();
            document.querySelectorAll('a').forEach(a => {
                const href = a.href;
                if ((href.includes('/a1') || href.includes('/a0')) && href.includes('lidl.bg')) {
                    links.add(href.split('?')[0].split('#')[0]);
                }
            });
            return Array.from(links);
        }''')
        
        all_urls = list(set(urls + offer_urls))
        logger.info(f"Found {len(all_urls)} category/offer URLs")
        return all_urls
    
    async def scrape_url(self, page, url):
        """Scrape a single URL"""
        if url in self.seen_urls:
            return 0
        self.seen_urls.add(url)
        
        logger.info(f"Scraping: {url}")
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await self.random_delay(2, 4)
            
            products = await self.extract_products(page)
            
            new_count = 0
            for p in products:
                name = p.get('name', '').strip()
                if name and len(name) > 3 and name not in self.seen_names:
                    self.seen_names.add(name)
                    p['price_bgn'] = p.get('price')
                    self.products.append(p)
                    new_count += 1
            
            self.stats['pages_visited'] += 1
            if new_count > 0:
                logger.info(f"  → {new_count} new products (total: {len(self.products)})")
            
            return new_count
            
        except Exception as e:
            logger.error(f"Error: {e}")
            self.stats['errors'] += 1
            return 0
    
    async def run(self):
        """Main entry point"""
        self.stats['start_time'] = datetime.now()
        
        logger.info("=" * 60)
        logger.info("Lidl Playwright Scraper - Starting")
        logger.info("=" * 60)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                locale='bg-BG',
            )
            
            page = await context.new_page()
            await apply_stealth(page)
            
            # Get URLs to scrape
            urls = await self.get_category_urls(page)
            
            # Scrape each URL
            for i, url in enumerate(urls[:40]):  # Limit to 40 URLs
                logger.info(f"Progress: {i+1}/{min(len(urls), 40)}")
                await self.scrape_url(page, url)
                
                # Coffee break every 15 pages
                if (i + 1) % 15 == 0 and i < len(urls) - 1:
                    coffee = random.randint(45, 90)
                    logger.info(f"☕ Coffee break: {coffee}s...")
                    await asyncio.sleep(coffee)
            
            await browser.close()
        
        self.save_products()
        self.print_summary()
    
    def save_products(self):
        """Save to JSON"""
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.products, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Saved {len(self.products)} products to {self.output_file}")
    
    def print_summary(self):
        """Print summary"""
        duration = datetime.now() - self.stats['start_time']
        
        logger.info("=" * 60)
        logger.info("COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration}")
        logger.info(f"Pages: {self.stats['pages_visited']}")
        logger.info(f"Products: {len(self.products)}")
        logger.info(f"Errors: {self.stats['errors']}")


if __name__ == "__main__":
    asyncio.run(LidlPlaywrightScraper(headless=True).run())
