# Git 项目设置和发布指南

## ✅ 已完成

1. ✅ Git 仓库已初始化
2. ✅ 所有文件已添加到暂存区
3. ✅ 首次提交已完成（65个文件，22049行代码）

## 📋 下一步：发布到远程仓库

### 方式一：发布到 GitHub

1. **在 GitHub 上创建新仓库**
   - 访问 https://github.com/new
   - 输入仓库名称（例如：`ai-generator`）
   - 选择 Public 或 Private
   - **不要**初始化 README、.gitignore 或 license（因为本地已有）

2. **连接远程仓库并推送**
   ```bash
   # 添加远程仓库（替换 YOUR_USERNAME 和 REPO_NAME）
   git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
   
   # 或者使用 SSH（如果已配置 SSH 密钥）
   git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git
   
   # 重命名分支为 main（GitHub 默认分支名）
   git branch -M main
   
   # 推送到远程仓库
   git push -u origin main
   ```

### 方式二：发布到 Gitee（码云）

1. **在 Gitee 上创建新仓库**
   - 访问 https://gitee.com/projects/new
   - 输入仓库名称
   - 选择公开或私有

2. **连接远程仓库并推送**
   ```bash
   # 添加远程仓库
   git remote add origin https://gitee.com/YOUR_USERNAME/REPO_NAME.git
   
   # 重命名分支为 main
   git branch -M main
   
   # 推送到远程仓库
   git push -u origin main
   ```

### 方式三：发布到 GitLab

1. **在 GitLab 上创建新项目**
   - 访问你的 GitLab 实例
   - 创建新项目

2. **连接远程仓库并推送**
   ```bash
   # 添加远程仓库
   git remote add origin https://gitlab.com/YOUR_USERNAME/REPO_NAME.git
   
   # 重命名分支为 main
   git branch -M main
   
   # 推送到远程仓库
   git push -u origin main
   ```

## 🔧 常用 Git 命令

### 查看状态
```bash
git status
```

### 查看提交历史
```bash
git log --oneline
```

### 添加文件
```bash
git add .
git add <文件名>
```

### 提交更改
```bash
git commit -m "提交说明"
```

### 推送到远程
```bash
git push
```

### 拉取远程更新
```bash
git pull
```

### 查看远程仓库
```bash
git remote -v
```

### 修改远程仓库地址
```bash
git remote set-url origin <新的仓库地址>
```

## 📝 注意事项

1. **敏感信息**：确保 `.env` 文件已在 `.gitignore` 中，不会被提交
2. **大文件**：`venv/`、`output/`、`uploads/` 等目录已被忽略
3. **数据库文件**：`*.db` 文件已被忽略，不会提交到仓库
4. **日志文件**：`*.log` 和 `logs/` 目录已被忽略

## 🚀 后续开发流程

1. 修改代码
2. `git add .` - 添加更改
3. `git commit -m "描述更改"` - 提交更改
4. `git push` - 推送到远程仓库

## 📚 更多资源

- [Git 官方文档](https://git-scm.com/doc)
- [GitHub 指南](https://guides.github.com/)
- [Gitee 帮助](https://gitee.com/help)
