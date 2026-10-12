// Multi-Tab & AI Management System for Financial Engineer ERP

const openTabsState = {};

function toggleAI() {
    const aiWindow = document.getElementById('ai-chat-window');
    if (aiWindow) {
        aiWindow.classList.toggle('ai-hidden');
    }
}

function openTab(tabId, tabTitle, contentUrl) {
    const headerContainer = document.getElementById('tab-headers');
    const bodyContainer = document.getElementById('tab-body');
    if (!headerContainer || !bodyContainer) return;

    // إلغاء تنشيط جميع التبويبات المفتوحة
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    // التحقق إذا كان التبويب موجوداً مسبقاً
    let tabBtn = document.getElementById('tab-btn-' + tabId);
    if (!tabBtn) {
        tabBtn = document.createElement('div');
        tabBtn.id = 'tab-btn-' + tabId;
        tabBtn.className = 'tab-btn active d-flex align-items-center gap-2';
        tabBtn.innerHTML = `
            <span class="tab-title" onclick="switchTab('${tabId}', '${contentUrl}')">${tabTitle}</span>
            <span class="tab-close" onclick="closeTab('${tabId}', event)">&times;</span>
        `;
        headerContainer.appendChild(tabBtn);
    } else {
        tabBtn.classList.add('active');
    }

    loadContent(contentUrl, tabId);
}

function switchTab(tabId, contentUrl) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const tabBtn = document.getElementById('tab-btn-' + tabId);
    if (tabBtn) tabBtn.classList.add('active');

    const bodyContainer = document.getElementById('tab-body');
    if (openTabsState[tabId]) {
        bodyContainer.innerHTML = openTabsState[tabId];
    } else {
        loadContent(contentUrl, tabId);
    }
}

function closeTab(tabId, event) {
    if (event) event.stopPropagation();
    const tabBtn = document.getElementById('tab-btn-' + tabId);
    if (tabBtn) tabBtn.remove();
    delete openTabsState[tabId];

    // تفعيل التبويب السابق إن وجد
    const remainingTabs = document.querySelectorAll('.tab-btn');
    if (remainingTabs.length > 0) {
        remainingTabs[remainingTabs.length - 1].click();
    } else {
        const bodyContainer = document.getElementById('tab-body');
        bodyContainer.innerHTML = '<div class="p-5 text-center text-muted"><h4>مرحباً بك في Financial Engineer ERP</h4><p>اختر قسماً من القائمة الجانبية للبدء.</p></div>';
    }
}

async function loadContent(url, tabId) {
    const bodyContainer = document.getElementById('tab-body');
    bodyContainer.innerHTML = '<div class="p-5 text-center"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted">جاري تحميل البيانات...</div></div>';
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("تعذر جلب البيانات");
        const html = await response.text();
        bodyContainer.innerHTML = html;
        if (tabId) openTabsState[tabId] = html;
        
        // Execute any script tags in loaded content
        bodyContainer.querySelectorAll("script").forEach(oldScript => {
            const newScript = document.createElement("script");
            Array.from(oldScript.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
            newScript.appendChild(document.createTextNode(oldScript.innerHTML));
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
    } catch (e) {
        bodyContainer.innerHTML = `<div class="p-4 text-center text-danger"><i class="fas fa-exclamation-triangle fa-2x mb-2"></i><br>خطأ في تحميل المحتوى: ${e.message}</div>`;
    }
}

async function sendToAI() {
    const input = document.getElementById('ai-input');
    const messages = document.getElementById('ai-messages');
    const text = input ? input.value.trim() : '';
    if (!text) return;

    messages.innerHTML += `<div class="user-msg p-2 mb-2 bg-light rounded text-end"><b>أنت:</b> ${text}</div>`;
    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    const loadingId = 'ai-loading-' + Date.now();
    messages.innerHTML += `<div id="${loadingId}" class="ai-msg p-2 mb-2 bg-primary-subtle rounded text-start"><i class="fas fa-spinner fa-spin"></i> جاري التحليل والمعالجة...</div>`;
    messages.scrollTop = messages.scrollHeight;

    try {
        const response = await fetch('/api/ai/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({query: text})
        });
        const data = await response.json();
        const loadElem = document.getElementById(loadingId);
        if (loadElem) loadElem.remove();

        messages.innerHTML += `<div class="ai-msg p-2 mb-2 bg-primary-subtle rounded text-start"><b>المساعد المالي:</b><br>${data.reply}</div>`;
    } catch (err) {
        const loadElem = document.getElementById(loadingId);
        if (loadElem) loadElem.remove();
        messages.innerHTML += `<div class="ai-msg p-2 mb-2 bg-danger-subtle text-danger rounded">حدث خطأ في الاتصال بالمساعد الذكي.</div>`;
    }
    messages.scrollTop = messages.scrollHeight;
}

// إضافة حدث الضغط على Enter في إدخال الذكاء الاصطناعي
document.addEventListener('DOMContentLoaded', () => {
    const aiInput = document.getElementById('ai-input');
    if (aiInput) {
        aiInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendToAI();
        });
    }

    // فتح تبويب لوحة التحكم افتراضياً
    openTab('dashboard', 'لوحة التحكم', '/api/dashboard/stats');
});
