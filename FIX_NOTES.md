# 修复说明：参考图片上传问题

## ✅ 已修复的问题

之前的错误：
```
Download Url Error.: download image url failed: parse "file://E:\..."
```

**原因**：火山引擎 API 只支持 HTTP/HTTPS 公网 URL，不支持本地文件路径。

## ✅ 当前解决方案

### 方案 A：仅使用文字生成图片（默认，立即可用）

**无需任何配置**，按以下步骤操作：

1. 访问 http://localhost:5000
2. 输入提示词（例如："一只可爱的猫咪，水彩画风格"）
3. **不要上传任何图片**
4. 选择比例、分辨率、生成数量
5. 点击"开始生成"

✅ **现在应该可以正常生成图片了！**

---

### 方案 B：使用参考图片功能（需要配置 TOS）

如果需要使用参考图片（图生图）功能，需要配置对象存储：

#### 1. 安装 TOS SDK
```powershell
.\.venv\Scripts\Activate.ps1
pip install tos
```

#### 2. 在 `.env` 中添加配置
```bash
# 启用 OSS 上传
OSS_ENABLED=true

# TOS 配置
TOS_ENDPOINT=tos-cn-beijing.volces.com
TOS_BUCKET=你的存储桶名称
TOS_REGION=cn-beijing
```

#### 3. 重启应用
```powershell
python web_app.py
```

现在上传的图片会自动上传到 TOS 并使用公网 URL。

---

## 🎯 快速测试（不使用参考图片）

### 测试 1：简单文字生成
```
提示词: 一只穿西装的狐狸，电影级肖像
负面提示词: 模糊，低质量
比例: 1:1
分辨率: 2K
数量: 1
```

### 测试 2：批量生成
```
提示词: 未来科技城市，赛博朋克风格，霓虹灯
比例: 16:9
分辨率: 2K
数量: 2
输出文件名: cyberpunk_city
```

### 测试 3：高分辨率
```
提示词: 日落时的山峰，金色阳光，风景摄影
比例: 3:2
分辨率: 4K
数量: 1
```

---

## 📝 代码修改说明

已修改 `web_app.py`：

1. **默认行为**：如果未配置 OSS（`OSS_ENABLED=true`），上传的图片会保存到本地，但**不会**传递给 API，避免错误
2. **启用 OSS 后**：图片会上传到火山引擎 TOS，使用公网 URL 调用 API
3. **提示信息**：终端会显示是否启用了 OSS，以及图片处理状态

### 关键逻辑：

```python
# 如果没有配置 OSS
if not oss_enabled:
    # 保存文件但不添加到 image_urls
    print("提示：将仅使用文字生成图片")

# 如果配置了 OSS
if oss_enabled:
    tos_url = upload_to_tos(filepath)
    if tos_url:
        image_urls.append(tos_url)  # 使用公网 URL
```

---

## ❓ 常见问题

### Q: 现在可以直接使用吗？
**A**: 是的！只要不上传图片，直接输入提示词即可生成。

### Q: 必须配置 TOS 吗？
**A**: 不必须。仅在需要使用参考图片功能时才需要。

### Q: 我上传了图片但没配置 TOS，会怎样？
**A**: 应用会保存图片到本地，但生成时会忽略它们，仅使用文字生成。终端会显示提示信息。

### Q: 如何验证是否正常？
**A**: 运行应用后，只填写提示词（不上传图片），点击生成。如果能看到生成的图片，说明正常。

---

## 🚀 立即开始（3 步）

```powershell
# 1. 确保虚拟环境已激活
.\.venv\Scripts\Activate.ps1

# 2. 启动应用
python web_app.py

# 3. 打开浏览器
# 访问 http://localhost:5000
# 输入提示词，不上传图片，点击生成
```

完成！现在应该可以正常使用了 🎉
