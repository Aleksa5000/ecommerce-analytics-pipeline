"""Business constants shared by the generator, the quality checks and the analytics layer."""

COUNTRY_CURRENCY = {
    "DE": "EUR",
    "FR": "EUR",
    "ES": "EUR",
    "GB": "GBP",
    "US": "USD",
    "PL": "PLN",
    "SE": "SEK",
}
CATEGORIES = ["Apparel", "Electronics", "Home", "Beauty", "Sports", "Books"]
ORDER_STATUSES = ["completed", "cancelled"]
CHANNELS = ["organic", "paid_search", "social", "email", "referral"]
TABLES = ["customers", "products", "orders", "order_items", "returns", "fx_rates"]
SEGMENT_ORDER = [
    "Champions",
    "Loyal",
    "Potential Loyalists",
    "New Customers",
    "Needs Attention",
    "At Risk",
    "Hibernating",
    "Lost",
]
