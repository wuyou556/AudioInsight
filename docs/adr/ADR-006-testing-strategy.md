# ADR-006: 测试策略

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

需要实现"测试"加分项，为核心功能编写单元测试或集成测试。关键约束：
- 时间限制（12-16 小时总工作量，测试不应占用过多时间）
- 测试覆盖率与开发速度的平衡
- 测试应验证关键行为，而非实现细节
- 需要展示测试能力，但不追求 100% 覆盖

可选方案：
1. **最小有效测试集**（核心功能 + 关键边界情况，投入 30-45 分钟）
2. **中等覆盖**（所有 API 端点 + 服务层逻辑，投入 1-2 小时）
3. **全面测试**（高覆盖率 + Mock 外部依赖，投入 2-3 小时）

## 决策

采用 **最小有效测试集** 策略，重点测试状态机流转、API 端点关键路径、幂等性。

### 测试范围

**1. API 集成测试** (`tests/test_api.py`):
```python
# 上传接口
- test_upload_recording_success() - 正常上传
- test_upload_invalid_file_extension() - 无效扩展名返回 400
- test_upload_file_too_large() - 超过 50MB 返回 400
- test_upload_duplicate_file() - 幂等性：相同文件返回相同 recording_id

# 查询接口
- test_get_task_status() - 查询任务状态
- test_get_task_not_found() - 任务不存在返回 404
- test_get_recording_detail() - 查询录音详情
- test_list_recordings_pagination() - 分页查询

# 重试接口
- test_retry_failed_task() - 重试失败任务
- test_retry_non_failed_task_returns_409() - 重试非失败任务返回 409

# 删除接口
- test_delete_recording() - 删除录音及文件
- test_delete_recording_not_found() - 删除不存在的录音返回 404
```

**2. 任务处理器测试** (`tests/test_task_processor.py`):
```python
# 状态机
- test_task_state_transitions() - pending → transcribing → summarizing → done
- test_task_failure_transitions() - 失败进入 failed 状态
- test_auto_retry_on_failure() - 自动重试逻辑（3次，指数退避）
- test_max_retries_exhausted() - 重试耗尽后保持 failed

# 服务重启恢复
- test_recover_pending_tasks_on_startup() - 启动时恢复 pending 任务
- test_reset_zombie_tasks() - 重置僵尸任务（超过 5 分钟未更新）
```

**3. 幂等性测试** (`tests/test_idempotency.py`):
```python
- test_upload_same_file_twice() - 相同文件哈希返回同一 recording
- test_force_reprocess_creates_new_recording() - force_reprocess=true 创建新录音
- test_different_files_create_different_recordings() - 不同文件创建不同录音
```

### 测试工具

**框架**: pytest + pytest-asyncio
```python
# 异步测试支持
import pytest

@pytest.mark.asyncio
async def test_upload_recording():
    # ...
```

**测试客户端**: httpx (FastAPI 测试)
```python
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

async def test_upload_recording(client):
    response = await client.post(
        "/v1/recordings",
        files={"file": ("test.mp3", b"fake audio", "audio/mpeg")}
    )
    assert response.status_code == 201
```

**数据库**: 测试专用数据库
```python
# conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/audioinsight_test"

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
```

### 测试原则

**测试外部行为，而非实现细节**:
```python
# ✅ 好的测试：验证 API 契约
async def test_upload_returns_task_id():
    response = await client.post("/v1/recordings", files={"file": file})
    data = response.json()
    assert "task_id" in data
    assert "status" in data
    assert data["status"] == "pending"

# ❌ 不好的测试：依赖内部实现
async def test_upload_calls_schedule_task():
    with patch('app.services.task_processor.schedule_task') as mock:
        await upload_recording(file)
        mock.assert_called_once()  # 测试实现细节
```

**使用真实依赖，最小化 Mock**:
- 使用真实数据库（测试专用）
- Mock 外部 LLM API（避免真实调用产生费用）
- Mock 转写服务（本就是 Mock 实现）

**测试关键路径和边界情况**:
```python
# 关键路径
- test_full_task_lifecycle() - 完整的任务生命周期

# 边界情况
- test_file_exactly_50mb() - 边界值测试
- test_concurrent_task_limit() - 并发限制测试
- test_retry_with_different_errors() - 不同错误类型的重试
```

## 考虑的替代方案

### 方案 2: 中等覆盖

**额外测试**:
- 所有服务层函数的单元测试
- Mock LLM 的不同响应场景
- 更多边界情况（如数据库连接失败）

**投入**: 1-2 小时

**拒绝理由**: 边际收益递减，时间更好地用于实现其他加分项或优化核心功能。

### 方案 3: 全面测试

**额外测试**:
- 80%+ 代码覆盖率
- 所有错误分支
- 性能测试
- 负载测试

**投入**: 2-3 小时

**拒绝理由**: 对于笔试项目过度投入，且高覆盖率不等于高质量（可能测试了很多实现细节）。

## 决策理由

1. **时间效率**: 30-45 分钟投入，覆盖最关键的功能
2. **展示能力**: 测试质量优于测试数量，验证关键行为
3. **实用性**: 测试真正能捕获 bug 的场景（状态机、幂等性、边界条件）
4. **可维护性**: 最小化 Mock，测试更稳定
5. **答辩友好**: 容易解释每个测试的意图

## 后果

### 积极影响

- ✅ 覆盖核心功能和关键边界情况
- ✅ 测试运行快速（< 30 秒）
- ✅ 低维护成本（少用 Mock）
- ✅ 答辩时容易解释测试意图
- ✅ 满足加分项"测试"要求

### 消极影响

- ❌ 代码覆盖率不高（可能 50-60%）
- ❌ 一些边缘场景未覆盖
- ❌ 没有性能测试

### 未测试的部分

以下场景**不在测试范围**（已知取舍）:
- LLM API 的所有失败模式（超时、限流、格式错误等）
- 文件系统错误（磁盘满、权限错误）
- 数据库连接池耗尽
- 极端并发场景（100+ 并发上传）

理由：这些是运维/生产环境问题，不是核心业务逻辑问题。

## 测试环境配置

**Docker Compose 测试配置**:
```yaml
# docker-compose.test.yml
services:
  db-test:
    image: postgres:15
    environment:
      POSTGRES_DB: audioinsight_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
```

**运行测试**:
```bash
# 启动测试数据库
docker-compose -f docker-compose.test.yml up -d

# 运行测试
pytest tests/ -v --asyncio-mode=auto

# 生成覆盖率报告（可选）
pytest tests/ --cov=app --cov-report=html
```

## CI/CD 集成（未来扩展）

虽然不在本项目范围内，但测试设计考虑了 CI 集成的可能性：

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: audioinsight_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

## 测试文档

**README.md 中的测试说明**:
```markdown
## 运行测试

### 前置条件
- Docker 和 Docker Compose 已安装
- PostgreSQL 测试数据库运行在 5433 端口

### 执行测试
\`\`\`bash
# 启动测试数据库
docker-compose -f docker-compose.test.yml up -d

# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_api.py -v

# 查看覆盖率
pytest tests/ --cov=app --cov-report=term-missing
\`\`\`

### 测试覆盖
- ✅ API 端点（上传、查询、重试、删除）
- ✅ 任务状态机流转
- ✅ 自动重试逻辑
- ✅ 上传幂等性
- ✅ 服务重启恢复
```

## 相关决策

- ADR-002: 异步处理方案（测试任务处理器）
- ADR-003: 数据库设计（测试数据层）
- ADR-004: 上传幂等实现（测试幂等性）
