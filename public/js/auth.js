// Auth utility - shared across all authenticated pages

const API_BASE = '';

function getToken() {
    return localStorage.getItem('token');
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('user'));
    } catch { return null; }
}

function requireAuth() {
    if (!getToken()) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = 'login.html';
}

async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...(options.headers || {})
    };

    try {
        const res = await fetch(API_BASE + url, { ...options, headers });
        if (res.status === 401) {
            logout();
            return null;
        }
        return res;
    } catch (e) {
        console.error('API Error:', e);
        showToast('网络错误，请检查连接', 'error');
        return null;
    }
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span style="font-size:1.2rem;">${type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️'}</span>
        <span style="flex:1;font-size:0.9rem;">${message}</span>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;">✕</button>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function initNav() {
    const user = getUser();
    if (!user) return;

    const nameEl = document.getElementById('nav-username');
    const avatarEl = document.getElementById('nav-avatar');

    if (nameEl) nameEl.textContent = user.real_name || user.username;
    if (avatarEl) avatarEl.textContent = (user.real_name || user.username).charAt(0);

    // Show admin nav
    if (user.role === 'admin' || user.role === 'doctor') {
        const adminNav = document.getElementById('admin-nav');
        if (adminNav) adminNav.style.display = 'block';
    }

    // Update alert badge
    updateAlertBadge();
}

async function updateAlertBadge() {
    const res = await apiFetch('/api/alerts/active-count');
    if (!res) return;
    const data = await res.json();
    const badge = document.getElementById('nav-alert-badge');
    if (badge && data.count > 0) {
        badge.textContent = `${data.count} 报警`;
        badge.style.display = 'inline';
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDateTime(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatTime(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// Auto-init on page load
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname !== '/' &&
        window.location.pathname !== '/index.html' &&
        window.location.pathname !== '/login.html') {
        if (!requireAuth()) return;
        initNav();
    }
});
