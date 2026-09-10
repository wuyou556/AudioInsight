# AudioInsight - 录音转写与智能摘要服务

## 项目概述

AudioInsight 是一个异步录音处理服务，提供音频文件的转写和智能摘要功能。用户上传音频文件后立即获得任务 ID，服务在后台完成转写和摘要生成，用户可查询任务状态和结果。

**项目类型**: 后端笔试项目  
**开发周期**: 4 个自然日（预计 12-16 小时实际工作量）  
**提交要求**: 保留完整 commit 历史，提供一键启动方式

## 业务领域

### 核心概念

**Recording（录音）**
- 用户上传的音频文件及其元数据
- 属性：文件名、存储路径、文件大小、MIME 类型、文件哈希
- 生命周期：创建 → 处理中 → 完成/失败 → 可被删除

**Task（处理任务）**
- 关联到一个 Recording 的异步处理工作单元
- 包含转写文本和摘要结果
- 一个 Recording 可以有多个 Task（重试场景）

**Transcription（转写）**
- 将音频内容转换为文本的过程
- 本项目使用 Mock 实现（模拟 ASR 行为）

**Summarization（摘要）**
- 对转写文本生成结构化摘要的过程
- 使用真实 LLM API（DeepSeek）
- 输出结构：一句话摘要、关键要点列表、待办事项列表

### 任务状态机

```
pending → transcribing → summarizing → done
   ↓           ↓              ↓
   └─────────→ failed ←───────┘
                 ↓
              (retry) → pending
```

**状态说明**:
- `pending`: 任务已创建，等待处理
- `transcribing`: 正在进行转写
- `summarizing`: 正在生成摘要
- `done`: 处理成功完成
- `failed`: 处理失败（转写或摘要阶段）

**状态转换规则**:
- 任一阶段失败进入 `failed` 状态
- `failed` 状态可通过重试接口或自动重试回到 `pending`
- 自动重试最多 3 次（指数退避：1s, 2s, 4s）

## 技术架构

### 技术栈

**后端框架**: Python 3.11+ + FastAPI
- 原生异步支持，性能优异
- 自动 OpenAPI 文档生成
- 强类型的请求/响应验证（Pydantic）

**数据库**: PostgreSQL 15
- 关系型数据，支持事务
- JSONB 类型高效存储摘要结果
- 丰富的索引和查询能力

**LLM 服务**: DeepSeek API
- 国内访问友好
- API 兼容 OpenAI 格式
- 支持结构化输出（JSON mode）

**异步处理**: asyncio + 后台协程池
- 轻量级，无额外中间件依赖
- 通过数据库状态持久化，支持服务重启恢复
- 使用 `asyncio.Semaphore` 实现并发控制

**部署**: Docker Compose
- 一键启动（包含应用和数据库）
- 环境一致性保证

### 架构模式

**分层架构**:
```
API 层 (FastAPI Routes)
    ↓
服务层 (Business Logic)
    ↓
数据层 (SQLAlchemy ORM)
    ↓
数据库 (PostgreSQL)
```

**异步处理流程**:
```
1. 客户端上传 → API 创建 Recording + Task → 立即返回 202
2. 后台任务处理器从队列获取 pending 任务
3. 执行转写 → 更新状态为 transcribing
4. 执行摘要 → 更新状态为 summarizing
5. 保存结果 → 更新状态为 done
6. 任一步骤失败 → 自动重试或进入 failed
```

## 数据模型

### Recordings 表
```sql
CREATE TABLE recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type VARCHAR(50),
    file_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256，用于幂等性
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tasks 表
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recording_id UUID NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,
    transcript TEXT,
    summary_json JSONB,  -- {summary, key_points[], todos[]}
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_recording_id ON tasks(recording_id);
CREATE INDEX idx_tasks_status ON tasks(status);
```

**关系**: Recordings 1:N Tasks（一个录音可以有多个任务，支持重试历史）

## API 设计

### 核心接口（P0）

**上传录音**
```
POST /v1/recordings
Content-Type: multipart/form-data

Body:
  - file: 音频文件（wav/mp3/m4a/aac，≤50MB）
  - force_reprocess: boolean（可选，强制重新处理）

Response 201:
{
  "recording_id": "uuid",
  "task_id": "uuid",
  "status": "pending",
  "is_duplicate": false
}
```

**查询任务状态**
```
GET /v1/tasks/{task_id}

Response 200:
{
  "task_id": "uuid",
  "recording_id": "uuid",
  "status": "transcribing",
  "created_at": "2026-09-10T10:30:00Z",
  "updated_at": "2026-09-10T10:30:05Z"
}
```

**查询录音详情**
```
GET /v1/recordings/{id}

Response 200:
{
  "recording_id": "uuid",
  "filename": "meeting.mp3",
  "file_size": 5242880,
  "created_at": "2026-09-10T10:30:00Z",
  "latest_task": {
    "task_id": "uuid",
    "status": "done",
    "transcript": "转写文本...",
    "summary": {
      "summary": "一句话摘要",
      "key_points": ["要点1", "要点2"],
      "todos": ["待办1"]
    }
  }
}
```

**录音列表（分页）**
```
GET /v1/recordings?page=1&page_size=20

Response 200:
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

**重试失败任务**
```
POST /v1/tasks/{task_id}/retry

Response 200:
{
  "task_id": "uuid",
  "status": "pending"
}

Error 409 (非 failed 状态):
{
  "error": {
    "code": "TASK_NOT_FAILED",
    "message": "Only failed tasks can be retried"
  }
}
```

**删除录音**
```
DELETE /v1/recordings/{id}

Response 204 No Content
```

### 加分项接口

**流式摘要生成**
```
GET /v1/recordings/{id}/summary/stream

Response: text/event-stream
data: {"chunk": "这是"}
data: {"chunk": "一个"}
data: {"chunk": "会议摘要"}
data: [DONE]
```

## 质量属性

### 可靠性
- 自动重试机制（3 次，指数退避）
- 服务重启后自动恢复未完成任务
- 检测并重置僵尸任务（超 5 分钟未更新的处理中任务）

### 性能
- 并发控制：最多 3 个任务同时处理
- 文件哈希流式计算，避免大文件内存占用
- 数据库索引优化查询性能

### 可观测性
- 结构化日志记录任务生命周期关键节点
- 任务状态可追溯（通过 created_at/updated_at）

### 可测试性
- 分层架构便于单元测试
- Mock 转写降低测试复杂度
- 提供测试覆盖：API 端点、状态机、幂等性、重试逻辑

## 开发约束

### 必须实现
- ✅ 所有核心功能（P0）
- ✅ 统一错误响应结构
- ✅ 关键路径日志
- ✅ 数据库迁移脚本
- ✅ 一键启动方式（Docker Compose）
- ✅ API 调试文件（.http 格式）

### 加分项（本项目全实现）
- ✅ 失败自动重试
- ✅ 服务重启恢复
- ✅ 并发控制
- ✅ 上传幂等
- ✅ LLM 流式输出
- ✅ 测试
- ✅ 部署（Railway）

### 明确不考察
- ❌ 用户注册/登录/鉴权
- ❌ 前端页面
- ❌ 高并发性能优化

## 配置管理

使用 `.env` 文件 + `pydantic-settings`：

```env
DATABASE_URL=postgresql://user:password@db:5432/audioinsight
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MAX_CONCURRENT_TASKS=3
UPLOAD_DIR=./uploads
```

## 关键决策参考

详细的架构决策记录请参见 `docs/adr/` 目录：
- ADR-001: 技术栈选择
- ADR-002: 异步处理方案
- ADR-003: 数据库设计
- ADR-004: 上传幂等实现
- ADR-005: LLM 流式输出设计
- ADR-006: 测试策略
