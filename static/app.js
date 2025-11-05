// Configuration
const MCP_BASE_URL = 'http://localhost:5001';
const ORDER_NUMBER_PATTERN = /^ORD-\d{4}-\d{3}$/;
const EMAIL_PATTERN = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

// Chat context
let currentOrderContext = null;

// DOM Elements
const searchForm = document.getElementById('searchForm');
const searchInput = document.getElementById('searchInput');
const errorAlert = document.getElementById('errorAlert');
const resultsCard = document.getElementById('resultsCard');
const ordersList = document.getElementById('ordersList');
const orderTemplate = document.getElementById('orderTemplate');
const chatInterface = document.getElementById('chatInterface');
const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const messageTemplate = document.getElementById('messageTemplate');

// Helper Functions
function formatCurrency(value) {
    if (value === null || value === undefined) return '(no total)';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

function formatDate(dateStr) {
    if (!dateStr) return '(no date)';
    return new Date(dateStr).toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric'
    });
}

function getStatusBadgeClass(status) {
    status = status.toLowerCase();
    if (status.includes('pend')) return 'pending';
    if (status.includes('ship')) return 'shipped';
    if (status.includes('deliver')) return 'delivered';
    if (status.includes('cancel')) return 'cancelled';
    return 'secondary';
}

function showError(message) {
    errorAlert.textContent = message;
    errorAlert.classList.remove('d-none');
    resultsCard.classList.add('d-none');
}

function clearError() {
    errorAlert.classList.add('d-none');
}

function setLoading(isLoading) {
    const spinner = searchForm.querySelector('.spinner-border');
    const button = searchForm.querySelector('button');
    if (isLoading) {
        spinner.classList.remove('d-none');
        button.disabled = true;
        searchInput.disabled = true;
    } else {
        spinner.classList.add('d-none');
        button.disabled = false;
        searchInput.disabled = false;
    }
}

// Create order card from template
function createOrderCard(order) {
    const template = orderTemplate.content.cloneNode(true);
    const card = template.querySelector('.order-item');
    
    // Order number and status
    card.querySelector('.order-number').textContent = order.order_number;
    const statusBadge = card.querySelector('.status-badge');
    statusBadge.textContent = order.status;
    statusBadge.classList.add(getStatusBadgeClass(order.status));
    
    // Basic order details
    card.querySelector('.order-total').textContent = `Total: ${formatCurrency(order.total_amount)}`;
    card.querySelector('.order-date').textContent = `Order Date: ${formatDate(order.order_date)}`;
    
    // Items
    if (order.items && order.items.length > 0) {
        const itemsList = card.querySelector('.order-items');
        itemsList.innerHTML = order.items.map(item => {
            const qty = item.qty || item.quantity || 1;
            const price = item.price || item.unit_price || item.amount;
            return `${item.name || item.sku} (${qty} x ${formatCurrency(price)})`;
        }).join('<br>');
    }
    
    // Shipping info
    const shippingInfo = card.querySelector('.shipping-info');
    if (order.shipping_address) {
        let addr = order.shipping_address;
        if (typeof addr === 'object') {
            addr = [
                addr.line1 || addr.street,
                addr.city,
                addr.state,
                addr.postal_code || addr.zip,
                addr.country
            ].filter(Boolean).join(', ');
        }
        shippingInfo.innerHTML = `<strong>Shipping to:</strong> ${addr}`;
    }
    
    // Tracking info
    const trackingInfo = card.querySelector('.tracking-info');
    const tracking = order.tracking_number || order.tracking;
    if (tracking) {
        trackingInfo.innerHTML = `<strong>Tracking:</strong> ${tracking}`;
    }
    
    // Notes
    const notesDiv = card.querySelector('.order-notes');
    const notes = order.notes || order.customer_notes;
    if (notes) {
        notesDiv.textContent = notes;
    } else {
        notesDiv.remove();
    }
    
    return card;
}

// Display order results
function displayResults(data, searchType) {
    clearError();
    resultsCard.classList.remove('d-none');
    ordersList.innerHTML = '';
    
    if (searchType === 'email') {
        // Display email search results
        const orders = data.orders || [];
        if (orders.length === 0) {
            showError(`No orders found for ${data.email}`);
            return;
        }
        
        // Set customer info
        resultsCard.querySelector('.customer-name').textContent = 
            `Orders for ${data.email}`;
        resultsCard.querySelector('.customer-email').textContent = 
            `${orders.length} order${orders.length === 1 ? '' : 's'} found`;
        
        // Display each order
        orders.forEach(order => {
            ordersList.appendChild(createOrderCard(order));
        });
    } else {
        // Display single order result
        if (data.error) {
            showError(`Order not found: ${data.order_number}`);
            return;
        }
        
        // Set customer info
        resultsCard.querySelector('.customer-name').textContent = 
            data.customer_name || 'Order Details';
        resultsCard.querySelector('.customer-email').textContent = 
            data.customer_email || '';
        
        // Display the order
        ordersList.appendChild(createOrderCard(data));
    }
}

// Handle form submission
searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = searchInput.value.trim();
    
    // Validate input
    if (!query) {
        showError('Please enter an order number or email address');
        return;
    }
    
    let tool, args;
    if (ORDER_NUMBER_PATTERN.test(query.toUpperCase())) {
        tool = 'get_order_status';
        args = { order_number: query.toUpperCase() };
    } else if (EMAIL_PATTERN.test(query.toLowerCase())) {
        tool = 'get_order_history_by_email';
        args = { email: query.toLowerCase(), limit: 10 };
    } else {
        showError('Please enter a valid order number (ORD-YYYY-NNN) or email address');
        return;
    }
    
    // Call MCP API
    try {
        setLoading(true);
        const response = await fetch(`${MCP_BASE_URL}/mcp/invoke`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool, args })
        });
        
        if (!response.ok) {
            throw new Error('Server error');
        }
        
        const data = await response.json();
        displayResults(data, tool === 'get_order_history_by_email' ? 'email' : 'order');
    } catch (err) {
        showError('Could not reach order service. Please try again in a few minutes.');
        console.error('API Error:', err);
    } finally {
        setLoading(false);
    }
});

// Chat Functions
function addMessage(content, isUser = false) {
    const template = messageTemplate.content.cloneNode(true);
    const message = template.querySelector('.chat-message');
    const messageContent = message.querySelector('.message-content');
    const messageTime = message.querySelector('.message-time');
    
    message.classList.add(isUser ? 'user' : 'assistant');
    messageContent.textContent = content;
    messageTime.textContent = new Date().toLocaleTimeString();
    
    chatMessages.appendChild(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator chat-message assistant';
    indicator.innerHTML = '<span></span><span></span><span></span>';
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return indicator;
}

async function handleChatMessage(message) {
    if (!currentOrderContext) {
        addMessage("Please search for an order first!", false);
        return;
    }

    try {
        const typing = showTypingIndicator();
        
        const response = await fetch(`${MCP_BASE_URL}/mcp/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                context: currentOrderContext
            })
        });
        
        typing.remove();
        
        if (!response.ok) {
            throw new Error('Chat API error');
        }
        
        const data = await response.json();
        addMessage(data.response, false);
    } catch (err) {
        console.error('Chat error:', err);
        addMessage("Sorry, I had trouble processing that. Please try again.", false);
    }
}

// Handle chat form submission
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    
    addMessage(message, true);
    chatInput.value = '';
    
    await handleChatMessage(message);
});

// Update displayResults to store context and show chat
function displayResults(data, searchType) {
    clearError();
    resultsCard.classList.remove('d-none');
    ordersList.innerHTML = '';
    chatMessages.innerHTML = '';
    
    if (searchType === 'email') {
        // Store multiple orders context
        currentOrderContext = {
            type: 'email',
            email: data.email,
            orders: data.orders || []
        };
        
        const orders = data.orders || [];
        if (orders.length === 0) {
            showError(`No orders found for ${data.email}`);
            chatInterface.classList.add('d-none');
            return;
        }
        
        // Set customer info
        resultsCard.querySelector('.customer-name').textContent = 
            `Orders for ${data.email}`;
        resultsCard.querySelector('.customer-email').textContent = 
            `${orders.length} order${orders.length === 1 ? '' : 's'} found`;
        
        // Display each order
        orders.forEach(order => {
            ordersList.appendChild(createOrderCard(order));
        });
    } else {
        // Store single order context
        currentOrderContext = {
            type: 'order',
            order: data
        };
        
        if (data.error) {
            showError(`Order not found: ${data.order_number}`);
            chatInterface.classList.add('d-none');
            return;
        }
        
        // Set customer info
        resultsCard.querySelector('.customer-name').textContent = 
            data.customer_name || 'Order Details';
        resultsCard.querySelector('.customer-email').textContent = 
            data.customer_email || '';
        
        // Display the order
        ordersList.appendChild(createOrderCard(data));
    }
    
    // Show chat interface
    chatInterface.classList.remove('d-none');
    
    // Add welcome message
    addMessage('How can I help you with this order? You can ask about status, items, shipping, or any other details.', false);
}