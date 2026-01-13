# 日志系统快速入门

## 1. 启动应用并查看日志

应用启动时会自动输出日志到控制台和 `app.log` 文件：

```powershell
# 启动应用
python web_app.py

# 控制台会显示类似以下内容
2024-01-15 10:30:00 - [INFO] - [操作] 应用启动 | 版本: 1.0 | 环境: 开发 | 监听地址: 0.0.0.0:5000
2024-01-15 10:30:01 - [INFO] - [操作] 数据库初始化 | 状态: 已初始化
2024-01-15 10:30:02 - [INFO] - [操作] OSS配置 | 端点: shor-file.oss-cn-wulanchabu.aliyuncs.com
```

## 2. 实时监控日志

### 使用PowerShell（Windows）查看实时日志

```powershell
# 在项目目录打开PowerShell，执行：
Get-Content app.log -Wait

# Ctrl+C 退出查看
```

### 使用tail（Linux/Mac）查看实时日志

```bash
tail -f app.log
```

## 3. 日志输出示例

### 用户登录时的日志
```
2024-01-15 10:31:00 - [INFO] - [请求] POST /login | 用户: admin
2024-01-15 10:31:01 - [INFO] - [操作] 用户登录 | 用户ID: 1, 用户名: admin
```

### 生成图片时的日志
```
2024-01-15 10:32:00 - [INFO] - [请求] POST /api/generate | 用户: 1 | 参数: 提示词长度: 256
2024-01-15 10:32:15 - [INFO] - [操作] 生成图片成功 | 用户ID: 1, 输出目录: output/1, 生成图片: 4
```

### 批量操作时的日志
```
2024-01-15 10:35:00 - [INFO] - [请求] POST /api/batch-delete | 用户: 1 | 记录数: 5
2024-01-15 10:35:02 - [INFO] - [操作] 批量删除记录 | 用户ID: 1, 成功: 5, 失败: 0
```

### 错误发生时的日志
```
2024-01-15 10:36:00 - [ERROR] - [操作] 生成图片失败 | 用户ID: 1, 错误: API超时
2024-01-15 10:36:01 - [WARNING] - [操作] 删除样本图失败 | 用户ID: 1, 错误: 文件不存在
```

## 4. 常用日志搜索

### 查找特定用户的所有操作
```powershell
Select-String "用户ID: 1" app.log
```

### 查找所有错误
```powershell
Select-String "\[ERROR\]" app.log
```

### 查找生成相关的操作
```powershell
Select-String "生成" app.log
```

### 查找特定时间段的日志（如10:30到10:35）
```powershell
Get-Content app.log | Select-String "10:3[0-5]"
```

### 统计操作次数
```powershell
# 统计生成图片成功的次数
(Select-String "生成图片成功" app.log).Count

# 统计用户1的操作数
(Select-String "用户ID: 1" app.log).Count
```

## 5. 日志分析任务示例

### 找出最常失败的操作
```powershell
Select-String "\[ERROR\]" app.log | Select-String "用户ID: " | Group-Object { $_ -replace '.*\[操作\] ([^ ]*).*/','$1' }
```

### 找出用户的完整操作链路（以用户1为例）
```powershell
$logs = Select-String "用户ID: 1" app.log
$logs | ForEach-Object { $_.Line }
```

## 6. 定期维护建议

### 检查日志文件大小
```powershell
# 获取app.log文件大小（MB）
$size = (Get-Item app.log).Length / 1MB
Write-Host "日志文件大小: $size MB"

# 如果超过100MB，建议备份或清理
if ($size -gt 100) {
    Write-Host "建议备份或清理日志文件"
    # 备份日志
    Copy-Item app.log "app.log.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    # 清空日志（保留第一行注释）
    "" | Out-File app.log
}
```

### 定期生成日志摘要
```powershell
# 生成今天的操作统计
$date = Get-Date -Format "yyyy-MM-dd"
$logs = Select-String "\[$date" app.log

# 统计各类操作
$operations = @{}
$logs | ForEach-Object {
    if ($_ -match '\[操作\] ([^|]*)\|') {
        $op = $matches[1]
        if ($operations.ContainsKey($op)) {
            $operations[$op]++
        } else {
            $operations[$op] = 1
        }
    }
}

Write-Host "今日操作统计:"
$operations | ForEach-Object { 
    Write-Host "$($_.Key): $($_.Value)次" 
}
```

## 7. 日志级别说明

| 级别 | 标记 | 用途 | 示例 |
|-----|------|------|------|
| INFO | [INFO] | 记录正常操作和成功的请求 | 用户登录, 图片生成成功 |
| WARNING | [WARNING] | 记录警告信息，操作部分失败 | 登录失败, 部分删除失败 |
| ERROR | [ERROR] | 记录错误，操作完全失败 | API错误, 数据库异常 |

## 8. 性能分析

### 计算API响应时间
日志中的请求时间和操作时间之间的差值就是响应时间：

```powershell
# 例如：
# 10:32:00 - [请求] POST /api/generate
# 10:32:15 - [操作] 生成图片成功
# 响应时间：15秒
```

### 找出最慢的操作（超过30秒）
```powershell
# 手动检查日志，找出相同用户和相同操作的请求和结果日志，计算时间差
```

## 9. 故障诊断

### 如果发现日志停止更新
1. 检查 `app.log` 文件是否被锁定
2. 检查磁盘空间是否充足
3. 重启应用

### 如果看到大量ERROR日志
1. 检查API服务是否可用
2. 检查数据库连接
3. 检查OSS配置

### 如果日志文件过大
1. 备份日志文件：`app.log.backup`
2. 清空日志：删除 `app.log` 内容或创建新文件
3. 考虑实施日志轮转机制

## 10. 日志导出和报告

### 导出为CSV格式进行分析
```powershell
# 简单的CSV导出（用户, 操作, 时间）
Select-String "\[操作\]" app.log | 
ForEach-Object {
    if ($_ -match '(\d{2}:\d{2}:\d{2}).*用户ID: (\d+).*\[操作\] ([^|]*)') {
        "$($matches[3]),$($matches[2]),$($matches[1])"
    }
} | Out-File operations.csv
```

### 每日生成日志摘要
```powershell
# 获取今日日志
$date = Get-Date -Format "yyyy-MM-dd"
$todayLogs = Select-String "\[$date" app.log

# 计算统计信息
$errorCount = ($todayLogs | Select-String "\[ERROR\]").Count
$infoCount = ($todayLogs | Select-String "\[INFO\]").Count
$warningCount = ($todayLogs | Select-String "\[WARNING\]").Count

Write-Host "日志摘要 ($date):"
Write-Host "总日志条数: $($todayLogs.Count)"
Write-Host "信息: $infoCount"
Write-Host "警告: $warningCount"
Write-Host "错误: $errorCount"
```

## 更多信息

详见 [LOGGING_DOCUMENTATION.md](LOGGING_DOCUMENTATION.md) 获取完整文档。
