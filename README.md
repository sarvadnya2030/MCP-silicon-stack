# Silicon Stack MCP Server

A microservice-based Order Management System with a modern web interface and intelligent chat assistant.

## Features

- 🔍 Order lookup by order number or email
- 💬 AI-powered chat interface for order inquiries
- 📱 Responsive web interface
- 🚀 FastAPI backend with MongoDB
- 🤖 LLM integration for natural language queries
- 💾 Session-based order caching
- ⚡ Real-time order status updates

## Getting Started

### Prerequisites

- Python 3.8+
- MongoDB
- [Ollama](https://ollama.ai/) for LLM support

### Environment Variables

```bash
# MongoDB Configuration
export MCP_MONGODB_URI="your_mongodb_uri"
export MCP_DATABASE="customer_support"

# LLM Configuration
export OLLAMA_API_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3:0.6b"

# Server Configuration
export PORT=5001  # Optional, defaults to 5001
```

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/silicon-stack-mcp-server.git
cd silicon-stack-mcp-server
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start the server:
```bash
python app.py
```

5. Open the web interface:
```
http://localhost:5001/static/index.html
```

## API Documentation

### MCP Tools

1. `get_order_status`
   - Input: `{"order_number": "ORD-YYYY-NNN"}`
   - Returns full order details

2. `get_order_history_by_email`
   - Input: `{"email": "user@example.com", "limit": 10}`
   - Returns list of orders for the email

### Chat Interface

POST `/mcp/chat`
- Input: 
  ```json
  {
    "message": "What's the total cost?",
    "context": {
      "type": "order|email",
      "order": {...} | "orders": [...]
    }
  }
  ```
- Returns AI-generated response about the order(s)

## Project Structure

```
silicon-stack-mcp-server/
├── app.py              # FastAPI server
├── assistant.py        # CLI assistant
├── mcp_client.py      # MCP client library
├── requirements.txt    # Python dependencies
├── static/            # Web interface
│   ├── index.html    # Main page
│   ├── styles.css    # Styling
│   └── app.js        # Frontend logic
└── README.md
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.