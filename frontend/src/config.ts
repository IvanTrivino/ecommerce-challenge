export const APP_NAME = import.meta.env.VITE_APP_NAME || "Ecommerce"
export const pageTitle = (page: string) => `${page} - ${APP_NAME}`
export const STORE_PAGE_SIZE = 12
export const ADMIN_PAGE_SIZE = 20
export const LOW_STOCK_THRESHOLD = 5
