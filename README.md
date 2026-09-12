# AudioInsight - 音频转写与智能摘要服务

一个基于 FastAPI + PostgreSQL 的异步音频处理服务，支持音频文件上传、自动转写和 AI 智能摘要。

[![Railway Deploy](https://img.shields.io/badge/Railway-Deploy-blueviolet)](https://audioinsight-production.up.railway.app)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📋 目录

- [项目概览](#项目概览)
- [在线演示](#在线演示)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [数据库设计](#数据库设计)
- [API 文档](#api-文档)
- [开发指南](#开发指南)
- [测试](#测试)
- [已知问题与限制](#已知问题与限制)
- [未来规划](#未来规划)

## 📖 项目概览

AudioInsight 是一个现代化的音频处理服务，旨在简化音频转写和智能分析流程。用户可以上传音频文件，系统会自动进行转写，并使用 AI 生成结构化摘要，提取关键要点和待办事项。

### 设计目标

- **异步处理**：上传即时响应，后台异步处理，避免长时间等待
- **高并发**：支持多文件并发上传，信号量控制防止过载
- **幂等性**：基于文件哈希的去重机制，避免重复处理
- **容错性**：自动重试机制，服务重启后任务恢复
- **可扩展**：分层架构，易于扩展转写引擎和 AI 模型

## 🌐 在线演示

- **前端界面**: https://audioinsight-production.up.railway.app
- **API 文档**: https://audioinsight-production.up.railway.app/docs
- **健康检查**: https://audioinsight-production.up.railway.app/health

## 🚀 核心功能

### 后端服务
- ✅ **异步任务处理** - 基于 asyncio 的高性能异步处理
- ✅ **文件去重** - SHA256 哈希去重，避免重复处理
- ✅ **并发控制** - 信号量限制并发数，防止资源耗尽
- ✅ **自动重试** - 指数退避重试，最大 3 次
- ✅ **任务恢复** - 服务重启后自动恢复未完成任务
- ✅ **性能优化** - 非阻塞 I/O，N+1 查询优化
- ✅ **DeepSeek AI** - 智能摘要生成

### 前端应用
- ✅ **现代化 UI** - 渐变紫色主题，响应式设计
- ✅ **拖拽上传** - 支持批量上传，实时进度显示
- ✅ **自动刷新** - 处理中任务自动轮询更新
- ✅ **完整功能** - 上传、查询、删除、重试一应俱全

### 支持格式
- 音频格式：MP3, WAV, M4A, AAC
- 最大文件：50MB
- 批量上传：支持多文件并发

## 🏗️ 系统架构

### 架构流程图

```
┌─────────────┐
│   用户上传   │
│  音频文件   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│              FastAPI Web 服务                    │
│  ┌──────────────────────────────────────────┐  │
│  │  上传接口 (POST /v1/recordings)          │  │
│  │  - 文件验证（格式、大小）                 │  │
│  │  - SHA256 哈希计算（去重）                │  │
│  │  - 异步文件写入（aiofiles）               │  │
│  │  - 创建 Recording + Task 记录             │  │
│  │  - 立即返回 202 (recording_id, task_id)  │  │
│  └──────────┬───────────────────────────────┘  │
│             │                                    │
│             ▼                                    │
│  ┌──────────────────────────────────────────┐  │
│  │      后台任务处理器 (asyncio)             │  │
│  │  - 信号量控制并发 (max 5 uploads)         │  │
│  │  - 转写任务信号量 (max 3 tasks)           │  │
│  │  - 指数退避重试 (max 3 retries)           │  │
│  └──────────┬───────────────────────────────┘  │
└─────────────┼───────────────────────────────────┘
              │
              ▼
     ┌────────────────┐
     │  任务处理流程   │
     └────────┬───────┘
              │
              ├─► 转写 (Mock/ASR) → transcript
              │
              └─► AI 摘要 (DeepSeek) → summary_json
                  {
                    "summary": "...",
                    "key_points": [...],
                    "todos": [...]
                  }
              │
              ▼
     ┌────────────────┐
     │  更新任务状态   │
     │  status: done  │
     └────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│         PostgreSQL 数据库            │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  recordings  │  │    tasks    │ │
│  │  (元数据)     │◄─┤ (处理结果)  │ │
│  └──────────────┘  └─────────────┘ │
│   - file_hash      - transcript    │
│   - file_path      - summary_json  │
│   - created_at     - status        │
└─────────────────────────────────────┘
              │
              ▼
     ┌────────────────┐
     │  前端查询结果   │
     │  GET /v1/...   │
     └────────────────┘
```

### 数据流

1. **上传阶段** (同步)
   - 客户端 → FastAPI → 文件验证 → 哈希计算 → 数据库写入
   - 返回：`recording_id`, `task_id`, `status: pending`

2. **处理阶段** (异步)
   - 后台任务队列 → 转写 → AI 摘要 → 更新状态
   - 状态流转：`pending` → `transcribing` → `summarizing` → `done` / `failed`

3. **查询阶段** (同步)
   - 客户端轮询 → 获取最新状态 → 展示结果

## 💻 技术栈

### 后端技术选型

| 技术 | 版本 | 选择理由 |
|------|------|----------|
| **Python** | 3.11+ | 成熟的异步生态，丰富的 AI/ML 库 |
| **FastAPI** | 0.115.0 | 原生异步支持，自动生成 OpenAPI 文档，高性能 |
| **PostgreSQL** | 15 | 成熟稳定的关系数据库，支持 JSON 类型，ACID 保证 |
| **SQLAlchemy** | 2.0.35 | 异步 ORM，类型安全，支持数据库迁移 |
| **asyncpg** | 0.31.0 | 高性能异步 PostgreSQL 驱动 |
| **Alembic** | 1.13.3 | 数据库版本管理，团队协作必备 |
| **aiofiles** | 24.1.0 | 真正的异步文件 I/O，避免阻塞事件循环 |

### 为什么选择 FastAPI？

1. **原生异步**: 基于 Starlette，充分利用 asyncio 处理高并发
2. **类型安全**: Pydantic 数据验证，减少运行时错误
3. **自动文档**: 零配置生成 Swagger UI 和 ReDoc
4. **性能优秀**: 与 Node.js、Go 同级别的性能表现
5. **生态成熟**: 插件丰富，社区活跃

### 为什么选择 PostgreSQL？

1. **ACID 保证**: 任务状态一致性至关重要
2. **JSON 支持**: `summary_json` 字段存储结构化摘要
3. **外键约束**: 自动级联删除，数据完整性
4. **索引优化**: 支持复合索引，查询性能优秀
5. **成熟稳定**: 企业级可靠性

### 为什么选择异步架构？

1. **用户体验**: 上传立即返回，不阻塞客户端
2. **资源利用**: 单进程处理数千并发连接
3. **成本优化**: 单实例支撑更高吞吐量
4. **可扩展性**: 易于水平扩展（多实例 + 消息队列）

## ⚡ 快速开始

### 前置要求

- Docker & Docker Compose
- Python 3.11+ (可选，用于本地开发)
- DeepSeek API Key (用于 AI 摘要)

### 1. 克隆项目

```bash
git clone https://github.com/wuyou556/AudioInsight.git
cd AudioInsight
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 数据库配置（Docker Compose 会自动使用）
DATABASE_URL=postgresql+asyncpg://audioinsight:password@db:5432/audioinsight

# DeepSeek API 配置（必需）
DEEPSEEK_API_KEY=your-api-key-here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# 任务处理配置
MAX_CONCURRENT_TASKS=3     # 最大并发转写任务数
MAX_RETRIES=3              # 失败自动重试次数
ZOMBIE_TASK_TIMEOUT=300    # 僵尸任务超时（秒）

# 文件上传配置
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=52428800     # 50MB
```

### 3. 一键启动

```bash
docker-compose up
```

服务启动后：
- **前端界面**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **数据库**: localhost:5432

### 4. 验证服务

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-09-12T10:00:00.000000"
}
```

## 🗄️ 数据库设计

### ER 图

```
┌─────────────────────────────────────┐
│          recordings                  │
├─────────────────────────────────────┤
│ id (PK, UUID)                        │
│ filename (VARCHAR 255)               │
│ file_path (VARCHAR 512)              │
│ file_size (INTEGER)                  │
│ mime_type (VARCHAR 100)              │
│ file_hash (VARCHAR 64) UNIQUE        │
│ created_at (TIMESTAMP)               │
│ updated_at (TIMESTAMP)               │
└──────────┬──────────────────────────┘
           │
           │ 1:N
           │
           ▼
┌─────────────────────────────────────┐
│            tasks                     │
├─────────────────────────────────────┤
│ id (PK, UUID)                        │
│ recording_id (FK) ON DELETE CASCADE  │
│ status (VARCHAR 50)                  │
│ transcript (TEXT)                    │
│ summary_json (TEXT)                  │
│ error_message (TEXT)                 │
│ retry_count (INTEGER)                │
│ created_at (TIMESTAMP)               │
│ updated_at (TIMESTAMP)               │
└─────────────────────────────────────┘
```

### 表结构详情

#### recordings 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PRIMARY KEY | 录音唯一标识 |
| filename | VARCHAR(255) | NOT NULL | 原始文件名 |
| file_path | VARCHAR(512) | NOT NULL | 服务器存储路径 |
| file_size | INTEGER | NOT NULL | 文件大小（字节）|
| mime_type | VARCHAR(100) | NOT NULL | MIME 类型 |
| file_hash | VARCHAR(64) | UNIQUE NOT NULL | SHA256 哈希（去重用）|
| created_at | TIMESTAMP | NOT NULL | 创建时间 |
| updated_at | TIMESTAMP | NOT NULL | 更新时间 |

**索引**:
- `idx_recordings_file_hash` - 用于快速去重查询
- `idx_recordings_created_at` - 用于列表分页排序

#### tasks 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PRIMARY KEY | 任务唯一标识 |
| recording_id | UUID | FK, ON DELETE CASCADE | 关联录音 ID |
| status | VARCHAR(50) | NOT NULL | pending/transcribing/summarizing/done/failed |
| transcript | TEXT | NULL | 转写文本 |
| summary_json | TEXT | NULL | AI 摘要 JSON |
| error_message | TEXT | NULL | 失败原因 |
| retry_count | INTEGER | DEFAULT 0 | 已重试次数 |
| created_at | TIMESTAMP | NOT NULL | 创建时间 |
| updated_at | TIMESTAMP | NOT NULL | 更新时间 |

**索引**:
- `idx_tasks_recording_id` - 用于按录音查询任务
- `idx_tasks_status` - 用于按状态筛选
- `idx_tasks_updated_at` - 用于检测僵尸任务

**外键约束**:
- `recording_id` → `recordings.id` (ON DELETE CASCADE)
  - 删除录音时自动删除关联任务

### DDL

详见 [migrations/versions/001_initial_schema.py](migrations/versions/001_initial_schema.py)

## 📚 API 文档

### 端点概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息（前端页面）|
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc 文档 |
| `/v1/recordings` | POST | 上传音频文件 |
| `/v1/recordings` | GET | 获取录音列表（分页）|
| `/v1/recordings/{id}` | GET | 获取录音详情 |
| `/v1/recordings/{id}` | DELETE | 删除录音 |
| `/v1/tasks` | GET | 获取任务列表（分页）|
| `/v1/tasks/{id}` | GET | 获取任务详情 |
| `/v1/tasks/{id}/retry` | POST | 重试失败任务 |

### 完整测试用例

详见 [audio-insight.http](audio-insight.http) 文件，包含所有端点的测试用例。

使用方法：
1. 安装 VS Code REST Client 插件
2. 打开 `audio-insight.http`
3. 修改 `@apiUrl` 变量选择环境
4. 点击 `Send Request` 执行测试

## 🛠️ 开发指南

### 本地开发环境

1. **创建虚拟环境**

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **启动数据库**

```bash
docker-compose up -d db
```

4. **运行数据库迁移**

```bash
alembic upgrade head
```

5. **启动开发服务器**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 数据库迁移

**创建新迁移**:
```bash
alembic revision --autogenerate -m "描述变更"
```

**应用迁移**:
```bash
alembic upgrade head
```

**回滚迁移**:
```bash
alembic downgrade -1
```

**查看历史**:
```bash
alembic history
```

### 代码质量

项目遵循 Python 最佳实践：
- 类型注解（Type Hints）
- Pydantic 数据验证
- SQLAlchemy 2.0 风格
- 异步优先（async/await）
- 分层架构（API/Service/Repository）

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_api.py -v

# 生成覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

### 测试覆盖

项目包含完整的单元测试和集成测试：
- API 端点测试
- 数据库操作测试
- 任务处理逻辑测试
- 边界条件和错误场景测试

## ⚠️ 已知问题与限制

### 1. 单实例限制

**现状**: 当前部署为单个 Railway 实例，无状态共享。

**影响**:
- 多实例部署会导致任务重复处理
- 无法实现真正的水平扩展

**解决方案** (未实现):
- 引入 Redis 分布式锁
- 使用消息队列（RabbitMQ/Celery）

### 2. 僵尸任务检测延迟

**现状**: 僵尸任务检测间隔为 5 分钟（`ZOMBIE_TASK_TIMEOUT=300`）

**影响**:
- 任务卡住后最多 5 分钟才会被重置
- 影响用户体验

**缓解措施**:
- 已实现服务重启时自动恢复
- 用户可手动重试

### 3. 本地文件存储非持久化

**现状**: Railway 的文件系统是临时的，重启后丢失。

**影响**:
- 上传的音频文件会在容器重启后丢失
- 数据库记录仍在，但文件不存在

**解决方案** (未实现):
- 集成对象存储（AWS S3 / Cloudinary）
- 文件上传直接到对象存储

### 4. 转写功能为 Mock

**现状**: 转写使用 Mock 实现，返回固定文本。

**原因**: 真实 ASR 服务需要额外配置和成本。

**扩展方向**:
- 集成 Whisper API
- 集成阿里云/腾讯云语音识别

### 5. 缺少用户认证

**现状**: 所有 API 端点无需认证。

**影响**: 无法多租户隔离，无法追踪使用量。

**未来规划**:
- JWT 认证
- 用户配额管理

### 6. 无速率限制

**现状**: 无 API 调用频率限制。

**风险**: 可能被滥用或 DDoS。

**未来规划**:
- 集成 slowapi 限流中间件

## 🚧 未来规划

由于时间限制，以下功能未实现但已在路线图中：

### 短期 (1-2 周)

- [ ] 集成真实 ASR 服务（Whisper/阿里云）
- [ ] 对象存储集成（S3/Cloudinary）
- [ ] WebSocket 实时推送任务状态
- [ ] 用户认证与授权

### 中期 (1-2 月)

- [ ] Redis 分布式锁
- [ ] 消息队列（Celery + Redis）
- [ ] 管理后台界面
- [ ] 数据导出功能（CSV/JSON）

### 长期 (3+ 月)

- [ ] 多语言支持
- [ ] 自定义 AI 提示词
- [ ] 批量处理 API
- [ ] 监控和告警（Prometheus + Grafana）

## 📊 项目里程碑

项目通过增量开发完成，Git 提交历史展示了完整的开发过程：

```bash
# 查看提交历史
git log --oneline --graph

# 主要里程碑：
# 1. 项目初始化 - 目录结构、Docker 配置
# 2. 数据库设计 - SQLAlchemy 模型、Alembic 迁移
# 3. 基础 API - 上传、查询接口
# 4. 异步处理 - 后台任务、重试机制
# 5. 性能优化 - N+1 查询、并发控制
# 6. 前端开发 - 单页应用
# 7. 部署上线 - Railway 集成
# 8. 文档完善 - README、API 测试文件
```

共计 20+ 有意义的提交，每个提交都是可运行的增量功能。

## 📝 配置说明

所有配置通过环境变量管理：

| 变量 | 说明 | 默认值 | 必需 |
|------|------|--------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | - | ✅ |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - | ✅ |
| `DEEPSEEK_API_BASE` | DeepSeek API 基础 URL | https://api.deepseek.com/v1 | ❌ |
| `MAX_CONCURRENT_TASKS` | 最大并发任务数 | 3 | ❌ |
| `MAX_RETRIES` | 最大重试次数 | 3 | ❌ |
| `ZOMBIE_TASK_TIMEOUT` | 僵尸任务超时（秒） | 300 | ❌ |
| `UPLOAD_DIR` | 文件上传目录 | ./uploads | ❌ |
| `MAX_FILE_SIZE` | 最大文件大小（字节） | 52428800 | ❌ |

## 🤝 贡献指南

本项目为学习和评估用途，暂不接受外部贡献。

## 📄 许可证

本项目仅供学习和评估使用。

## 👥 作者

AudioInsight Team - 2026

---

**部署地址**: https://audioinsight-production.up.railway.app

**文档更新日期**: 2026-09-12
