# 阿里云 OSS 配置快速指南

## ✅ 已完成的修改

1. ✅ 替换为阿里云 OSS SDK
2. ✅ 安装 oss2 依赖包
3. ✅ 配置 OSS 端点为 `shor-file.oss-cn-wulanchabu.aliyuncs.com`
4. ✅ 更新 `.env.example` 模板

## 📝 配置步骤

### 1. 编辑 `.env` 文件

在项目根目录的 `.env` 文件中添加以下配置：

```bash
# 火山引擎 API（必需）
VOLCENGINE_AK=你的火山引擎AccessKey
VOLCENGINE_SK=你的火山引擎SecretKey

# 阿里云 OSS（可选，仅在使用参考图片时需要）
OSS_ENABLED=true
OSS_ENDPOINT=shor-file.oss-cn-wulanchabu.aliyuncs.com
OSS_ACCESS_KEY_ID=你的阿里云AccessKeyId
OSS_ACCESS_KEY_SECRET=你的阿里云AccessKeySecret
```

### 2. 获取阿里云 AccessKey

1. 登录 [阿里云 RAM 控制台](https://ram.console.aliyun.com/manage/ak)
2. 创建或查看 AccessKey
3. 复制 `AccessKey ID` 和 `AccessKey Secret`
4. 填入 `.env` 文件

### 3. 确认 OSS 存储桶权限

确保 `shor-file` 存储桶已配置：
- ✅ **公共读**权限（推荐）：上传的图片可以通过 URL 直接访问
- 或配置**私有**并使用签名 URL（需修改代码）

### 4. 重启应用

```powershell
# 如果应用正在运行，按 Ctrl+C 停止
# 然后重新启动
python web_app.py
```

## 🎯 测试配置

### 测试 1：纯文字生成（无需 OSS）

1. 访问 http://localhost:5000
2. 输入提示词："一只可爱的小猫"
3. **不上传图片**
4. 点击生成
5. ✅ 应该正常生成图片

### 测试 2：参考图片生成（需要 OSS）

1. 在 `.env` 设置 `OSS_ENABLED=true`
2. 填写 OSS 配置（AccessKey ID/Secret）
3. 重启应用
4. 访问 http://localhost:5000
5. 输入提示词："保持这个风格，换个场景"
6. **上传 1-4 张参考图片**
7. 点击生成
8. 查看终端输出，应显示：`成功上传图片到阿里云 OSS: https://...`
9. ✅ 生成的图片应参考上传的图片风格

## 🔍 验证 OSS 上传

成功上传后，终端会显示：
```
成功上传图片到阿里云 OSS: https://shor-file.oss-cn-wulanchabu.aliyuncs.com/ai-images/20251130/xxx.jpg
```

你可以：
1. 复制这个 URL
2. 在浏览器中打开
3. 应该能看到上传的图片（如果配置了公共读权限）

## ⚙️ OSS 配置说明

### OSS_ENDPOINT 格式

格式：`bucket-name.oss-region.aliyuncs.com`

示例：
- `shor-file.oss-cn-wulanchabu.aliyuncs.com` ✅
- `my-bucket.oss-cn-hangzhou.aliyuncs.com` ✅

### 上传路径

图片会上传到：
```
ai-images/
  └── 20251130/          # 日期目录
      ├── image1.jpg
      └── image2.jpg
```

公网访问 URL：
```
https://shor-file.oss-cn-wulanchabu.aliyuncs.com/ai-images/20251130/image1.jpg
```

## 🐛 常见问题

### Q1: 上传失败，提示 "AccessDenied"

**原因**：AccessKey 权限不足

**解决**：
1. 确认 AccessKey 有 OSS 的读写权限
2. 在 RAM 控制台检查权限策略
3. 确保策略包含 `oss:PutObject` 权限

### Q2: 上传成功但图片无法访问

**原因**：存储桶权限为私有

**解决**：
- **方案 A**：在 OSS 控制台将存储桶设置为**公共读**
- **方案 B**：修改代码使用签名 URL（有效期限制）

### Q3: 提示 "未安装 oss2 SDK"

**解决**：
```powershell
.\.venv\Scripts\Activate.ps1
pip install oss2
```

### Q4: 仍然想使用本地图片测试

**临时方案**：
- 手动将图片上传到 OSS
- 获取公网 URL
- 在 API 调用时直接使用该 URL

## 📊 费用说明

阿里云 OSS 按使用量计费：
- **存储费用**：约 ¥0.12/GB/月
- **流量费用**：外网流出约 ¥0.50/GB
- **请求费用**：PUT 请求约 ¥0.01/万次

小规模使用（每天生成几十张图）基本可忽略不计。

## 🎉 完成

配置完成后：
- ✅ 可以使用纯文字生成图片（无需 OSS）
- ✅ 可以上传参考图片进行图生图（需要 OSS）
- ✅ 生成的图片保存在 `output/` 目录
- ✅ 上传的图片也会保存在 `uploads/` 目录

开始使用吧！访问 http://localhost:5000 🚀
