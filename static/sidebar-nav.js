// 侧边栏导航栏通用JavaScript
function toggleSidebar() {
    const sidebar = document.getElementById('sidebarNav');
    const toggleIcon = document.getElementById('toggleIcon');
    if (sidebar && toggleIcon) {
        sidebar.classList.toggle('collapsed');
        toggleIcon.textContent = sidebar.classList.contains('collapsed') ? '›' : '‹';
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    }
}

async function applySidebarRoleMenuVisibility() {
    let menuKeys = ['index'];
    try {
        const resp = await fetch('/api/me/menu-permissions');
        const data = await resp.json();
        if (data && data.success && data.data && Array.isArray(data.data.menu_keys)) {
            menuKeys = data.data.menu_keys;
        }
    } catch (_err) {}
    const allowed = new Set(menuKeys);
    document.querySelectorAll('.sidebar-nav-item[data-menu-key]').forEach((item) => {
        const key = item.getAttribute('data-menu-key');
        item.style.display = allowed.has(key) ? '' : 'none';
    });
}

// 页面加载时恢复侧边栏状态
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebarNav');
    const toggleIcon = document.getElementById('toggleIcon');
    if (sidebar && toggleIcon) {
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            toggleIcon.textContent = '›';
        }

        // 更新当前页面的导航项active状态
        const currentPath = window.location.pathname;
        document.querySelectorAll('.sidebar-nav-item').forEach(item => {
            item.classList.remove('active');
            if (item.getAttribute('href') === currentPath) {
                item.classList.add('active');
            }
        });
    }

    applySidebarRoleMenuVisibility();
});
