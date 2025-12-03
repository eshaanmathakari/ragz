// Configuration
const CONFIG = {
    // n8n connection - try proxy first, then fallback to direct
    // Proxy avoids CORS issues when frontend and n8n are on different origins
    get N8N_BASE_URL() {
        // Try to use proxy if available (when served from same origin)
        const useProxy = window.location.port === '8080' || window.location.hostname === 'localhost';
        if (useProxy) {
            // Try proxy first (nginx proxy)
            return `${window.location.protocol}//${window.location.host}/api/n8n`;
        }
        // Fallback to direct connection
        return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:5678'
            : `http://${window.location.hostname}:5678`;
    },
    
    // Direct n8n URL for connection checks
    get N8N_DIRECT_URL() {
        return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:5678'
            : `http://${window.location.hostname}:5678`;
    },
    
    // Webhook IDs from the workflow (verified from n8n)
    // Chat URL: http://localhost:5678/webhook/c1f8d15b-e096-47f8-922e-a7484ebbc25c/chat
    // Form URL: http://localhost:5678/webhook/cab3dda4-3b49-4f05-a2c1-915ae4c62017
    WEBHOOKS: {
        FORM_UPLOAD: 'cab3dda4-3b49-4f05-a2c1-915ae4c62017',
        // Chat webhook ID (we append /chat in the code)
        CHAT_MESSAGE: 'c1f8d15b-e096-47f8-922e-a7484ebbc25c'
    },
    
    // Workflow ID (from rag-workflow.json)
    // Some n8n webhook formats require the workflow ID
    WORKFLOW_ID: 'T7QP0aDxDoBUMEWj'
};

// State management
const state = {
    isUploading: false,
    isChatting: false,
    chatHistory: [],
    sessionId: null  // Session ID for n8n chat trigger
};

// Generate or retrieve session ID
function getSessionId() {
    if (!state.sessionId) {
        // Generate a unique session ID (UUID-like format)
        state.sessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        // Store in sessionStorage to persist across page refreshes
        sessionStorage.setItem('n8n_sessionId', state.sessionId);
        console.log('Generated new session ID:', state.sessionId);
    }
    return state.sessionId;
}

// Load session ID from sessionStorage on page load
function loadSessionId() {
    const stored = sessionStorage.getItem('n8n_sessionId');
    if (stored) {
        state.sessionId = stored;
        console.log('Loaded existing session ID:', state.sessionId);
    }
}

// DOM Elements
const elements = {
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    uploadStatus: document.getElementById('uploadStatus'),
    chatContainer: document.getElementById('chatContainer'),
    chatForm: document.getElementById('chatForm'),
    chatInput: document.getElementById('chatInput'),
    sendBtn: document.getElementById('sendBtn'),
    statusDot: document.querySelector('.status-dot'),
    statusText: document.querySelector('.status-text')
};

// Utility Functions
function showStatus(message, type = 'info') {
    elements.uploadStatus.textContent = message;
    elements.uploadStatus.className = `status-message ${type}`;
    elements.uploadStatus.style.display = 'block';
    
    if (type !== 'loading') {
        setTimeout(() => {
            elements.uploadStatus.style.display = 'none';
        }, 5000);
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        elements.statusDot.style.backgroundColor = 'var(--success)';
        elements.statusText.textContent = 'Connected';
    } else {
        elements.statusDot.style.backgroundColor = 'var(--error)';
        elements.statusText.textContent = 'Disconnected';
    }
}

function addMessage(content, isUser = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = isUser ? '👤' : '🤖';
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    messageContent.textContent = content;
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(messageContent);
    
    // Remove welcome message if it exists
    const welcomeMsg = elements.chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    elements.chatContainer.appendChild(messageDiv);
    elements.chatContainer.scrollTop = elements.chatContainer.scrollHeight;
    
    state.chatHistory.push({ content, isUser, timestamp: Date.now() });
}

function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot typing-indicator';
    typingDiv.id = 'typing-indicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';
    
    const typingContent = document.createElement('div');
    typingContent.className = 'typing-indicator';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.className = 'typing-dot';
        typingContent.appendChild(dot);
    }
    
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(typingContent);
    elements.chatContainer.appendChild(typingDiv);
    elements.chatContainer.scrollTop = elements.chatContainer.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

// API Functions
async function checkN8nConnection() {
    // Try direct connection first (more reliable)
    const directUrl = CONFIG.N8N_DIRECT_URL;
    const baseUrl = CONFIG.N8N_BASE_URL;
    
    // Try multiple endpoints to check n8n availability
    // Note: /healthz may have CORS issues, so we try form webhook first
    const endpoints = [
        { path: `/webhook/${CONFIG.WEBHOOKS.FORM_UPLOAD}`, method: 'GET' }, // Form webhook (most reliable, returns HTML)
        { path: '/rest/login', method: 'GET' }, // Login endpoint
        { path: '/healthz', method: 'GET' }  // Health check (may have CORS issues)
    ];
    
    // First try direct connection
    for (const endpoint of endpoints) {
        try {
            const response = await fetch(`${directUrl}${endpoint.path}`, {
                method: endpoint.method,
                mode: 'cors',
                credentials: 'omit',
                headers: {
                    'Accept': 'application/json, text/html, */*'
                }
            });
            
            // If we get any response (even 401/403/404), n8n is reachable
            // Status 0 means network error, anything else means server responded
            if (response.status !== 0 && response.status < 600) {
                console.log(`✅ n8n connection check successful via ${endpoint.path}:`, response.status);
                return true;
            }
        } catch (error) {
            // CORS or network error - try next endpoint
            console.log(`⚠️ n8n connection check failed for ${directUrl}${endpoint.path}:`, error.message);
            // Don't return false yet, try other endpoints
            continue;
        }
    }
    
    // If direct connection fails, try proxy
    if (baseUrl !== directUrl) {
        console.log('Trying proxy connection...');
        try {
            const response = await fetch(`${baseUrl}/healthz`, {
                method: 'GET',
                mode: 'cors',
                credentials: 'omit'
            });
            
            if (response.status !== 0 && response.status < 600) {
                console.log('✅ n8n connection check successful via proxy');
                return true;
            }
        } catch (error) {
            console.log('⚠️ Proxy connection also failed:', error.message);
        }
    }
    
    // Last resort: try a simple HEAD request to the base URL
    try {
        const response = await fetch(directUrl, {
            method: 'HEAD',
            mode: 'cors',
            credentials: 'omit'
        });
        if (response.status !== 0 && response.status < 600) {
            console.log('✅ n8n connection check successful via base URL');
            return true;
        }
    } catch (error) {
        console.log('⚠️ Base URL check also failed:', error.message);
    }
    
    console.error('❌ n8n connection check failed - n8n may not be accessible');
    return false;
}

async function uploadPDF(file) {
    if (state.isUploading) {
        showStatus('Upload already in progress...', 'error');
        return;
    }

    state.isUploading = true;
    showStatus('Uploading PDF...', 'loading');
    elements.uploadArea.style.pointerEvents = 'none';
    elements.uploadArea.style.opacity = '0.6';

    try {
        // Create FormData for file upload
        const formData = new FormData();
        formData.append('file', file);

        // n8n form trigger webhook URL
        // Try different webhook URL formats
        const webhookUrl = `${CONFIG.N8N_BASE_URL}/webhook/${CONFIG.WEBHOOKS.FORM_UPLOAD}`;
        
        console.log('Uploading to:', webhookUrl);
        console.log('File:', file.name, 'Size:', file.size, 'Type:', file.type);

        const response = await fetch(webhookUrl, {
            method: 'POST',
            body: formData,
            mode: 'cors',
            credentials: 'omit',
            // Don't set Content-Type - let browser set it with boundary for FormData
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const result = await response.json();
        console.log('Upload response:', result);

        showStatus('PDF uploaded successfully! Processing...', 'success');
        
        // Clear file input
        elements.fileInput.value = '';
        
        // Show success message in chat
        addMessage('PDF uploaded and indexed successfully! You can now ask questions about it.', false);
        
    } catch (error) {
        console.error('Upload error:', error);
        showStatus(`Upload failed: ${error.message}`, 'error');
        addMessage(`❌ Upload failed: ${error.message}`, false);
    } finally {
        state.isUploading = false;
        elements.uploadArea.style.pointerEvents = 'auto';
        elements.uploadArea.style.opacity = '1';
    }
}

async function sendChatMessage(message) {
    if (state.isChatting || !message.trim()) {
        return;
    }

    // Add user message to chat
    addMessage(message, true);
    
    // Clear input
    elements.chatInput.value = '';
    elements.sendBtn.disabled = true;
    state.isChatting = true;
    
    // Show typing indicator
    showTypingIndicator();

    try {
        // n8n chat trigger webhook URL
        // n8n chat triggers use the format: /webhook/{webhookId}/chat
        const webhookId = CONFIG.WEBHOOKS.CHAT_MESSAGE;
        const workflowId = CONFIG.WORKFLOW_ID;
        const baseUrl = CONFIG.N8N_BASE_URL;
        
        // n8n chat triggers use: /webhook/{webhookId}/chat
        // The webhookId should NOT include /chat - we append it here
        const webhookUrls = [
            `${baseUrl}/webhook/${webhookId}/chat`,  // Standard chat trigger format (CORRECT)
            `${baseUrl}/webhook/${webhookId}`,  // Fallback: without /chat
        ];
        
        let lastError = null;
        let response = null;
        
        // Try each URL format until one works
        for (const webhookUrl of webhookUrls) {
            try {
                console.log(`Trying webhook URL: ${webhookUrl}`);
                
                // n8n chat trigger requires sessionId in the request
                const sessionId = getSessionId();
                
                response = await fetch(webhookUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        sessionId: sessionId,  // REQUIRED by n8n chat trigger
                        chatInput: message,  // REQUIRED by AI Agent node - this is what it expects
                        question: message,  // Keep for compatibility
                        message: message,  // Keep for compatibility
                        chatHistory: state.chatHistory.slice(-5) // Send last 5 messages for context
                    }),
                    mode: 'cors',
                    credentials: 'omit'
                });

                // If we get a response (even error), this URL format is correct
                if (response.status !== 0) {
                    console.log(`✅ Webhook responded with status: ${response.status}`);
                    break;  // Found working URL format
                }
            } catch (error) {
                console.log(`⚠️ Webhook URL failed: ${webhookUrl} - ${error.message}`);
                lastError = error;
                continue;  // Try next URL format
            }
        }
        
        if (!response || response.status === 0) {
            throw new Error(`All webhook URL formats failed. Last error: ${lastError?.message || 'No response'}`);
        }

        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `Chat failed: ${response.status} ${response.statusText}`;
            
            // Provide helpful error messages
            if (response.status === 404) {
                errorMessage += `\n\n❌ Webhook not found. Please check:\n`;
                errorMessage += `1. Workflow is ACTIVE in n8n (toggle must be ON)\n`;
                errorMessage += `2. Chat trigger node is properly configured\n`;
                errorMessage += `3. Webhook ID matches: ${webhookId}\n`;
                errorMessage += `4. Open n8n UI and copy the actual webhook URL from the chat trigger node`;
            }
            
            if (errorText) {
                try {
                    const errorJson = JSON.parse(errorText);
                    if (errorJson.message) {
                        errorMessage += `\n\nn8n says: ${errorJson.message}`;
                    }
                } catch (e) {
                    errorMessage += `\n\nResponse: ${errorText.substring(0, 200)}`;
                }
            }
            
            throw new Error(errorMessage);
        }

        const result = await response.json();
        console.log('Chat response:', result);

        // Remove typing indicator
        removeTypingIndicator();

        // Extract response text from n8n response
        // n8n chat trigger/AI Agent returns response in 'output' field
        let responseText = '';
        if (result.output) {
            // AI Agent returns { output: "text" } or { output: { text: "..." } }
            if (typeof result.output === 'string') {
                responseText = result.output;
            } else if (result.output.text) {
                responseText = result.output.text;
            } else {
                responseText = JSON.stringify(result.output, null, 2);
            }
        } else if (result.text) {
            responseText = result.text;
        } else if (result.message) {
            responseText = result.message;
        } else if (typeof result === 'string') {
            responseText = result;
        } else {
            responseText = JSON.stringify(result, null, 2);
        }

        addMessage(responseText, false);

    } catch (error) {
        console.error('Chat error:', error);
        removeTypingIndicator();
        addMessage(`❌ Error: ${error.message}. Make sure n8n workflow is active and webhook is accessible.`, false);
    } finally {
        state.isChatting = false;
        elements.sendBtn.disabled = false;
        elements.chatInput.focus();
    }
}

// Event Listeners
elements.uploadArea.addEventListener('click', () => {
    elements.fileInput.click();
});

elements.uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    elements.uploadArea.classList.add('dragover');
});

elements.uploadArea.addEventListener('dragleave', () => {
    elements.uploadArea.classList.remove('dragover');
});

elements.uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    elements.uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
        uploadPDF(files[0]);
    } else {
        showStatus('Please upload a PDF file', 'error');
    }
});

elements.fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        if (file.type === 'application/pdf') {
            uploadPDF(file);
        } else {
            showStatus('Please select a PDF file', 'error');
            elements.fileInput.value = '';
        }
    }
});

elements.chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = elements.chatInput.value.trim();
    if (message && !state.isChatting) {
        sendChatMessage(message);
    }
});

elements.chatInput.addEventListener('input', () => {
    elements.sendBtn.disabled = !elements.chatInput.value.trim() || state.isChatting;
});

// Initialize
async function init() {
    console.log('Initializing RAGz frontend...');
    console.log('n8n URL:', CONFIG.N8N_BASE_URL);
    console.log('Frontend URL:', window.location.origin);
    
    // Load existing session ID or generate new one
    loadSessionId();
    getSessionId(); // Ensure we have a session ID
    
    // Check n8n connection with retry
    let connected = false;
    let retries = 3;
    
    while (!connected && retries > 0) {
        connected = await checkN8nConnection();
        if (!connected && retries > 1) {
            console.log(`Connection check failed, retrying... (${retries - 1} attempts left)`);
            await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds
        }
        retries--;
    }
    
    updateConnectionStatus(connected);
    
    if (!connected) {
        // Try one more time with a simpler check
        console.log('Final connection attempt with simple health check...');
        try {
            const healthCheck = await fetch(`${CONFIG.N8N_DIRECT_URL}/healthz`, {
                method: 'GET',
                mode: 'cors',
                credentials: 'omit'
            });
            if (healthCheck.status === 200 || healthCheck.status === 0) {
                // If we get here, n8n is reachable (even if CORS blocked the response)
                connected = true;
                console.log('✅ n8n is reachable (connection check passed)');
            }
        } catch (e) {
            console.log('Health check also failed:', e.message);
        }
    }
    
    updateConnectionStatus(connected);
    
    if (!connected) {
        const errorMsg = `⚠️ Cannot connect to n8n at ${CONFIG.N8N_DIRECT_URL}. 
        
Please check:
1. n8n is running: docker-compose ps
2. n8n is accessible: open http://localhost:5678 in browser
3. Check browser console (F12) for CORS errors
4. Try refreshing this page`;
        
        showStatus('⚠️ Cannot connect to n8n. Check console (F12) for details.', 'error');
        addMessage(errorMsg, false);
        console.error('n8n connection failed. Troubleshooting:', {
            n8nUrl: CONFIG.N8N_DIRECT_URL,
            frontendUrl: window.location.origin,
            suggestion: 'Open browser DevTools (F12) and check Console/Network tabs'
        });
    } else {
        showStatus('✅ Connected to n8n', 'success');
        console.log('✅ Successfully connected to n8n');
        // Remove any error messages if connection is successful
        const errorMsg = elements.chatContainer.querySelector('.message.bot');
        if (errorMsg && errorMsg.textContent.includes('Cannot connect')) {
            errorMsg.remove();
        }
    }
    
    // Focus chat input
    elements.chatInput.focus();
    
    console.log('Frontend initialized');
}

// Start the application
document.addEventListener('DOMContentLoaded', init);
