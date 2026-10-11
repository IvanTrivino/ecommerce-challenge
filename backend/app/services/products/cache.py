from app.core.cache import CacheNamespace

PRODUCTS = CacheNamespace("product", ttl=300)
PRODUCT_CATEGORIES = CacheNamespace("product_category", ttl=300)
