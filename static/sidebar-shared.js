(function () {
    function hideAllMenuItems() {
        document.querySelectorAll('.sidebar-nav-item[data-menu-key]').forEach((item) => {
            item.style.display = 'none';
        });
    }

    function applyMenuVisibility(menuKeys) {
        const allowed = new Set(menuKeys || []);
        document.querySelectorAll('.sidebar-nav-item[data-menu-key]').forEach((item) => {
            const key = item.getAttribute('data-menu-key');
            item.style.display = allowed.has(key) ? '' : 'none';
        });
    }

    async function initMenuVisibility() {
        hideAllMenuItems();
        try {
            const resp = await fetch('/api/me/menu-permissions');
            const data = await resp.json();
            const menuKeys = data && data.success && data.data ? data.data.menu_keys : [];
            applyMenuVisibility(menuKeys);
        } catch (_error) {
            applyMenuVisibility(['index']);
        }
    }

    async function initSharedSidebarProjectSwitcher() {
        const select = document.getElementById('sidebarProjectSelect');
        if (!select) return;

        try {
            const resp = await fetch('/api/projects');
            const data = await resp.json();
            if (!data.success) {
                select.innerHTML = '<option value="">项目加载失败</option>';
                return;
            }

            const projects = data.projects || [];
            const currentProjectId = String(data.current_project_id || '');
            if (!projects.length) {
                select.innerHTML = '<option value="">暂无项目</option>';
                return;
            }

            select.innerHTML = projects.map((project) => {
                const selected = String(project.id) === currentProjectId ? ' selected' : '';
                return `<option value="${project.id}"${selected}>${project.name}</option>`;
            }).join('');

            select.addEventListener('change', async (event) => {
                const projectId = event.target.value;
                const switchResp = await fetch('/api/projects/switch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_id: projectId }),
                });
                const switchData = await switchResp.json();
                if (!switchResp.ok || !switchData.success) {
                    alert(switchData.error || '切换项目失败');
                    return;
                }
                window.location.reload();
            });
        } catch (_error) {
            select.innerHTML = '<option value="">项目加载失败</option>';
        }
    }

    window.initSharedSidebarProjectSwitcher = initSharedSidebarProjectSwitcher;
    window.initSidebarRoleVisibility = initMenuVisibility;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initMenuVisibility();
            initSharedSidebarProjectSwitcher();
        });
    } else {
        initMenuVisibility();
        initSharedSidebarProjectSwitcher();
    }
})();
