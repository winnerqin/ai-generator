# 示例图功能使用说明

## 功能概述

Web应用现在支持从阿里云OSS读取示例图片，用户可以直接从页面上选择1-4张示例图作为参考图，无需重复上传。

## 主要更新

### 1. 保留原始文件名
- 上传到OSS时保留原始文件名，不添加时间戳前缀
- 便于管理和识别文件

### 2. 示例图管理
- 示例图存储在OSS的 `ai-images/sample/` 目录
- Web页面自动从OSS加载示例图列表
- 用户可点击选择1-4张示例图

### 3. 灵活组合
- 支持同时使用手动上传图片和OSS示例图
- 总数限制：最多4张（手动上传 + 示例图）

## 使用步骤

### 1. 上传示例图到OSS

使用提供的脚本上传示例图：

```bash
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 上传单个图片
python upload_sample_images.py path/to/image.jpg

# 上传整个文件夹的图片
python upload_sample_images.py path/to/folder/
```

脚本会自动：
- 读取 `.env` 配置
- 上传图片到 `ai-images/sample/` 目录
- 显示公网访问URL

### 2. 在Web界面使用示例图

1. 打开浏览器访问 http://localhost:5000
2. 在"选择示例图片（从OSS）"区域查看可用的示例图
3. 点击图片选择（最多4张）
4. 选中的图片会显示蓝色边框和序号
5. 可以与手动上传的图片组合使用
6. 填写提示词等参数后点击"开始生成"

### 3. 页面功能说明

**示例图区域：**
- 自动从OSS加载 `ai-images/sample/` 目录的图片
- 点击图片进行选择/取消选择
- 选中的图片显示蓝色边框和序号（1、2、3、4）
- 悬停时图片会放大显示

**总数限制：**
- 手动上传图片 + 示例图 ≤ 4张
- 超过限制会显示提示信息

**图片优先级：**
1. 首先使用从OSS选择的示例图
2. 然后添加手动上传的图片
3. 发送到API时按此顺序组合

## 示例图管理建议

### 图片命名规范
```
sample/
  ├── style_anime_01.jpg
  ├── style_realistic_01.jpg
  ├── character_girl_01.jpg
  ├── background_forest_01.jpg
  └── ...
```

### 推荐的示例图类型
- **风格参考**：不同艺术风格的示例（动漫、写实、水彩等）
- **角色参考**：各类人物角色的参考图
- **场景参考**：常见场景和背景
- **构图参考**：不同构图方式的示例

### 图片要求
- 格式：JPG, PNG, WEBP（推荐JPG）
- 尺寸：建议不超过2K分辨率
- 大小：建议每张不超过5MB
- 质量：清晰、主题明确的高质量图片

## API接口

### 获取示例图列表
```
GET /api/sample-images
```

响应示例：
```json
{
  "success": true,
  "images": [
    {
      "filename": "style_anime_01.jpg",
      "url": "https://shor-file.oss-cn-wulanchabu.aliyuncs.com/ai-images/sample/style_anime_01.jpg",
      "key": "ai-images/sample/style_anime_01.jpg"
    }
  ]
}
```

### 生成图片（带示例图）
```
POST /generate
```

表单数据：
- `sample_image_urls[]`: 示例图URL列表（从OSS选择的）
- `images`: 手动上传的文件
- 其他生成参数...

## 故障排查

### 示例图显示"加载中..."
- 检查OSS配置是否正确（`.env`文件）
- 确认 `ai-images/sample/` 目录存在且有图片
- 查看浏览器控制台的错误信息

### 示例图显示"暂无示例图片"
- 使用 `upload_sample_images.py` 上传示例图
- 确认文件已成功上传到OSS

### 示例图显示"加载失败"
- 检查网络连接
- 验证OSS访问权限配置
- 查看Flask应用的控制台输出

### 选择示例图后生成失败
- 确认示例图URL可公网访问
- 检查API请求日志中的image_urls参数
- 验证火山引擎API是否支持该URL格式

## 技术细节

### 前端实现
- 使用 `fetch('/api/sample-images')` 加载示例图
- 通过点击事件切换选择状态
- FormData 提交时包含 `sample_image_urls` 字段

### 后端实现
- `list_sample_images_from_oss()`: 列出OSS中的示例图
- `get_oss_bucket()`: 获取OSS bucket连接
- `/api/sample-images`: 返回示例图列表
- `/generate`: 合并示例图URL和上传文件URL

### 存储结构
```
shor-file (OSS Bucket)
└── ai-images/
    ├── sample/          # 示例图目录（新增）
    │   ├── image1.jpg
    │   ├── image2.jpg
    │   └── ...
    └── YYYYMMDD/        # 生成结果和上传的参考图
        ├── xxx.jpg
        └── ...
```

## 下一步计划

可以考虑的增强功能：
- [ ] 示例图分类标签系统
- [ ] 示例图搜索和筛选
- [ ] 示例图预览大图功能
- [ ] 批量管理示例图的后台界面
- [ ] 示例图使用统计和热度排序
