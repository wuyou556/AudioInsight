# AudioInsight - 录音转写与智能摘要服务

一个基于 FastAPI + PostgreSQL 的异步音频处理服务，支持音频文件上传、自动转写和 AI 智能摘要。

## 🎯 项目特性

### 后端服务
- ✅ FastAPI 异步 Web 框架
- ✅ PostgreSQL 数据库 + SQLAlchemy ORM
- ✅ Alembic 数据库迁移管理
- ✅ Docker Compose 一键启动
- ✅ 分层架构（API/服务/数据层）
- ✅ Pydantic Settings 配置管理
- ✅ 完整的 RESTful API
- ✅ DeepSeek AI 智能摘要
- ✅ 异步任务处理
- ✅ 性能优化（N+1 查询修复）

### 前端应用
- ✅ 美观的单页应用
- ✅ 响应式设计（手机/平板/桌面）
- ✅ 拖拽上传
- ✅ 实时状态更新
- ✅ 完整功能展示

## 🚀 核心功能

1. **📤 音频上传** - 支持 MP3, WAV, M4A, AAC 格式
2. **🎙️ 自动转写** - Mock 转写（可扩展真实 ASR）
3. **✨ AI 摘要** - DeepSeek AI 智能生成摘要、要点、待办
4. **📋 录音管理** - 列表查询、详情查看、分页浏览
5. **🔄 失败重试** - 手动重试失败任务
6. **🗑️ 删除功能** - 删除录音及关联数据

## 📸 界面预览

访问前端应用查看：
- 渐变紫色背景设计
- 卡片式布局
- 彩色状态徽章
- 流畅的交互动画

## 技术栈

- **Web 框架**: FastAPI 0.115.0
- **数据库**: PostgreSQL 15
- **ORM**: SQLAlchemy 2.0.35 (异步)
- **迁移工具**: Alembic 1.13.3
- **数据验证**: Pydantic 2.9.2
- **ASGI 服务器**: Uvicorn 0.30.6

## 项目结构

```
audioinsight/
├── app/                      # 应用代码
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接
│   ├── models.py            # SQLAlchemy 模型
│   ├── api/                 # API 路由层
│   │   └── __init__.py
│   └── services/            # 业务逻辑层
│       └── __init__.py
├── migrations/              # Alembic 数据库迁移
│   ├── versions/
│   │   └── 001_initial_schema.py
│   ├── env.py
│   └── script.py.mako
├── tests/                   # 测试代码
├── uploads/                 # 音频文件存储
├── docs/                    # 文档
├── .env.example             # 环境变量模板
├── .gitignore
├── alembic.ini              # Alembic 配置
├── docker-compose.yml       # Docker Compose 配置
├── Dockerfile               # Docker 镜像构建
├── requirements.txt         # Python 依赖
└── README.md
```

## 快速开始

### 1. 环境准备

确保已安装：
- Docker & Docker Compose
- Python 3.11+ (如果需要本地开发)

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量：

```env
DATABASE_URL=postgresql+asyncpg://audioinsight:password@localhost:5432/audioinsight
DEEPSEEK_API_KEY=your-api-key-here
```

### 3. 启动服务

使用 Docker Compose 一键启动：

```bash
docker-compose up
```

服务将在以下端口启动：
- **API 服务**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **API 文档**: http://localhost:8000/docs

### 4. 验证服务

访问健康检查端点：

```bash
curl http://localhost:8000/health
```

预期响应：

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-09-10T11:05:00.000000"
}
```

## 数据库设计

### recordings 表

存储音频文件元数据：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| filename | VARCHAR(255) | 原始文件名 |
| file_path | VARCHAR(512) | 文件存储路径 |
| file_size | INTEGER | 文件大小（字节）|
| mime_type | VARCHAR(100) | MIME 类型 |
| file_hash | VARCHAR(64) | SHA256 文件哈希（唯一） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

**索引**:
- `idx_recordings_file_hash` (UNIQUE)
- `idx_recordings_created_at`

### tasks 表

存储处理任务：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| recording_id | UUID | 关联的录音 ID（外键）|
| status | VARCHAR(50) | 任务状态 |
| transcript | TEXT | 转写结果 |
| summary_json | TEXT | 摘要结果（JSON）|
| error_message | TEXT | 错误信息 |
| retry_count | INTEGER | 重试次数 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

**索引**:
- `idx_tasks_recording_id`
- `idx_tasks_status`
- `idx_tasks_updated_at`

**外键**: `recording_id` → `recordings.id` (CASCADE DELETE)

## API 端点

### 健康检查

```http
GET /health
```

返回服务状态和数据库连接状态。

### 根端点

```http
GET /
```

返回服务信息和文档链接。

## 开发指南

### 本地开发

1. 创建虚拟环境：

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 启动数据库：

```bash
docker-compose up -d db
```

4. 运行数据库迁移：

```bash
alembic upgrade head
```

5. 启动开发服务器：

```bash
uvicorn app.main:app --reload
```

### 数据库迁移

创建新迁移：

```bash
alembic revision --autogenerate -m "描述"
```

应用迁移：

```bash
alembic upgrade head
```

回滚迁移：

```bash
alembic downgrade -1
```

### 运行测试

```bash
pytest tests/ -v
```

## 配置说明

所有配置通过环境变量管理，参考 `.env.example`：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 连接字符串 | - |
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | - |
| DEEPSEEK_API_BASE | DeepSeek API 基础 URL | https://api.deepseek.com/v1 |
| MAX_CONCURRENT_TASKS | 最大并发任务数 | 3 |
| MAX_RETRIES | 最大重试次数 | 3 |
| ZOMBIE_TASK_TIMEOUT | 僵尸任务超时（秒） | 300 |
| UPLOAD_DIR | 文件上传目录 | ./uploads |
| MAX_FILE_SIZE | 最大文件大小（字节） | 52428800 (50MB) |

## 停止服务

```bash
docker-compose down
```

保留数据卷：

```bash
docker-compose down
```

删除数据卷（清空数据库）：

```bash
docker-compose down -v
```

## 接受标准

- ✅ 项目目录结构创建完成（app/api, app/services, tests, migrations, uploads）
- ✅ FastAPI 应用骨架搭建，带基础配置（config.py 使用 pydantic-settings）
- ✅ SQLAlchemy 模型定义（Recording 和 Task 表）
- ✅ Alembic 初始化，初始迁移脚本创建两张表
- ✅ docker-compose.yml 配置（app + PostgreSQL 服务）
- ✅ GET /health 端点返回 {status: "healthy", database: "connected", timestamp}
- ✅ .env.example 文件包含所有必需的环境变量
- ✅ requirements.txt 包含所有依赖
- ⏳ 服务启动成功，健康检查通过（需要 Docker 运行）

## 许可证

本项目为笔试项目，仅供学习和评估使用。

## 作者

AudioInsight Team
