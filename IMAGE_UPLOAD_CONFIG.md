# 参考图片上传配置说明

## 问题说明

火山引擎视觉 API 的 `image_urls` 参数**只支持公网可访问的 HTTP/HTTPS URL**，不支持本地文件路径。

错误示例：
```
file://E:\path\to\image.jpg  ❌ 不支持
```

正确示例：
```
https://your-bucket.tos-cn-beijing.volces.com/image.jpg  ✅ 支持
```

## 解决方案

### 方案 1：仅使用文字生成图片（默认）

如果不需要参考图片功能，直接使用即可。Web 应用会自动忽略上传的图片，仅使用提示词生成。

**无需额外配置。**

---

### 方案 2：配置火山引擎 TOS 对象存储（推荐）

#### 步骤 1：开通 TOS 服务

1. 登录 [火山引擎控制台](https://console.volcengine.com/)
2. 进入「对象存储 TOS」服务
3. 创建存储桶（Bucket）
4. 配置公共读权限（或使用签名 URL）

#### 步骤 2：安装 TOS SDK

```powershell
.\.venv\Scripts\Activate.ps1
pip install tos
```

#### 步骤 3：配置环境变量

在 `.env` 文件中添加：

```bash
# 启用 OSS 上传
OSS_ENABLED=true

# TOS 配置
TOS_ENDPOINT=tos-cn-beijing.volces.com
TOS_BUCKET=your-bucket-name
TOS_REGION=cn-beijing

# AK/SK（已有则无需重复添加）
VOLCENGINE_AK=你的AccessKey
VOLCENGINE_SK=你的SecretKey
```

#### 步骤 4：重启应用

```powershell
python web_app.py
```

现在上传的图片会自动上传到 TOS，并使用公网 URL 调用 API。

---

### 方案 3：使用第三方图床或 CDN

如果不想使用 TOS，也可以：

1. 将图片手动上传到图床（如：imgur、sm.ms、七牛云等）
2. 获取公网 URL
3. 修改代码，将获取的 URL 传递给 API

**修改位置**：`web_app.py` 中的 `upload_to_tos` 函数，替换为你的上传逻辑。

---

### 方案 4：开发环境临时方案（使用 ngrok）

适用于本地开发测试：

#### 步骤 1：安装 ngrok

下载：https://ngrok.com/download

#### 步骤 2：启动文件服务器

在项目目录运行：

```powershell
# 在 8080 端口启动文件服务器
python -m http.server 8080 --directory uploads
```

#### 步骤 3：使用 ngrok 暴露到公网

```powershell
ngrok http 8080
```

复制 ngrok 提供的公网 URL（如 `https://xxxx.ngrok.io`）

#### 步骤 4：修改代码

在 `web_app.py` 中，将：
```python
image_urls.append(f"file://{os.path.abspath(filepath)}")
```

改为：
```python
ngrok_url = "https://xxxx.ngrok.io"  # 替换为你的 ngrok URL
image_urls.append(f"{ngrok_url}/{unique_filename}")
```

**注意**：此方案仅适合开发测试，不建议用于生产环境。

---

## 推荐配置

**生产环境**：方案 2（TOS 对象存储）  
**快速测试**：方案 1（仅文字生成）  
**开发调试**：方案 4（ngrok）

---

## 常见问题

### Q1: 是否必须配置对象存储？

**不必须。** 如果只使用文字生成图片功能，无需配置。Web 应用会自动忽略上传的图片。

### Q2: TOS 费用如何？

火山引擎 TOS 提供免费额度，小规模使用基本免费。详见 [TOS 价格说明](https://www.volcengine.com/pricing/tos)

### Q3: 可以使用阿里云 OSS 或腾讯云 COS 吗？

**可以。** 修改 `upload_to_tos` 函数，替换为对应的 SDK 调用即可。

示例（阿里云 OSS）：
```python
import oss2

def upload_to_aliyun_oss(file_path):
    auth = oss2.Auth('AccessKeyId', 'AccessKeySecret')
    bucket = oss2.Bucket(auth, 'oss-endpoint', 'bucket-name')
    object_key = f"ai-images/{os.path.basename(file_path)}"
    bucket.put_object_from_file(object_key, file_path)
    return f"https://bucket-name.oss-endpoint.com/{object_key}"
```

### Q4: 如何测试 TOS 是否配置成功？

运行 Web 应用后，上传一张图片，检查终端输出：
- 成功：`成功上传图片到 TOS: https://...`
- 失败：`TOS 上传失败: ...`

---

## 快速开始（无参考图片）

如果暂时不需要参考图片功能：

1. 确保 `.env` 中有 `VOLCENGINE_AK` 和 `VOLCENGINE_SK`
2. 运行 `python web_app.py`
3. 访问 http://localhost:5000
4. **只填写提示词，不上传图片**
5. 点击生成即可

这样可以立即使用文字生成图片功能，无需任何额外配置！
