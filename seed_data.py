import os
from pymongo import MongoClient
from datetime import datetime
uri = os.getenv("MDB_MCP_CONNECTION_STRING")
if not uri:
    print("Set MDB_MCP_CONNECTION_STRING before running.")
    raise SystemExit(1)

client = MongoClient(uri)
db = client.get_database()
# create one user and one order
db.users.insert_one({"user_id":"u1","name":"Test User","email":"test@example.com","created_at":datetime.utcnow()})
db.orders.insert_one({
    "order_id":"ORD-1",
    "user_id":"u1",
    "status":"shipped",
    "total":49.99,
    "items":[{"sku":"SKU-1","name":"Widget","qty":1}],
    "shipping":{"carrier":"MockCarrier","tracking_url":None},
    "created_at":datetime.utcnow(),
    "updated_at":datetime.utcnow()
})
print("seeded: 1 user, 1 order")
