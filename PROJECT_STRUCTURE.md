# AudioInsight 项目结构（规划）

本文档描述实现后的完整项目结构。

```
audioinsight/
├── .env.example                 # 环境变量模板
├── .gitignore                   # Git 忽略文件
├── CLAUDE.md                    # Claude 配置（已存在）
├── CONTEXT.md                   # 项目概览和领域知识
├── SPECIFICATION.md             # 完整实现规格
├── README.md                    # 项目说明（待创建）
├── requirements.txt             # Python 依赖
├── Dockerfile                   # Docker 镜像构建
├── docker-compose.yml           # 本地开发环境
├── docker-compose.test.yml      # 测试环境
├── railway.json                 # Railway 部署配置
├── alembic.ini                  # Alembic 配置
├── audio-insight.http           # API 测试文件
│
├── app/                         # 应用代码
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口
│   ├── config.py                # 配置管理（pydantic-settings）
│   ├── database.py              # 数据库连接
│   ├── models.py                # SQLAlchemy 模型
│   ├── schemas.py               # Pydantic 请求/响应模型
│   │
│   ├── api/                     # API 路由层
│   │   ├── __init__.py
│   │   ├── recordings.py        # 录音相关接口
│   │   └── tasks.py             # 任务相关接口
│   │
│   └── services/                # 业务逻辑层
│       ├── __init__.py
│       ├── transcription.py     # Mock 转写服务
│       ├── summarization.py     # LLM 摘要服务
│       └── task_processor.py    # 任务处理器（状态机）
│
├── migrations/                  # Alembic 数据库迁移
│   ├── versions/
│   │   └── 001_initial_schema.py
│   └── env.py
│
├── tests/                       # 测试代码
│   ├── __init__.py
│   ├── conftest.py              # pytest 配置和 fixtures
│   ├── test_api.py              # API 集成测试
│   ├── test_task_processor.py   # 任务处理器测试
│   └── test_idempotency.py      # 幂等性测试
│
├── uploads/                     # 音频文件存储（.gitignore）
│
└── docs/                        # 文档
    ├── agents/                  # Agent 配置（已存在）
    │   ├── domain.md
    │   └── issue-tracker.md
    │
    └── adr/                     # 架构决策记录
        ├── README.md            # ADR 索引
        ├── ADR-001-technology-stack.md
        ├── ADR-002-async-processing.md
        ├── ADR-003-database-design.md
        ├── ADR-004-upload-idempotency.md
        ├── ADR-005-llm-streaming.md
        ├── ADR-006-testing-strategy.md
        └── ADR-007-deployment.md
```

## 关键文件说明

### 配置文件

- **`.env.example`**: 环境变量模板，包含 DATABASE_URL, DEEPSEEK_API_KEY 等
- **`alembic.ini`**: 数据库迁移工具配置
- **`docker-compose.yml`**: 本地开发环境（app + PostgreSQL）
- **`railway.json`**: Railway 平台部署配置

### 应用代码

- **`app/main.py`**: FastAPI 应用入口，路由注册，启动时任务恢复
- **`app/config.py`**: 使用 pydantic-settings 管理配置
- **`app/models.py`**: Recording 和 Task 的 SQLAlchemy 模型
- **`app/schemas.py`**: API 请求/响应的 Pydantic 模型

### API 层

- **`app/api/recordings.py`**: 
  - POST /v1/recordings (上传)
  - GET /v1/recordings (列表)
  - GET /v1/recordings/{id} (详情)
  - DELETE /v1/recordings/{id} (删除)
  
- **`app/api/tasks.py`**:
  - GET /v1/tasks/{id} (查询状态)
  - POST /v1/tasks/{id}/retry (重试)
  - GET /v1/recordings/{id}/summary/stream (流式摘要)

### 服务层

- **`app/services/transcription.py`**: Mock 转写（5-15s 延迟，20% 失败率）
- **`app/services/summarization.py`**: DeepSeek LLM 调用（结构化输出）
- **`app/services/task_processor.py`**: 
  - 任务调度和处理
  - 状态机实现
  - 自动重试逻辑
  - 并发控制（Semaphore）
  - 启动时任务恢复

### 测试

- **`tests/conftest.py`**: pytest fixtures（测试数据库、客户端等）
- **`tests/test_api.py`**: API 端点测试（上传、查询、重试、删除）
- **`tests/test_task_processor.py`**: 状态机、重试、恢复逻辑测试
- **`tests/test_idempotency.py`**: 文件哈希去重测试

### 文档

- **`CONTEXT.md`**: 项目概览、业务领域、技术架构、数据模型
- **`SPECIFICATION.md`**: 完整实现规格（54 个用户故事）
- **`docs/adr/`**: 7 个架构决策记录（技术栈、异步处理、数据库、幂等、流式、测试、部署）

## 数据流

```
用户上传文件
    ↓
POST /v1/recordings (API 层)
    ↓
录音文件保存到 uploads/
    ↓
创建 Recording + Task 记录（数据层）
    ↓
schedule_task() 启动后台处理（服务层）
    ↓
[后台协程] task_processor.process_task()
    ↓
更新状态: pending → transcribing
    ↓
mock_transcribe() - 5-15s，20% 失败
    ↓
更新状态: transcribing → summarizing
    ↓
llm_summarize() - DeepSeek API，60s 超时
    ↓
保存结果到 Task.transcript 和 Task.summary_json
    ↓
更新状态: summarizing → done
    ↓
用户通过 GET /v1/recordings/{id} 查询结果
```

## Git 提交历史（规划）

实现时应遵循的提交顺序：

1. `feat: 初始化项目结构和配置`
2. `feat: 添加数据库模型和迁移`
3. `feat: 实现上传接口和文件存储`
4. `feat: 实现 Mock 转写服务`
5. `feat: 集成 DeepSeek LLM 摘要`
6. `feat: 实现任务处理器和状态机`
7. `feat: 添加任务查询接口`
8. `feat: 实现重试和删除接口`
9. `feat: 添加自动重试和并发控制`
10. `feat: 实现启动时任务恢复`
11. `feat: 添加上传幂等性（文件哈希）`
12. `feat: 实现 LLM 流式输出（SSE）`
13. `test: 添加 API 集成测试`
14. `test: 添加任务处理器和幂等性测试`
15. `deploy: 添加 Docker 和 docker-compose 配置`
16. `deploy: 配置 Railway 部署`
17. `docs: 完善 README 和 API 文档`

## 下一步行动

1. ✅ 文档已完成（CONTEXT.md, SPECIFICATION.md, ADRs）
2. ⏭️ 等待用户确认文档
3. ⏭️ 开始创建项目结构
4. ⏭️ 实现核心功能
5. ⏭️ 实现加分项
6. ⏭️ 编写测试
7. ⏭️ Docker 化和部署
