/**
 * 全局状态管理器 - 在页面切换时保留用户输入状态
 * 自动为所有具有 data-save 属性的表单元素保存值
 */

const StateManager = {
    // 存储前缀
    PREFIX: 'state_',
    
    /**
     * 初始化状态管理器
     * 在页面加载时调用此方法
     */
    init() {
        // 恢复保存的状态
        this.restoreAllStates();
        
        // 监听所有具有 data-save 属性的表单元素
        document.addEventListener('input', (e) => {
            if (e.target.dataset.save) {
                this.saveState(e.target);
            }
        });
        
        document.addEventListener('change', (e) => {
            if (e.target.dataset.save) {
                this.saveState(e.target);
            }
        });
    },
    
    /**
     * 为元素自动绑定保存
     */
    autoSave(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.dataset.save = 'true';
            element.addEventListener('input', () => this.saveState(element));
            element.addEventListener('change', () => this.saveState(element));
        }
    },
    
    /**
     * 保存单个元素的状态
     */
    saveState(element) {
        const key = this.PREFIX + element.id;
        try {
            let value = element.value;
            
            // 处理不同类型的元素
            if (element.type === 'checkbox') {
                value = element.checked;
            } else if (element.type === 'radio') {
                value = document.querySelector(`input[name="${element.name}"]:checked`)?.value;
            } else if (element.tagName === 'SELECT') {
                value = element.value;
            } else if (element.tagName === 'TEXTAREA') {
                value = element.value;
            }
            
            localStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            console.error(`保存状态失败 [${element.id}]:`, e);
        }
    },
    
    /**
     * 恢复所有保存的状态
     */
    restoreAllStates() {
        // 遍历所有有 id 的表单元素
        const formElements = document.querySelectorAll('[id]');
        formElements.forEach(element => {
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName)) {
                this.restoreState(element);
            }
        });
    },
    
    /**
     * 恢复单个元素的状态
     */
    restoreState(element) {
        const key = this.PREFIX + element.id;
        try {
            const saved = localStorage.getItem(key);
            if (saved !== null) {
                const value = JSON.parse(saved);
                
                if (element.type === 'checkbox') {
                    element.checked = value;
                } else if (element.type === 'radio') {
                    const radio = document.querySelector(`input[name="${element.name}"][value="${value}"]`);
                    if (radio) radio.checked = true;
                } else {
                    element.value = value;
                }
                
                // 触发 change 事件以更新相关 UI
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }
        } catch (e) {
            console.error(`恢复状态失败 [${element.id}]:`, e);
        }
    },
    
    /**
     * 清除特定元素的保存状态
     */
    clearState(elementId) {
        const key = this.PREFIX + elementId;
        localStorage.removeItem(key);
    },
    
    /**
     * 清除所有保存的状态
     */
    clearAll() {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith(this.PREFIX)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
    }
};

// 页面加载完成时初始化
document.addEventListener('DOMContentLoaded', () => {
    StateManager.init();
});
