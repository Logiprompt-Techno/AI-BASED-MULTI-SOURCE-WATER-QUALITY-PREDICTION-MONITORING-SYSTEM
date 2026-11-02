// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', () => {
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        setTimeout(() => {
            alerts.forEach(alert => {
                alert.style.transition = 'opacity 0.5s ease';
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 500);
            });
        }, 5000);
    }
});

// Render Dashboard Charts if element exists
function renderCharts(statsData) {
    // Colors
    const safeColor = 'rgba(16, 185, 129, 0.8)';
    const unsafeColor = 'rgba(239, 68, 68, 0.8)';
    const sourceColors = [
        'rgba(59, 130, 246, 0.8)',
        'rgba(139, 92, 246, 0.8)',
        'rgba(236, 72, 153, 0.8)',
        'rgba(245, 158, 11, 0.8)',
        'rgba(16, 185, 129, 0.8)'
    ];

    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';

    // Pie Chart: Safe vs Unsafe
    const pieCtx = document.getElementById('statusChart');
    if (pieCtx) {
        new Chart(pieCtx, {
            type: 'doughnut',
            data: {
                labels: ['SAFE', 'UNSAFE'],
                datasets: [{
                    data: [statsData.safe, statsData.unsafe],
                    backgroundColor: [safeColor, unsafeColor],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }

    // Monthly Predictions Bar Chart
    const monthlyCtx = document.getElementById('monthlyChart');
    if (monthlyCtx) {
        new Chart(monthlyCtx, {
            type: 'bar',
            data: {
                labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
                datasets: [{
                    label: 'Predictions',
                    data: statsData.monthly,
                    backgroundColor: 'rgba(59, 130, 246, 0.8)',
                    borderRadius: 4
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }
    
    // WQI Trend Line Chart
    const trendCtx = document.getElementById('wqiTrendChart');
    if (trendCtx && statsData.wqi_trend) {
        new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: statsData.wqi_trend.map((_, i) => `T-${statsData.wqi_trend.length - i}`),
                datasets: [{
                    label: 'WQI Score',
                    data: statsData.wqi_trend,
                    borderColor: 'rgba(139, 92, 246, 0.8)',
                    tension: 0.4,
                    fill: true,
                    backgroundColor: 'rgba(139, 92, 246, 0.2)'
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    // Parameter Comparison
    const paramCtx = document.getElementById('paramChart');
    if (paramCtx && statsData.param_comparison) {
        const pLabels = Object.keys(statsData.param_comparison).map(k => k.toUpperCase());
        const pData = Object.values(statsData.param_comparison);
        new Chart(paramCtx, {
            type: 'radar',
            data: {
                labels: pLabels,
                datasets: [{
                    label: 'Avg Values',
                    data: pData,
                    borderColor: 'rgba(16, 185, 129, 0.8)',
                    backgroundColor: 'rgba(16, 185, 129, 0.4)'
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }
}

// ===== NEW FEATURES =====

function showLoader() {
    const l = document.getElementById('global-loader');
    if (l) l.style.display = 'flex';
}

function hideLoader() {
    const l = document.getElementById('global-loader');
    if (l) l.style.display = 'none';
}

document.addEventListener('submit', function() {
    showLoader();
});


// AI Chat Widget
function toggleChat() {
    const body = document.getElementById('chatBody');
    const icon = document.getElementById('chatToggleIcon');
    if (body.style.display === 'none') {
        body.style.display = 'flex';
        icon.classList.replace('fa-chevron-up', 'fa-chevron-down');
    } else {
        body.style.display = 'none';
        icon.classList.replace('fa-chevron-down', 'fa-chevron-up');
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    
    input.value = '';
    const messages = document.getElementById('chatMessages');
    
    const userDiv = document.createElement('div');
    userDiv.className = 'message user';
    userDiv.innerText = msg;
    messages.appendChild(userDiv);
    messages.scrollTop = messages.scrollHeight;
    
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({message: msg})
        });
        const data = await res.json();
        
        const aiDiv = document.createElement('div');
        aiDiv.className = 'message ai';
        aiDiv.innerText = data.response;
        messages.appendChild(aiDiv);
        messages.scrollTop = messages.scrollHeight;
    } catch (e) {
        console.error(e);
    }
}

// Bfcache reload logic for back/forward navigation protection
window.addEventListener('pageshow', function (event) {
    if (event.persisted || (window.performance && window.performance.navigation.type === 2)) {
        window.location.reload();
    }
});
