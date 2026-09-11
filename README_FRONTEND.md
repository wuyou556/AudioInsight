# 🎨 前端使用指南

AudioInsight 提供了一个美观的单页应用界面，完整展现所有核心功能。

## 快速启动

### 方法 1: 直接打开（最简单）

直接在浏览器中打开 `frontend/index.html` 文件即可使用。

### 方法 2: HTTP 服务器（推荐）

```bash
# 进入前端目录
cd frontend

# Python 3
python -m http.server 8080

# 或使用 Node.js
npx http-server -p 8080

# Windows 快捷方式
双击 start.bat
```

然后访问 http://localhost:8080

## 后端 CORS 配置

在 `app/main.py` 中添加：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 主要功能

### 📤 上传录音
- 点击上传区域或拖拽文件
- 支持 MP3, WAV, M4A, AAC
- 自动上传并切换到列表

### 📋 我的录音
- 查看所有录音列表
- 实时状态显示（等待/转写/摘要/完成/失败）
- 分页浏览（每页10条）

### 👁️ 查看详情
- 完整转写文本
- AI 智能摘要
- 关键要点提取
- 待办事项列表

### 🔄 重试失败任务
- 一键重新处理失败任务

### 🗑️ 删除录音
- 删除录音及所有关联数据

## 界面特点

- 🎨 渐变紫色背景
- 💳 卡片式设计
- 📱 响应式布局
- ✨ 流畅动画效果
- 🏷️ 彩色状态徽章

详细文档见 [frontend/README.md](frontend/README.md)
