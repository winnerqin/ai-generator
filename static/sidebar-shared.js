(function () {
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSharedSidebarProjectSwitcher);
    } else {
        initSharedSidebarProjectSwitcher();
    }
})();
