(function () {
    function menuItem(props, item) {
        return React.createElement(
            'a',
            {
                href: item.href,
                className: 'sidebar-nav-item' + (props.activePage === item.key ? ' active' : ''),
            },
            React.createElement('span', { className: 'sidebar-nav-icon', 'aria-hidden': 'true' }, item.icon),
            React.createElement('span', { className: 'sidebar-nav-text' }, item.label)
        );
    }

    function ProjectSwitcher(props) {
        return React.createElement(
            'div',
            { style: { marginTop: '8px' } },
            React.createElement(
                'label',
                { style: { fontSize: '0.85em', color: '#cbd4f5' } },
                '当前项目'
            ),
            React.createElement(
                'select',
                {
                    style: { width: '100%', padding: '6px', borderRadius: '6px' },
                    value: props.currentProjectId || '',
                    onChange: (e) => props.onProjectChange && props.onProjectChange(e.target.value),
                },
                (!props.projects || props.projects.length === 0)
                    ? React.createElement('option', null, '加载中...')
                    : props.projects.map((p) => React.createElement('option', { key: p.id, value: p.id }, p.name))
            )
        );
    }

    function AppSidebar(props) {
        const items = [
            { key: 'index', href: '/', icon: '🎨', label: '单图生成' },
            { key: 'batch', href: '/batch', icon: '📦', label: '批量生成' },
            { key: 'records', href: '/records', icon: '🖼️', label: '生图任务' },
            { key: 'video_generate', href: '/video-generate', icon: '🎬', label: '视频生成' },
            { key: 'video_tasks', href: '/video-tasks', icon: '📹', label: '视频任务' },
            { key: 'omni_video', href: '/omni-video', icon: '🎥', label: '全能视频' },
            { key: 'omni_video_tasks', href: '/omni-video-tasks', icon: '🗂️', label: '全能任务' },
            { key: 'script_generate', href: '/script-generate', icon: '📝', label: '剧本生成' },
            { key: 'storyboard_studio', href: '/storyboard-studio', icon: '🧩', label: '分镜制作' },
            { key: 'txt2csv', href: '/txt2csv', icon: '🔁', label: '转换工具' },
            { key: 'content_management', href: '/content-management', icon: '🗃️', label: '内容管理' },
        ];
        const adminItems = [
            { key: 'admin', href: '/admin', icon: '⚙️', label: '系统管理' },
            { key: 'stats', href: '/stats', icon: '📊', label: '系统统计' },
        ];
        const isSystemAdmin = window.__APP_CONTEXT__?.is_system_admin;

        return React.createElement(
            'nav',
            { className: 'sidebar-nav', id: 'sidebarNav' },
            React.createElement(
                'div',
                { className: 'sidebar-nav-header' },
                React.createElement('div', { className: 'sidebar-nav-title' }, 'AI创作工具'),
                React.createElement(
                    'button',
                    {
                        className: 'sidebar-nav-toggle',
                        onClick: () => toggleSidebar(),
                        title: '收起/展开',
                    },
                    React.createElement('span', { id: 'toggleIcon' }, '•')
                )
            ),
            React.createElement(
                'div',
                { className: 'sidebar-nav-menu' },
                items.map((item) => menuItem(props, item)),
                isSystemAdmin
                    ? React.createElement(
                        React.Fragment,
                        null,
                        React.createElement('div', { className: 'sidebar-nav-divider' }),
                        adminItems.map((item) => menuItem(props, item))
                    )
                    : null
            ),
            React.createElement(
                'div',
                { className: 'sidebar-nav-user' },
                React.createElement(
                    'div',
                    { className: 'sidebar-nav-user-info' },
                    React.createElement('div', { className: 'sidebar-nav-user-avatar' }, '👤'),
                    React.createElement('div', { className: 'sidebar-nav-user-name' }, props.username || 'user'),
                    React.createElement('a', { href: '/logout', className: 'sidebar-nav-logout' }, '登出')
                ),
                React.createElement(ProjectSwitcher, props)
            )
        );
    }

    window.AppSidebar = AppSidebar;
})();
