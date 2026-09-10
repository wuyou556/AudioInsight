# ADR-002: 异步处理方案

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

项目核心需求是异步处理录音文件：用户上传后立即返回，后台完成转写和摘要生成。关键约束：
- 转写阶段耗时 5-15 秒（Mock）
- LLM 摘要耗时 10-60 秒（真实 API 调用）
- 服务重启后未完成的任务不能丢失
- 需要支持失败自动重试（加分项）
- 需要限制并发处理数量（加分项）

可选方案：
1. **asyncio + 后台协程池 + 数据库状态机**
2. **消息队列（Redis + RQ/Celery）**
3. **后台线程池（threading/concurrent.futures）**
4. **数据库轮询（定时扫描 pending 任务）**

## 决策

采用 **asyncio + 后台协程池 + 数据库状态机** 方案。

### 核心设计

**任务调度器**:
```python
# 全局信号量控制并发
task_semaphore = asyncio.Semaphore(3)

async def schedule_task(task_id: UUID):
    """将任务加入后台处理队列"""
    asyncio.create_task(process_task_with_semaphore(task_id))

async def process_task_with_semaphore(task_id: UUID):
    """使用信号量控制并发"""
    async with task_semaphore:
        await process_task(task_id)
```

**任务处理流程**:
```python
async def process_task(task_id: UUID):
    """完整的任务处理流程，包含自动重试"""
    for attempt in range(MAX_RETRIES):
        try:
            # 更新状态为 transcribing
            await update_task_status(task_id, "transcribing")
            transcript = await mock_transcribe()
            
            # 更新状态为 summarizing
            await update_task_status(task_id, "summarizing")
            summary = await llm_summarize(transcript)
            
            # 保存结果并标记完成
            await save_task_result(task_id, transcript, summary)
            await update_task_status(task_id, "done")
            break
            
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                # 指数退避重试
                await asyncio.sleep(2 ** attempt)
                await increment_retry_count(task_id)
            else:
                # 重试耗尽，标记失败
                await update_task_status(task_id, "failed", str(e))
```

**服务启动时的任务恢复**:
```python
async def recover_tasks_on_startup():
    """检测并恢复未完成的任务"""
    # 1. 重置僵尸任务（超过5分钟未更新的处理中任务）
    await db.execute("""
        UPDATE tasks 
        SET status = 'pending', updated_at = NOW()
        WHERE status IN ('transcribing', 'summarizing')
        AND updated_at < NOW() - INTERVAL '5 minutes'
    """)
    
    # 2. 将所有 pending 任务重新调度
    pending_tasks = await db.fetch_all(
        "SELECT id FROM tasks WHERE status = 'pending'"
    )
    for task in pending_tasks:
        await schedule_task(task.id)
```

## 考虑的替代方案

### 方案 2: 消息队列（Redis + Celery）

**优点**:
- 成熟的分布式任务队列
- 自带任务持久化和重试机制
- 支持复杂的任务编排

**缺点**:
- 增加 Redis 依赖，违背"一键启动"的简洁性
- 配置复杂（broker、backend、worker）
- 对于单实例服务过度设计

**拒绝理由**: 增加了系统复杂度，而本项目是单实例服务，不需要分布式能力。

### 方案 3: 后台线程池

**优点**:
- Python 标准库自带
- 实现简单

**缺点**:
- Python GIL 限制，CPU 密集型任务性能差
- 无法使用 asyncio 的异步 I/O 优势
- 与 FastAPI 的异步模型不匹配

**拒绝理由**: 本项目是 I/O 密集型（文件读写、HTTP 调用），asyncio 更适合。

### 方案 4: 数据库轮询

**优点**:
- 实现极简
- 服务重启自动恢复

**缺点**:
- 轮询间隔带来延迟（如每 5 秒轮询一次）
- 频繁查询数据库，效率低

**拒绝理由**: 响应延迟不可接受，且与事件驱动的异步模型不符。

## 决策理由

1. **轻量级**: 无需额外中间件（Redis、RabbitMQ），满足一键启动要求
2. **持久化**: 任务状态存储在数据库，服务重启后可恢复
3. **性能**: asyncio 的协程比线程更轻量，适合高并发 I/O
4. **可控性**: 通过 `asyncio.Semaphore` 精确控制并发数
5. **简洁**: 代码量少，易于理解和维护

## 后果

### 积极影响

- ✅ 满足"一键启动"要求（无额外依赖）
- ✅ 服务重启后自动恢复任务（启动时扫描数据库）
- ✅ 并发控制简单有效（`Semaphore(3)`）
- ✅ 自动重试逻辑清晰（循环 + 指数退避）
- ✅ 与 FastAPI 异步模型无缝集成

### 消极影响

- ❌ 单实例限制：无法水平扩展（多个实例会竞争任务）
- ❌ 任务调度不如专业队列精细（无优先级、延迟调度等）
- ❌ 重启时正在处理的任务会中断（需要等 5 分钟超时才重置）

### 风险缓解

**单实例限制**:
- 本项目不考察高并发性能，单实例足够
- 未来如需扩展，可迁移到 Celery（数据库表结构不需要大改）

**任务中断问题**:
- 通过僵尸任务检测（5 分钟超时）自动重置
- 任务幂等设计：重复执行不会产生副作用

**数据库并发冲突**:
- 使用 `SELECT FOR UPDATE` 锁定任务行，防止重复处理
- 乐观锁检测（`updated_at` 版本号）

## 实现细节

### 并发控制

```python
# config.py
MAX_CONCURRENT_TASKS = 3

# task_processor.py
task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
```

### 自动重试配置

```python
# config.py
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1  # 秒，指数退避基数

# 重试延迟：1s, 2s, 4s
```

### 僵尸任务检测阈值

```python
# config.py
ZOMBIE_TASK_TIMEOUT = 300  # 5分钟
```

## 相关决策

- ADR-001: 技术栈选择（选择 Python + asyncio）
- ADR-003: 数据库设计（任务状态存储）
