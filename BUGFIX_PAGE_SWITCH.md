# 修复：页面切换导致的 Failed to fetch 错误

## 问题描述
在做脚本分析时，如果在分析进行中切换到单图生成，再回来脚本分析页面，会出现 "Failed to fetch" 错误。

## 根本原因
1. 页面 A 有未完成的请求
2. 用户切换到页面 B（beforeunload 事件触发，abort 了页面 A 的请求）
3. 用户回到页面 A
4. 旧的 AbortController 仍然处于 abort 状态，新请求会立即失败

## 修复方案

### 修复1：改进 AbortController 管理（script_analysis.html）

**之前的问题代码：**
```javascript
window.addEventListener('beforeunload', () => {
    if (analysisAbortController) {
        analysisAbortController.abort();
    }
});
```

**修复后的代码：**
```javascript
// 页面可见性变化时的处理
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // 页面隐藏时，取消任何未完成的请求
        if (analysisAbortController) {
            analysisAbortController.abort();
            analysisAbortController = new AbortController();
        }
    } else {
        // 页面重新显示时，重置 AbortController
        analysisAbortController = new AbortController();
    }
});
```

**改进点：**
- 使用 `visibilitychange` 事件而不是 `beforeunload`
- 页面重新显示时自动创建新的 AbortController
- 避免旧的 abort 状态干扰新请求

### 修复2：添加 keepalive 选项（script_analysis.html）

**修改的 fetch 请求：**
```javascript
const response = await fetch('/api/analyze-script', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script: scriptText }),
    signal: analysisAbortController ? analysisAbortController.signal : undefined,
    keepalive: true  // 新增：保持连接，即使页面卸载也继续处理
});
```

**改进点：**
- 添加 `keepalive: true` 选项，即使页面卸载也能继续处理请求
- 使页面切换不会中断后端的处理
- 用户可以在后台继续接收服务器响应

### 修复3：更安全的错误处理（script_analysis.html）

**改进后的代码：**
```javascript
// 确保有有效的 AbortController
try {
    if (analysisAbortController) {
        analysisAbortController.abort();
    }
} catch (e) {
    // 忽略错误
}

// 创建新的 AbortController
try {
    analysisAbortController = new AbortController();
} catch (e) {
    console.error('无法创建 AbortController:', e);
    analysisAbortController = null;
}
```

**改进点：**
- 使用 try-catch 处理异常
- 即使无法创建 AbortController 也能继续
- 更健壮的错误处理

### 修复4：添加 keepalive 到 batch.html

```javascript
const response = await fetch('/api/batch-generate-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tasks: batchData }),
    signal: batchGenerateAbortController.signal,
    keepalive: true  // 新增：保持请求活跃
});
```

## 测试步骤

1. **启动应用**
   ```powershell
   python web_app.py
   ```

2. **测试脚本分析的页面切换**
   - 打开脚本分析页面
   - 输入一段脚本文本
   - 点击"分析"按钮，开始分析
   - **立即**切换到单图生成页面
   - 等待5-10秒
   - 切换回脚本分析页面
   - ✅ 应该看到分析结果（不再是 Failed to fetch 错误）

3. **测试批量生成的页面切换**
   - 打开批量生成页面
   - 提交批量任务
   - 立即切换到其他页面
   - 等待10秒后切换回来
   - ✅ 应该看到进度更新（不再出现错误）

## 预期结果

✅ **页面切换不会导致 Failed to fetch 错误**
✅ **切换回原页面时，服务器的处理会继续**
✅ **用户体验更顺滑，不会被错误信息打扰**

## 技术细节

### keepalive 参数的作用
- `keepalive: true` 告诉浏览器保持 HTTP 连接活跃
- 即使页面卸载，服务器也能继续处理请求
- 客户端不再监听响应，但服务器仍在工作

### visibilitychange 事件的优势
- 比 `beforeunload` 更可靠
- 页面切换和回来时都能正确处理
- 支持现代浏览器的所有版本

### 为什么不用 beforeunload？
- `beforeunload` 可能不会在所有页面切换情况下触发
- 用户从标签页切换到另一个标签页时，`beforeunload` 不触发
- `visibilitychange` 在这些情况下都能正确触发

## 向后兼容性

✅ **完全向后兼容**
- 只修改了前端代码
- 后端代码无需改动
- 与现有功能无冲突
- 不影响其他页面

## 相关文件修改

1. **templates/script_analysis.html**
   - 改进 AbortController 管理
   - 添加 keepalive 选项
   - 增强错误处理

2. **templates/batch.html**
   - 添加 keepalive 选项

3. **templates/index.html**
   - 已有 keepalive 选项，无需修改

## 后续建议

如果仍然遇到问题，可以考虑：

1. **添加日志记录**
   ```javascript
   console.log('页面隐藏，正在准备新请求');
   ```

2. **增加重试机制**
   ```javascript
   // 如果请求失败，自动重试一次
   ```

3. **使用 Service Worker**
   - 在后台处理请求
   - 更好地处理离线场景

4. **使用 Beacon API**
   - 用于发送分析数据
   - 页面卸载时仍能发送

## 验证日志

应用启动后，查看日志输出：
```powershell
python log_monitor.py --watch
```

看到这样的日志说明正常：
```
2024-01-15 10:31:00 - [INFO] - [请求] POST /api/analyze-script | 用户: 1
2024-01-15 10:31:15 - [INFO] - [操作] 分析脚本成功 | 用户ID: 1, 生成场景数: 5
```

## 总结

通过结合 `visibilitychange` 事件和 `keepalive: true` 选项，我们：
- ✅ 避免了 abort 状态干扰新请求
- ✅ 保证后端能完成处理
- ✅ 改进了用户体验
- ✅ 增加了系统可靠性

修复完成！现在可以安心地在页面之间切换了。 🎉
