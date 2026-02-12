# Contributing to PromoBG

## Development Setup

### Prerequisites
- Python 3.9+
- Git
- Web browser for testing

### Clone Repository
```bash
git clone https://github.com/MartinPetrov8/promo_products_bg.git
cd promo_products_bg
```

### Run Scrapers
```bash
cd services/scraper
python3 combined_scraper.py
```

### Test Locally
```bash
cd apps/web
python3 -m http.server 3001
# Open http://localhost:3001
```

## Workflow

### 1. Making Changes

```bash
# Create feature branch
git checkout -b feature/your-feature

# Make changes
# ...

# Test locally
python3 -m http.server 3001

# Commit
git add .
git commit -m "Add: your feature description"

# Push
git push origin feature/your-feature
```

### 2. Updating Data

```bash
# Run scrapers
cd services/scraper
python3 combined_scraper.py

# Copy to web app
cp data/all_products.json ../../apps/web/data/

# Copy to deployment
cp -r ../../apps/web/* ../../docs/

# Commit
git add .
git commit -m "Update: product data"
git push
```

### 3. Deploying

After pushing to `main`, GitHub Pages auto-deploys from `/docs`.

No manual deployment needed.

## Code Style

### Python
- Use type hints
- Use dataclasses for structured data
- Follow PEP 8
- Add docstrings to functions

```python
def scrape_store(url: str) -> List[Product]:
    """Scrape products from store URL.
    
    Args:
        url: Store offers page URL
        
    Returns:
        List of Product objects
    """
    pass
```

### JavaScript
- Use `const` and `let`, not `var`
- Use template literals for strings
- Use arrow functions where appropriate

```javascript
const renderProduct = (product) => {
    return `<div class="product">${product.name}</div>`;
};
```

### HTML/CSS
- Use Tailwind CSS classes
- Mobile-first responsive design
- Semantic HTML5 elements

## Adding a New Store

1. **Research the store website**
   - Find the offers/promotions page
   - Inspect HTML structure (F12 Developer Tools)
   - Check if data is in HTML or loaded via JavaScript

2. **Create scraper** (see `services/scraper/README.md`)

3. **Test thoroughly**
   ```bash
   python3 scrapers/newstore_scraper.py
   ```

4. **Add to combined scraper**

5. **Update documentation**
   - Add store to README.md table
   - Add scraper details to scraper README

6. **Submit pull request**

## Reporting Issues

Include:
- What you were trying to do
- What happened
- What you expected
- Browser/Python version
- Error messages (if any)

## Questions?

Open an issue or contact the team:
- Martin
- Maria
- Cookie 🍪
