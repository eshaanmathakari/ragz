// Configuration
const CONFIG = {
    uploadUrl: 'https://eshaanmathakari.app.n8n.cloud/form/cab3dda4-3b49-4f05-a2c1-915ae4c62017',
    chatUrl: 'https://eshaanmathakari.app.n8n.cloud/webhook/c1f8d15b-e096-47f8-922e-a7484ebbc25c/chat',
    sessionId: 'user-' + Math.random().toString(36).substr(2, 9)
};

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadStatus = document.getElementById('uploadStatus');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const chatContainer = document.getElementById('chatContainer');

// Upload Area Interactions
uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
        handleFileUpload(files[0]);
    } else {
        showStatus('Please drop a PDF file', 'error');
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

// File Upload Handler
async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    showStatus(`Uploading ${file.name}...`, 'loading');
    
    try {
        const response = await fetch(CONFIG.uploadUrl, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            showStatus(`✓ ${file.name} uploaded successfully`, 'success');
            fileInput.value = '';
            
            // Clear welcome message if exists
            const welcomeMsg = chatContainer.querySelector('.welcome-message');
            if (welcomeMsg) {
                welcomeMsg.remove();
            }
            
            // Add system message
            addMessage('bot', `Document "${file.name}" has been processed and added to the knowledge base. You can now ask questions about it.`);
        } else {
            showStatus('Upload failed. Please try again.', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showStatus('Connection error. Please check your network.', 'error');
    }
}

// Chat Form Handler
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const message = chatInput.value.trim();
    if (!message) return;
    
    // Add user message
    addMessage('user', message);
    chatInput.value = '';
    sendBtn.disabled = true;
    
    // Show typing indicator
    const typingId = showTypingIndicator();
    
    try {
        const response = await fetch(CONFIG.chatUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chatInput: message,
                sessionId: CONFIG.sessionId
            })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator(typingId);
        
        // Add bot response
        const botResponse = data.output || 'Sorry, I could not process your request.';
        addMessage('bot', botResponse);
        
    } catch (error) {
        console.error('Chat error:', error);
        removeTypingIndicator(typingId);
        addMessage('bot', 'Connection error. Please try again.');
    } finally {
        sendBtn.disabled = false;
        chatInput.focus();
    }
});

// Add Message to Chat
function addMessage(type, text) {
    // Remove welcome message if it exists
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = type === 'user' ? '👤' : '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text;
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Typing Indicator
function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot';
    typingDiv.id = 'typing-indicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    
    content.appendChild(typingIndicator);
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(content);
    
    chatContainer.appendChild(typingDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    return 'typing-indicator';
}

function removeTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) {
        indicator.remove();
    }
}

// Status Message
function showStatus(message, type) {
    uploadStatus.textContent = message;
    uploadStatus.className = `status-message ${type}`;
    uploadStatus.style.display = 'block';
    
    if (type === 'success') {
        setTimeout(() => {
            uploadStatus.style.display = 'none';
        }, 5000);
    }
}

// Auto-focus chat input
chatInput.focus();
