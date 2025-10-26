// FiMesh JavaScript functionality

let websocket = null;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    fetchTransfers();
    connectWebSocket();

    // Handle form submission
    document.getElementById('uploadForm').addEventListener('submit', handleUpload);
});

// Fetch transfers from API
async function fetchTransfers() {
    try {
        const response = await fetch('/api/v1/fimesh/transfers');
        const transfers = await response.json();

        updateActiveTransfersTable(transfers.filter(t => t.status === 'active' || t.status === 'in_progress'));
        updateTransferHistoryTable(transfers.filter(t => t.status !== 'active' && t.status !== 'in_progress'));
    } catch (error) {
        console.error('Error fetching transfers:', error);
        showError('Failed to load transfers');
    }
}

// Establish WebSocket connection
function connectWebSocket() {
    websocket = new WebSocket(`ws://${window.location.host}/ws/map`);

    websocket.onopen = function(event) {
        console.log('WebSocket connected for FiMesh updates');
    };

    websocket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'fimesh_update') {
            handleFimeshUpdate(data.data);
        }
    };

    websocket.onclose = function(event) {
        console.log('WebSocket disconnected, attempting to reconnect...');
        setTimeout(connectWebSocket, 5000);
    };

    websocket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
}

// Handle FiMesh update messages
function handleFimeshUpdate(data) {
    console.log('Received FiMesh update:', data);
    // Refresh transfers after update
    fetchTransfers();
}

// Handle file upload
async function handleUpload(event) {
    event.preventDefault();

    const formData = new FormData();
    const fileInput = document.getElementById('fileInput');
    const nodeIdInput = document.getElementById('nodeIdInput');

    formData.append('file', fileInput.files[0]);
    formData.append('node_id', nodeIdInput.value);

    try {
        const response = await fetch('/api/v1/fimesh/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showSuccess('File uploaded successfully');
            // Reset form
            fileInput.value = '';
            nodeIdInput.value = '';
            // Refresh transfers
            fetchTransfers();
        } else {
            showError('Upload failed: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Upload error:', error);
        showError('Upload failed');
    }
}

// Handle cancel button clicks
async function cancelTransfer(sessionId) {
    try {
        const response = await fetch(`/api/v1/fimesh/transfers/${sessionId}/cancel`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showSuccess('Transfer cancelled');
            fetchTransfers();
        } else {
            showError('Failed to cancel transfer');
        }
    } catch (error) {
        console.error('Cancel error:', error);
        showError('Failed to cancel transfer');
    }
}

// Update active transfers table
function updateActiveTransfersTable(transfers) {
    const tbody = document.querySelector('#activeTransfersTable tbody');
    tbody.innerHTML = '';

    transfers.forEach(transfer => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${transfer.filename || 'Unknown'}</td>
            <td>${transfer.direction || 'Unknown'}</td>
            <td>${transfer.status || 'Unknown'}</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${transfer.progress || 0}%"></div>
                    <span class="progress-text">${transfer.progress || 0}%</span>
                </div>
            </td>
            <td>${transfer.window_size || 'N/A'}</td>
            <td>${transfer.from_node || 'N/A'} → ${transfer.to_node || 'N/A'}</td>
            <td>
                <button onclick="cancelTransfer('${transfer.session_id}')" class="btn btn-danger btn-sm">Cancel</button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

// Update transfer history table
function updateTransferHistoryTable(transfers) {
    const tbody = document.querySelector('#transferHistoryTable tbody');
    tbody.innerHTML = '';

    transfers.forEach(transfer => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${transfer.filename || 'Unknown'}</td>
            <td>${transfer.direction || 'Unknown'}</td>
            <td>${transfer.status || 'Unknown'}</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${transfer.progress || 0}%"></div>
                    <span class="progress-text">${transfer.progress || 0}%</span>
                </div>
            </td>
            <td>${transfer.window_size || 'N/A'}</td>
            <td>${transfer.from_node || 'N/A'} → ${transfer.to_node || 'N/A'}</td>
            <td>${transfer.timestamp || 'Unknown'}</td>
        `;

        tbody.appendChild(row);
    });
}

// Utility functions for notifications (assuming they exist globally)
function showSuccess(message) {
    if (typeof window.showSuccess === 'function') {
        window.showSuccess(message);
    } else {
        alert('Success: ' + message);
    }
}

function showError(message) {
    if (typeof window.showError === 'function') {
        window.showError(message);
    } else {
        alert('Error: ' + message);
    }
}