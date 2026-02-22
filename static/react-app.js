(() => {
    if (!window.React || !window.ReactDOM) return;
    const root = document.getElementById('reactApp');
    if (!root) return;

    document.body.classList.add('react-theme');

    const e = window.React.createElement;
    const App = () => {
        const containerRef = window.React.useRef(null);
        window.React.useEffect(() => {
            const container = containerRef.current;
            if (!container) return;
            const legacyMain = document.getElementById('legacyMain');
            if (legacyMain) {
                const children = Array.from(legacyMain.children);
                children.forEach(node => {
                    if (node.tagName && node.tagName.toLowerCase() === 'script') return;
                    container.appendChild(node);
                });
                legacyMain.remove();
                return;
            }
            const sidebar = document.querySelector('.sidebar-nav');
            const main = document.querySelector('.main-content');
            if (sidebar) container.appendChild(sidebar);
            if (main) container.appendChild(main);
        }, []);
        return e('div', { ref: containerRef });
    };

    window.ReactDOM.createRoot(root).render(e(App));
})();
