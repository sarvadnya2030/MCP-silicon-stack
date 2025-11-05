import requests
from typing import Any, Dict
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcp-client")

class MCPClient:
    def __init__(self, base_url: str, timeout: int=8, retries: int=2):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def tools(self):
        return requests.get(f"{self.base}/mcp/tools", timeout=self.timeout).json()

    def health(self):
        return requests.get(f"{self.base}/mcp/health", timeout=self.timeout).json()

    def invoke(self, tool: str, args: Dict[str, Any]):
        payload = {"tool": tool, "args": args}
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                r = requests.post(f"{self.base}/mcp/invoke", json=payload, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                else:
                    log.warning("MCP invoke non-200 %s: %s", r.status_code, r.text)
                    return {"error": "invoke_failed", "status": r.status_code, "body": r.text}
            except Exception as e:
                log.warning("MCP invoke attempt %d failed: %s", attempt + 1, e)
                last_exc = e
        raise last_exc

if __name__ == "__main__":
    client = MCPClient("http://localhost:5001")
    print("health:", client.health())
    print("tools:", client.tools())
    print("get_order_status:", client.invoke("get_order_status", {"order_id":"ORD-1"}))
