from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Dict
import os
import motor.motor_asyncio
import uvicorn
import logging
import aiohttp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("order-mcp")

# MongoDB configuration
MONGO_URI = os.getenv("MCP_MONGODB_URI") or os.getenv("MDB_MCP_CONNECTION_STRING")
DB_NAME = os.getenv("MCP_DATABASE", "customer_support")

# LLM configuration
OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")

log.info(f"connecting to mongo: {MONGO_URI}")
log.info(f"using DB: {DB_NAME}")

app = FastAPI(title="Order Management MCP Server", version="0.3")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For demo only. In production, specify your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Async Mongo client
if MONGO_URI:
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo_client[DB_NAME]
else:
    mongo_client = None
    db = None

class InvokeRequest(BaseModel):
    tool: str
    args: Dict[str, Any] = {}

class ChatRequest(BaseModel):
    message: str
    context: Dict[str, Any]

TOOLS = {
    "get_order_history_by_email": {
        "params": {"email": "string", "limit": "int optional"},
        "description": "Return list of orders for an email (most recent first)",
    },
    "get_order_status": {
        "params": {"order_number": "string"},
        "description": "Return order by order_number"
    }
}

@app.get("/mcp/tools")
async def tools():
    return {"tools": TOOLS}

@app.get("/mcp/health")
async def health():
    """
    Simple health endpoint. Checks whether DB is configured and reachable.
    """
    if db is None:
        return {"status": "degraded", "mongo": "not_configured"}
    try:
        # `server_info` will raise if not reachable
        await mongo_client.server_info()
        return {"status": "ok", "mongo": "ok"}
    except Exception as e:
        log.exception("mongo health check failed")
        return {"status": "degraded", "mongo": "error", "detail": str(e)}

@app.post("/mcp/invoke")
async def invoke(req: InvokeRequest):
    tool = req.tool
    args = req.args or {}

    if db is None:
        raise HTTPException(status_code=503, detail="database unavailable")

    # Order history by email
    if tool == "get_order_history_by_email":
        email = args.get("email")
        try:
            limit = int(args.get("limit", 10))
        except Exception:
            limit = 10
        if not email:
            raise HTTPException(status_code=400, detail="email required")

        cursor = db.orders.find({"customer_email": email}).sort("order_date", -1).limit(limit)
        orders = []
        async for o in cursor:
            orders.append({
                "order_number": o.get("order_number"),
                "status": o.get("status"),
                "total_amount": o.get("total_amount"),
                "order_date": o.get("order_date")
            })
        return {"email": email, "orders": orders}

    # Order status by order_number
    elif tool == "get_order_status":
        order_number = args.get("order_number")
        if not order_number:
            raise HTTPException(status_code=400, detail="order_number required")

        o = await db.orders.find_one({"order_number": order_number})
        if not o:
            return {"error": "not_found", "order_number": order_number}

        # remove internal _id for safer transport
        o.pop("_id", None)
        # Ensure JSON serializable values (e.g., convert datetimes if needed)
        # For demo, return as-is; the client (LLM) will render fields it understands.
        return o

    raise HTTPException(status_code=404, detail=f"tool '{tool}' not found")

@app.post("/mcp/chat")
async def chat(req: ChatRequest):
    """Handle chat messages with order context."""
    try:
        # Call Ollama API for chat
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an order assistant. Answer questions about the order(s) using the context provided."
                },
                {
                    "role": "user",
                    "content": f"Context: {req.context}\n\nQuestion: {req.message}"
                }
            ],
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=10
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=500,
                        detail="LLM service unavailable"
                    )
                data = await resp.json()
                return {"response": data["message"]["content"]}
                
    except Exception as e:
        log.exception("Chat error")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 5001)), log_level="info")
