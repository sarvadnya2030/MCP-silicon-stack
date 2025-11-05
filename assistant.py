#!/usr/bin/env python3
import os
import json
import random
import requests
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

# Regular expressions for validation
ORDER_NUMBER_PATTERN = r"(ORD-\d{4}-\d{3})"
EMAIL_PATTERN = r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

# --- Configuration ---
OLLAMA_HTTP_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = "qwen3:0.6b"

# List your 4 MCP endpoints here
MCP_ENDPOINTS = [
    os.getenv("MCP_URL1", "http://localhost:5001"),
    os.getenv("MCP_URL2", "http://localhost:5002"),
    os.getenv("MCP_URL3", "http://localhost:5003"),
    os.getenv("MCP_URL4", "http://localhost:5004")
]

REQUEST_TIMEOUT = 5  # shorter timeout for better UX
RETRY_ATTEMPTS = 2   # number of MCPs to try before giving up

# --- Session memory to hold retrieved orders ---
SESSION_MEMORY: Dict[str, Dict[str, Any]] = {}


# --- LLM helpers (left in place for non-order flows) ---
def safe_json_parse(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except:
        pass
    # extract first JSON object
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s:e+1])
        except:
            pass
    return None


def model_generate(prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_HTTP_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"thinking": "disabled"},
        },
        timeout=REQUEST_TIMEOUT,
    )
    raw = r.text.strip()
    j = safe_json_parse(raw)
    if not j:
        raise RuntimeError(f"OLLAMA bad response: {raw}")
    return j["message"]["content"].strip()


def check_mcp_health(mcp_base: str) -> bool:
    """Check if an MCP endpoint is healthy."""
    try:
        r = requests.get(f"{mcp_base}/mcp/health", timeout=REQUEST_TIMEOUT)
        return r.status_code == 200 and r.json().get("status") in ("ok", "degraded")
    except Exception:
        return False

def call_mcp(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Call MCP endpoint with retries across healthy servers."""
    # Try up to RETRY_ATTEMPTS different MCPs
    errors = []
    tried = set()
    for _ in range(RETRY_ATTEMPTS):
        # Pick a random MCP we haven't tried yet
        available = [ep for ep in MCP_ENDPOINTS if ep not in tried]
        if not available:
            break
        mcp_base = random.choice(available)
        tried.add(mcp_base)
        
        try:
            resp = requests.post(f"{mcp_base}/mcp/invoke", 
                               json={"tool": tool, "args": args}, 
                               timeout=REQUEST_TIMEOUT)
            # try to return JSON safely
            try:
                return resp.json()
            except Exception:
                errors.append(f"Invalid JSON from {mcp_base}")
                continue
        except requests.exceptions.Timeout:
            errors.append(f"Timeout from {mcp_base}")
        except requests.exceptions.ConnectionError:
            errors.append(f"Cannot connect to {mcp_base}")
        except Exception as e:
            errors.append(f"Error from {mcp_base}: {e}")
    
    # All retries failed
    return {
        "error": "mcp_unavailable",
        "details": "Could not reach order service. Please try again in a few minutes.",
        "debug_info": ", ".join(errors)
    }


# --- Formatting & extraction helpers ---
def _fmt_currency(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def _fmt_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    # try ISO parse
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%b %d, %Y")
    except Exception:
        # try common Mongo format with space
        try:
            # strip timezone Z
            if value.endswith("Z"):
                value = value[:-1]
            dt = datetime.fromisoformat(value)
            return dt.strftime("%b %d, %Y")
        except Exception:
            return value


def _get(order: Dict[str, Any], *keys) -> Optional[Any]:
    for k in keys:
        if not k:
            continue
        # nested dot
        if "." in k:
            cur = order
            parts = k.split(".")
            ok = True
            for p in parts:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    ok = False
                    break
            if ok:
                return cur
        else:
            if k in order:
                return order[k]
    return None


def format_items(items: List[Dict[str, Any]]) -> str:
    parts = []
    for it in items:
        name = it.get("name") or it.get("title") or it.get("sku") or "Item"
        qty = it.get("qty") or it.get("quantity") or it.get("qty_ordered") or 1
        price = it.get("price") or it.get("unit_price") or it.get("unitPrice") or it.get("amount")
        price_s = _fmt_currency(price) if price is not None else None
        if price_s:
            parts.append(f"{name} ({int(qty)} x {price_s})")
        else:
            parts.append(f"{name} ({int(qty)} x qty={qty})")
    return ", ".join(parts) if parts else "(no items)"


def build_order_summary(order: Dict[str, Any]) -> str:
    # customer
    customer_name = _get(order, "customer_name", "customer.name", "name", "customer_name")
    customer_email = _get(order, "customer_email", "email", "customer.email")

    order_number = _get(order, "order_number", "order_id", "id") or "(unknown order)"

    # items
    items = _get(order, "items", "line_items", "order_items") or []
    items_str = format_items(items) if isinstance(items, list) else str(items)

    # totals
    total = _get(order, "total_amount", "total", "grand_total", "amount")
    tax = _get(order, "tax", "tax_amount", "taxAmount")
    shipping_cost = _get(order, "shipping_cost", "shipping.amount", "shipping_cost")
    # try to compute grand total if not present
    try:
        total_val = float(total) if total is not None else None
    except Exception:
        total_val = None
    if total_val is None:
        try:
            t = 0.0
            if isinstance(items, list):
                for it in items:
                    p = it.get("price") or it.get("unit_price") or it.get("amount")
                    q = it.get("qty") or it.get("quantity") or 1
                    if p is not None:
                        t += float(p) * int(q)
            if shipping_cost:
                t += float(shipping_cost)
            if tax:
                t += float(tax)
            total_val = t if t else None
        except Exception:
            total_val = None

    total_s = _fmt_currency(total_val) if total_val is not None else (_fmt_currency(total) if isinstance(total, (int, float)) else None)

    status = _get(order, "status") or "(unknown)"

    # shipping address
    ship_addr = _get(order, "shipping.address", "shipping_address", "shippingAddress", "address")
    if isinstance(ship_addr, dict):
        addr_parts = [ship_addr.get(k) for k in ("line1", "street", "address1", "street1") if ship_addr.get(k)]
        city = ship_addr.get("city")
        state = ship_addr.get("state")
        postal = ship_addr.get("postal_code") or ship_addr.get("zip") or ship_addr.get("postal")
        country = ship_addr.get("country")
        city_state = ", ".join([p for p in (city, state) if p])
        addr = ", ".join([p for p in (" ".join(addr_parts), city_state, postal, country) if p])
    else:
        addr = ship_addr or "(no shipping address)"

    # tracking and delivery dates
    tracking = _get(order, "shipping.tracking_number", "tracking_number", "tracking", "shipping.tracking")
    delivered_date = _get(order, "delivered_at", "delivery_date", "shipping.delivered_at")
    delivered_s = _fmt_date(delivered_date) if delivered_date else None

    # notes
    notes = _get(order, "notes", "note", "customer_notes", "internal_notes")

    # build summary
    parts = []
    greet = f"Hello {customer_name}! " if customer_name else "Hello! "
    parts.append(greet + f"Your order {order_number} is {status}.")
    parts.append(f"Items: {items_str}.")
    if total_s:
        parts.append(f"Total: {total_s}.")
    if addr:
        parts.append(f"Shipping to: {addr}.")
    if tracking:
        parts.append(f"Tracking: {tracking}.")
    if delivered_s:
        parts.append(f"Delivered on: {delivered_s}.")
    if notes:
        parts.append(f"Notes: {notes}.")

    # always include email if available
    if customer_email:
        parts.insert(1, f"Customer email: {customer_email}.")

    # join and ensure friendly tone
    summary = " ".join(parts)
    return summary


def extract_field(order: Dict[str, Any], field: str) -> str:
    """Extract a specific field from an order with friendly formatting."""
    f = field.lower()
    if f in ("status", "order status"):
        return str(_get(order, "status") or "(unknown)")
    if f in ("total", "total cost", "total amount", "total price"):
        total = _get(order, "total_amount", "total", "grand_total", "amount")
        if total is None:
            # try compute
            return build_order_summary(order)
        return _fmt_currency(total) if isinstance(total, (int, float)) else _fmt_currency(float(total)) if _is_number_like(total) else str(total)
    if f in ("shipping address", "shipping", "address"):
        ship_addr = _get(order, "shipping.address", "shipping_address", "address")
        if isinstance(ship_addr, dict):
            addr_parts = [ship_addr.get(k) for k in ("line1", "street", "address1", "street1") if ship_addr.get(k)]
            city = ship_addr.get("city")
            state = ship_addr.get("state")
            postal = ship_addr.get("postal_code") or ship_addr.get("zip") or ship_addr.get("postal")
            country = ship_addr.get("country")
            city_state = ", ".join([p for p in (city, state) if p])
            return ", ".join([p for p in (" ".join(addr_parts), city_state, postal, country) if p])
        return str(ship_addr or "(no shipping address)")
    if f in ("tracking", "tracking number"):
        return str(_get(order, "shipping.tracking_number", "tracking_number", "tracking") or "(no tracking number)")
    if f in ("items", "order items"):
        items = _get(order, "items", "line_items", "order_items") or []
        return format_items(items) if isinstance(items, list) else str(items)
    if f in ("customer", "customer name", "name"):
        return str(_get(order, "customer_name", "customer.name", "name") or "(no name)")
    if f in ("email", "customer email"):
        return str(_get(order, "customer_email", "email", "customer.email") or "(no email)")
    if f in ("notes", "note"):
        return str(_get(order, "notes", "note", "customer_notes", "internal_notes") or "(no notes)")
    if f in ("date", "order date"):
        date = _get(order, "order_date", "created_at", "date")
        return _fmt_date(date) if date else "(no date)"
    # fallback: return short summary
    return build_order_summary(order)

def format_order_history(orders: List[Dict[str, Any]], email: str) -> str:
    """Format a list of orders for a customer."""
    if not orders:
        return f"No orders found for {email}."
    
    # Get customer name from first order if available
    customer_name = None
    for o in orders:
        name = _get(o, "customer_name", "customer.name", "name")
        if name:
            customer_name = name
            break
    
    parts = []
    greet = f"Hello {customer_name}! " if customer_name else "Hello! "
    parts.append(greet + f"You have {len(orders)} order{'s' if len(orders) != 1 else ''}:")
    
    for i, o in enumerate(orders, 1):
        order_num = _get(o, "order_number", "order_id", "id") or "(unknown)"
        status = _get(o, "status") or "(unknown)"
        total = _get(o, "total_amount", "total", "amount")
        total_s = _fmt_currency(total) if total is not None else "(no total)"
        date = _get(o, "order_date", "created_at", "date")
        date_s = _fmt_date(date) if date else "(no date)"
        parts.append(f"{i}. {order_num}, {status}, Total: {total_s}, Order Date: {date_s}")
    
    parts.append(f"Customer email: {email}")
    return "\n".join(parts)

def extract_field_from_history(orders: List[Dict[str, Any]], field: str) -> str:
    """Extract a specific field from multiple orders."""
    parts = []
    for o in orders:
        order_num = _get(o, "order_number", "order_id", "id") or "(unknown)"
        value = extract_field(o, field)
        parts.append(f"{order_num}: {value}")
    return "\n".join(parts)


def _is_number_like(x: Any) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False


# --- Main Interactive Loop ---
def detect_lookup_type(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detect order number or email in text, along with any field requests.
    Returns: (type, value, field) where type is 'order' or 'email'.
    """
    # Check for order number
    order_match = re.search(ORDER_NUMBER_PATTERN, text.upper())
    if order_match:
        order_number = order_match.group(1)
        # Look for field request
        field = None
        text = text.lower()
        if any(k in text for k in ("total cost", "total of", "total for", "total cost of", "total:", "total")) and "items" not in text:
            field = "total"
        elif any(k in text for k in ("status", "order status")):
            field = "status"
        elif any(k in text for k in ("shipping address", "shipping to", "ship to", "address")) and "tracking" not in text:
            field = "shipping address"
        elif any(k in text for k in ("tracking", "tracking number", "track")):
            field = "tracking"
        elif any(k in text for k in ("items", "what's in", "what are the items", "line items")):
            field = "items"
        elif any(k in text for k in ("email", "customer email")):
            field = "email"
        elif any(k in text for k in ("date", "order date", "when")):
            field = "date"
        return "order", order_number, field
    
    # Check for email
    email_match = re.search(EMAIL_PATTERN, text.lower())
    if email_match:
        email = email_match.group(1)
        # Look for field request
        field = None
        text = text.lower()
        if "status" in text:
            field = "status"
        elif "total" in text and "items" not in text:
            field = "total"
        elif "items" in text:
            field = "items"
        elif "date" in text or "when" in text:
            field = "date"
        return "email", email, field
    
    return None, None, None

def interactive_loop():
    # Check MCP health at startup
    healthy_mcps = [ep for ep in MCP_ENDPOINTS if check_mcp_health(ep)]
    if not healthy_mcps:
        print("ERROR: No MCP servers are available. Please start at least one MCP server.")
        print("Available MCPs:", MCP_ENDPOINTS)
        return
    
    print(f"Assistant ready. {len(healthy_mcps)}/{len(MCP_ENDPOINTS)} MCPs available.")
    while True:
        try:
            u = input("> ").strip()
        except EOFError:
            print("\nExiting assistant.")
            break
        if not u:
            continue
        if u.lower() in ("exit", "quit"):
            break

        # Detect lookup type (order or email) and field request
        lookup_type, value, field = detect_lookup_type(u)
        
        # Handle order lookup
        if lookup_type == "order":
            order_number = value

            # If cached, use session memory
            if order_number in SESSION_MEMORY:
                order = SESSION_MEMORY[order_number]
            else:
                # fetch full order from MCP
                result = call_mcp("get_order_status", {"order_number": order_number})
                if not isinstance(result, dict):
                    print("Sorry — I couldn't reach the order service right now. Please try again in a few minutes.")
                    continue
                if "error" in result:
                    # handle common errors with friendly messages
                    err = result.get("error", "unknown")
                    if err == "not_found":
                        print(f"I can't find order {order_number}. Please check the order number and try again.")
                    elif err == "mcp_unavailable":
                        print(result.get("details", "Order service is temporarily unavailable."))
                    else:
                        print("Sorry, I encountered an error looking up your order. Please try again in a few minutes.")
                    continue
                order = result
                # cache by order number
                SESSION_MEMORY[order_number] = order

            # Determine whether the user asked for a specific field
            q = u.lower()
            # mapping of keywords to fields
            if any(k in q for k in ("total cost", "total of", "total for", "total cost of", "total:" , "total")) and "items" not in q:
                out = extract_field(order, "total")
                print(f"The total cost of {order_number} is {out}.")
                continue
            if any(k in q for k in ("status", "order status")):
                out = extract_field(order, "status")
                print(f"{order_number} status: {out}.")
                continue
            if any(k in q for k in ("shipping address", "shipping to", "ship to", "address")) and "tracking" not in q:
                out = extract_field(order, "shipping address")
                print(f"Shipping address for {order_number}: {out}")
                continue
            if any(k in q for k in ("tracking", "tracking number", "track")):
                out = extract_field(order, "tracking")
                print(f"Tracking for {order_number}: {out}")
                continue
            if any(k in q for k in ("items", "what's in", "what are the items", "line items")):
                out = extract_field(order, "items")
                print(f"Items in {order_number}: {out}")
                continue
            if any(k in q for k in ("email", "customer email")):
                out = extract_field(order, "email")
                print(f"Customer email for {order_number}: {out}")
                continue

            # Handle field-specific or full summary
            if field:
                out = extract_field(order, field)
                print(f"{order_number} {field}: {out}")
            else:
                summary = build_order_summary(order)
                print(summary)
            continue

        # Handle email lookup
        elif lookup_type == "email":
            email = value
            # fetch order history from MCP
            result = call_mcp("get_order_history_by_email", {"email": email, "limit": 10})
            if not isinstance(result, dict):
                print("Sorry — I couldn't reach the order service right now. Please try again in a few minutes.")
                continue
            if "error" in result:
                err = result.get("error", "unknown")
                if err == "not_found":
                    print(f"I couldn't find any orders for {email}.")
                elif err == "mcp_unavailable":
                    print(result.get("details", "Order service is temporarily unavailable."))
                else:
                    print("Sorry, I encountered an error looking up orders. Please try again in a few minutes.")
                continue
            
            orders = result.get("orders", [])
            # cache orders by order number
            for o in orders:
                if isinstance(o, dict):
                    order_num = _get(o, "order_number", "order_id", "id")
                    if order_num:
                        SESSION_MEMORY[order_num] = o
            
            # Handle field-specific or full summary
            if field:
                out = extract_field_from_history(orders, field)
                print(f"Orders for {email}, {field}:")
                print(out)
            else:
                summary = format_order_history(orders, email)
                print(summary)
            continue

        # --- Otherwise, let the LLM handle non-order prompts ---
        prompt = "You are an assistant. Answer briefly." + "\nUser: " + u + "\nRespond now."
        try:
            out = model_generate(prompt)
        except Exception as e:
            print(f"LLM error: {e}")
            continue
        j = safe_json_parse(out)

        if j and "tool" in j:
            tool = j["tool"]
            args = j.get("args", {})

            # If it's an order lookup, follow the same caching & formatting rules
            if tool == "get_order_status":
                order_number = args.get("order_number")
                if not order_number:
                    print("order_number required in tool args")
                    continue
                if order_number in SESSION_MEMORY:
                    order = SESSION_MEMORY[order_number]
                else:
                    result = call_mcp(tool, args)
                    if not isinstance(result, dict) or "error" in result:
                        if isinstance(result, dict) and result.get("error") == "not_found":
                            print(f"I can't find order {order_number}.")
                        else:
                            print(f"Order lookup failed: {result}")
                        continue
                    order = result
                    SESSION_MEMORY[order_number] = order
                # produce friendly summary
                print(build_order_summary(order))
                continue

            # for other tools, call MCP and print raw result
            result = call_mcp(tool, args)
            print(json.dumps(result))
        else:
            print(out)


# --- Entry Point ---
if __name__ == "__main__":
    interactive_loop()
