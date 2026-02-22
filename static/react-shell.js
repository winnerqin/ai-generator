(() => {
    if (!window.React || !window.ReactDOM) return;
    const root = document.getElementById('reactShellRoot');
    if (!root) return;

    document.body.classList.add('react-theme');

    const e = window.React.createElement;
    const Shell = () => e(
        'div',
        { className: 'react-shell-bar' },
        e('div', null, 'Ai创作工具 · React Style'),
        e('div', { className: 'react-shell-badge' }, 'Theme Active')
    );

    window.ReactDOM.createRoot(root).render(e(Shell));
})();
