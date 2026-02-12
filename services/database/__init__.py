# Database module
from .db import Database, get_db
from .monitor import DatabaseMonitor

# Models are optional (require pydantic)
try:
    from .models import Product, Store, Price, StoreProduct
    __all__ = ['Database', 'get_db', 'Product', 'Store', 'Price', 'StoreProduct', 'DatabaseMonitor']
except ImportError:
    __all__ = ['Database', 'get_db', 'DatabaseMonitor']
