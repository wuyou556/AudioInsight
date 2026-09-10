# ADR-003: 数据库设计

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

需要设计数据库表结构来存储录音文件信息和处理任务状态。关键需求：
- 一个录音可以有多个处理任务（支持重试历史）
- 任务包含状态、转写文本、结构化摘要
- 支持按创建时间倒序分页查询录音列表
- 删除录音时自动删除关联的所有任务
- 支持文件哈希去重（幂等性）

可选方案：
1. **两张独立表**（recordings + tasks，一对多关系）
2. **单表存储**（所有信息在 recordings 表）
3. **一对一关系**（重试时更新同一个任务记录）

## 决策

采用 **两张独立表，一对多关系** 方案。

### 表结构

**recordings 表**:
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

CREATE INDEX idx_recordings_file_hash ON recordings(file_hash);
CREATE INDEX idx_recordings_created_at ON recordings(created_at DESC);
```

**tasks 表**:
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recording_id UUID NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,  -- pending, transcribing, summarizing, done, failed
    transcript TEXT,
    summary_json JSONB,  -- {summary: string, key_points: string[], todos: string[]}
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_recording_id ON tasks(recording_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_updated_at ON tasks(updated_at);
```

### SQLAlchemy 模型

```python
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

class Recording(Base):
    __tablename__ = "recordings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(50))
    file_hash = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    tasks = relationship("Task", back_populates="recording", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recording_id = Column(UUID(as_uuid=True), ForeignKey("recordings.id"), nullable=False)
    status = Column(String(20), nullable=False)
    transcript = Column(Text)
    summary_json = Column(JSONB)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    recording = relationship("Recording", back_populates="tasks")
```

## 考虑的替代方案

### 方案 2: 单表存储

**表结构**:
```sql
CREATE TABLE recordings (
    id UUID PRIMARY KEY,
    filename VARCHAR(255),
    file_path VARCHAR(512),
    status VARCHAR(20),
    transcript TEXT,
    summary_json JSONB,
    error_message TEXT,
    retry_count INTEGER,
    ...
);
```

**优点**:
- 表结构简单
- 查询录音详情时无需 JOIN

**缺点**:
- 无法保留重试历史（每次重试覆盖原数据）
- 职责不清晰（录音和任务混在一起）
- 扩展性差（如未来支持多种处理类型）

**拒绝理由**: 无法满足"保留重试历史"的需求，且违背单一职责原则。

### 方案 3: 一对一关系

**表结构**: 与方案 1 相同，但一个 recording 只有一个 task

**优点**:
- 简化查询逻辑
- 数据量更少

**缺点**:
- 重试时需要更新同一个任务记录，丢失历史
- 难以追踪"为什么失败了 3 次"

**拒绝理由**: 调试和运维时需要查看完整的重试历史。

## 决策理由

1. **职责分离**: Recording 代表文件元数据，Task 代表处理工作，职责清晰
2. **重试历史**: 每次重试创建新 Task，保留完整历史（便于调试）
3. **扩展性**: 未来可以扩展多种任务类型（如"重新转写"、"重新摘要"）
4. **级联删除**: 通过 `ON DELETE CASCADE`，删除录音自动清理所有任务
5. **JSONB 类型**: PostgreSQL 原生支持，高效存储和查询结构化摘要

## 后果

### 积极影响

- ✅ 清晰的数据模型，易于理解
- ✅ 重试历史可追溯，便于调试
- ✅ 支持复杂查询（如"查找所有失败超过 3 次的录音"）
- ✅ 级联删除自动清理关联数据
- ✅ JSONB 类型支持灵活的摘要结构

### 消极影响

- ❌ 查询录音详情时需要 JOIN（性能影响小，可通过索引优化）
- ❌ 多次重试会产生多条任务记录（存储开销可接受）

### 查询优化

**获取录音最新任务**:
```sql
SELECT r.*, t.*
FROM recordings r
LEFT JOIN LATERAL (
    SELECT * FROM tasks
    WHERE recording_id = r.id
    ORDER BY created_at DESC
    LIMIT 1
) t ON true
WHERE r.id = :recording_id;
```

**录音列表分页（带最新任务状态）**:
```sql
SELECT r.*, 
       (SELECT status FROM tasks WHERE recording_id = r.id ORDER BY created_at DESC LIMIT 1) AS latest_status
FROM recordings r
ORDER BY r.created_at DESC
LIMIT :page_size OFFSET :offset;
```

### 索引策略

- `idx_recordings_file_hash`: 支持幂等性检查（O(1) 查找）
- `idx_recordings_created_at`: 支持分页查询排序
- `idx_tasks_recording_id`: 加速 JOIN 查询
- `idx_tasks_status`: 支持按状态过滤（如查找所有 pending 任务）
- `idx_tasks_updated_at`: 支持僵尸任务检测

## 数据完整性

### 外键约束

```sql
FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
```

确保：
- 任务必须关联到存在的录音
- 删除录音时自动删除所有关联任务

### 唯一性约束

```sql
file_hash VARCHAR(64) UNIQUE NOT NULL
```

确保：
- 相同文件不会重复存储（幂等性）
- 哈希冲突会被数据库拒绝（实际上 SHA256 冲突概率极低）

### 状态枚举

虽然数据库层面使用 `VARCHAR(20)`，但应用层使用 Python Enum 限制可选值：

```python
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"
```

## 迁移策略

使用 Alembic 管理数据库版本：

```bash
# 初始化
alembic init migrations

# 创建迁移
alembic revision --autogenerate -m "Create recordings and tasks tables"

# 执行迁移
alembic upgrade head
```

## 相关决策

- ADR-002: 异步处理方案（任务状态存储和查询）
- ADR-004: 上传幂等实现（file_hash 字段用途）
