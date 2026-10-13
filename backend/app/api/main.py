from fastapi import APIRouter

from app.api.routes import (
    auth,
    cart,
    product_categories,
    product_imports,
    products,
    users,
    utils,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(products.router)
api_router.include_router(product_categories.router)
api_router.include_router(product_imports.router)
api_router.include_router(cart.router)
api_router.include_router(utils.router)
