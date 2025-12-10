# GitHub API 速率限制解决方案

## 问题描述
当频繁调用GitHub API检查版本更新时，会遇到速率限制错误：
```
GitHub API速率限制已达到，使用缓存数据或稍后再试
```

## 解决方案

### 1. 使用GitHub Personal Access Token（推荐）

#### 创建Token：
1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token" -> "Generate new token (classic)"
3. 设置过期时间和权限（只需要 public_repo 权限）
4. 复制生成的token

#### 配置Token：

**方法1：环境变量**
```bash
set GITHUB_TOKEN=your_token_here
```

**方法2：配置文件**
1. 复制 `github_config.json.example` 为 `github_config.json`
2. 填入你的token：
```json
{
  "github_token": "ghp_xxxxxxxxxxxxxxxxxxxx"
}
```

### 2. 缓存机制
- 系统会自动缓存API响应2小时
- 遇到速率限制时会使用旧缓存数据
- 缓存文件位置：`%TEMP%/multifun_debug_tool_update/version_cache.json`

### 3. 速率限制对比
- **无Token**: 60次/小时
- **有Token**: 5000次/小时

## 测试命令
```bash
# 命令行测试
python test_version_check.py --cli

# GUI测试
python test_version_check.py
```

## 故障排除
1. 如果仍然遇到速率限制，检查token是否正确配置
2. 清除缓存：删除 `%TEMP%/multifun_debug_tool_update/` 目录
3. 检查网络连接和GitHub访问权限