# AudioInsight 录音转写服务 - 完整实现规格

## Problem Statement

需要实现一个后端笔试项目：录音转写与智能摘要服务。用户上传音频文件后，系统异步完成转写（Mock）和智能摘要（真实 LLM API），用户可查询任务状态和结果。项目要求在 4 个自然日内完成，保留完整 git commit 历史，提供一键启动方式，并尽可能实现加分项以展示工程能力。

## Solution

构建一个基于 Python + FastAPI + PostgreSQL 的异步处理服务，采用分层架构和数据库状态机设计。通过 asyncio + 后台协程池实现轻量级异步处理，支持并发控制、自动重试、服务重启恢复等生产级特性。使用 Docker Compose 实现一键启动，部署到 Railway 提供公网访问。

## User Stories

### 核心功能（P0）

1. As a user, I want to upload an audio file (wav/mp3/m4a/aac, ≤50MB), so that I can get it transcribed and summarized
2. As a user, I want to receive a task ID immediately after upload, so that I don't have to wait for processing to complete
3. As a user, I want to query task status by task ID, so that I can track processing progress
4. As a user, I want to see the current processing stage (pending/transcribing/summarizing/done/failed), so that I know what's happening
5. As a user, I want to retrieve the transcript and summary when processing is done, so that I can use the results
6. As a user, I want to list all my recordings with pagination, so that I can browse through them
7. As a user, I want recordings sorted by creation time (newest first), so that I can find recent uploads easily
8. As a user, I want to see the latest task status in the recording list, so that I can quickly identify failed tasks
9. As a user, I want to retry a failed task, so that I can recover from transient failures
10. As a user, I want to delete a recording, so that I can remove unwanted files
11. As a user, I want the file and all associated data deleted together, so that I don't have orphaned data
12. As a user, I want clear error messages with proper HTTP status codes (404/400/409), so that I can understand what went wrong
13. As a user, I want the service to log key operations, so that issues can be debugged

### 异步处理

14. As a system, I want to process tasks asynchronously in the background, so that upload requests return immediately
15. As a system, I want to transition tasks through states (pending → transcribing → summarizing → done), so that progress is tracked
16. As a system, I want to mark tasks as failed when errors occur, so that users know processing stopped
17. As a system, I want to mock transcription with 5-15 second delay and 20% failure rate, so that it simulates real ASR behavior
18. As a system, I want to call real LLM API (DeepSeek) for summarization, so that results are useful
19. As a system, I want to generate structured summaries (summary, key_points, todos), so that results are actionable
20. As a system, I want to handle LLM timeouts (60s), so that stuck requests don't hang forever
21. As a system, I want to handle JSON parsing failures from LLM, so that malformed responses don't crash the service

### 加分项 - 自动重试

22. As a system, I want to automatically retry failed tasks up to 3 times, so that transient failures are recovered
23. As a system, I want to use exponential backoff (1s, 2s, 4s) for retries, so that I don't overwhelm external services
24. As a system, I want to increment retry_count on each attempt, so that I can track how many times a task was retried
25. As a system, I want to mark a task as failed only after all retries are exhausted, so that users see failures only when truly unrecoverable

### 加分项 - 服务重启恢复

26. As a system, I want to detect pending tasks on startup, so that they can be resumed
27. As a system, I want to reset zombie tasks (processing for >5 minutes without update), so that stuck tasks are recovered
28. As a system, I want to reschedule recovered tasks automatically, so that no work is lost

### 加分项 - 并发控制

29. As a system, I want to limit concurrent task processing to 3, so that I don't overwhelm resources
30. As a system, I want additional tasks to queue when the limit is reached, so that they're processed when slots free up
31. As a system, I want to use asyncio.Semaphore for concurrency control, so that it's lightweight and doesn't require external dependencies

### 加分项 - 上传幂等

32. As a user, I want duplicate file uploads to return the existing recording, so that I don't create redundant tasks due to network retries
33. As a user, I want to see an "is_duplicate" flag in the response, so that I know the file was already processed
34. As a user, I want to force reprocessing if needed, so that I can get a fresh result when the model improves
35. As a system, I want to compute SHA256 file hash for deduplication, so that identical content is detected regardless of filename
36. As a system, I want to stream hash computation, so that large files (50MB) don't consume excessive memory

### 加分项 - LLM 流式输出

37. As a user, I want to stream summary generation in real-time via SSE, so that I can see progress for long summaries
38. As a user, I want to call the streaming endpoint when the task is in "summarizing" state, so that I see live generation
39. As a user, I want to receive the complete summary in JSON format if the task is already done, so that I can still get results after completion
40. As a system, I want to save streamed content to the database as it's generated, so that the normal API returns the same result

### 加分项 - 测试

41. As a developer, I want unit tests for the state machine, so that state transitions are verified
42. As a developer, I want integration tests for API endpoints, so that the HTTP contract is validated
43. As a developer, I want tests for idempotency, so that duplicate upload behavior is correct
44. As a developer, I want tests for retry logic, so that failure recovery works
45. As a developer, I want tests for boundary cases (file size limits, invalid extensions), so that edge cases are handled

### 加分项 - 部署

46. As a reviewer, I want the service deployed to a public URL, so that I can test it without local setup
47. As a reviewer, I want HTTPS enabled, so that the API is secure
48. As a developer, I want GitHub integration for auto-deployment, so that updates are deployed on push
49. As a developer, I want health check endpoint, so that Railway can monitor service status

### 开发体验

50. As a developer, I want to start the entire stack with `docker-compose up`, so that local development is effortless
51. As a developer, I want database migrations managed by Alembic, so that schema changes are versioned
52. As a developer, I want environment variables in .env file, so that configuration is centralized
53. As a developer, I want automatic API documentation at /docs, so that I can explore endpoints interactively
54. As a developer, I want .http files for API testing, so that I can quickly test endpoints in my IDE

## Implementation Decisions

### Architecture

**Layered architecture** with clear separation of concerns:
- **API layer** (`app/api/`): FastAPI route handlers, request validation (Pydantic), response formatting
- **Service layer** (`app/services/`): Business logic for transcription, summarization, task processing
- **Data layer** (`app/models.py`, `app/database.py`): SQLAlchemy models, database connections
- **Configuration** (`app/config.py`): Centralized settings using pydantic-settings

**Async processing approach**:
- Use `asyncio.create_task()` to spawn background tasks on upload
- Use `asyncio.Semaphore(3)` to limit concurrent processing
- Use database (PostgreSQL) as the source of truth for task state
- On startup, query database for unfinished tasks and reschedule them

**State management**:
- Task states stored in database `tasks.status` column
- Valid states: pending, transcribing, summarizing, done, failed
- Use database `updated_at` timestamp to detect zombie tasks (>5 min without update)
- Each state transition updates `updated_at` via SQLAlchemy `onupdate`

### Database Schema

**Two-table design** (recordings 1:N tasks):
- `recordings`: File metadata (id, filename, file_path, file_size, mime_type, file_hash, timestamps)
- `tasks`: Processing work (id, recording_id, status, transcript, summary_json, error_message, retry_count, timestamps)

**Indexes**:
- `idx_recordings_file_hash`: Support O(1) idempotency check
- `idx_recordings_created_at DESC`: Support paginated listing sorted by newest first
- `idx_tasks_recording_id`: Speed up JOIN queries for recording details
- `idx_tasks_status`: Support filtering pending/failed tasks
- `idx_tasks_updated_at`: Support zombie task detection

**Constraints**:
- `file_hash UNIQUE NOT NULL`: Enforce idempotency at database level
- `FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE`: Auto-cleanup on recording deletion

### API Design

**Upload endpoint**:
- `POST /v1/recordings` with `multipart/form-data`
- Accept optional `force_reprocess` form field (boolean)
- Validate file extension (wav/mp3/m4a/aac) and size (≤50MB)
- Compute SHA256 hash, check for existing recording
- If duplicate and not force_reprocess, return existing recording + latest task with `is_duplicate: true`
- Otherwise save file to `uploads/{uuid}.{ext}`, create recording + task, schedule async processing
- Return 201 with `{recording_id, task_id, status: "pending", is_duplicate}`

**Task status endpoint**:
- `GET /v1/tasks/{task_id}`
- Return task details including current status, timestamps
- Return 404 if task not found

**Recording detail endpoint**:
- `GET /v1/recordings/{id}`
- Return recording metadata + latest task (with transcript/summary if done)
- Return 404 if recording not found

**Recording list endpoint**:
- `GET /v1/recordings?page=1&page_size=20`
- Return paginated list sorted by `created_at DESC`
- Include latest task status for each recording
- Return `{items, total, page, page_size}`

**Retry endpoint**:
- `POST /v1/tasks/{task_id}/retry`
- Check task status, return 409 if not failed
- Reset status to pending, increment retry_count, reschedule
- Return 200 with updated task

**Delete endpoint**:
- `DELETE /v1/recordings/{id}`
- Delete file from disk (`os.remove`)
- Delete database record (CASCADE deletes tasks)
- Return 204 No Content

**Stream endpoint**:
- `GET /v1/recordings/{id}/summary/stream`
- If status is "done", return complete summary as JSON
- If status is "summarizing", return SSE stream of LLM generation
- Otherwise return 400 with error code `INVALID_TASK_STATUS`

**Health check**:
- `GET /health`
- Check database connectivity
- Return `{status: "healthy", database: "connected", timestamp}`
- Return 503 if unhealthy

**Error response format**:
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Recording not found",
    "details": {}
  }
}
```

### Task Processing

**Processing function**:
```python
async def process_task(task_id: UUID):
    for attempt in range(MAX_RETRIES):
        try:
            await update_status(task_id, "transcribing")
            transcript = await mock_transcribe()  # Random 5-15s, 20% fail
            
            await update_status(task_id, "summarizing")
            summary = await llm_summarize(transcript)  # DeepSeek API, 60s timeout
            
            await save_result(task_id, transcript, summary)
            await update_status(task_id, "done")
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                await increment_retry_count(task_id)
            else:
                await update_status(task_id, "failed", str(e))
```

**Transcription mock**:
- Use `asyncio.sleep(random.uniform(5, 15))`
- Raise exception with 20% probability
- On success, return random text from predefined list (5-10 meeting/call transcripts)

**Summarization**:
- Use OpenAI SDK (DeepSeek compatible)
- Set `response_format={"type": "json_object"}` for structured output
- Timeout 60 seconds
- Retry JSON parsing failure once
- Prompt requests: `{summary: string, key_points: string[], todos: string[]}`

**Startup recovery**:
```python
async def recover_tasks_on_startup():
    # Reset zombie tasks
    await db.execute("""
        UPDATE tasks SET status = 'pending', updated_at = NOW()
        WHERE status IN ('transcribing', 'summarizing')
        AND updated_at < NOW() - INTERVAL '5 minutes'
    """)
    
    # Reschedule all pending
    pending = await db.fetch_all("SELECT id FROM tasks WHERE status = 'pending'")
    for task in pending:
        await schedule_task(task.id)
```

### Configuration Management

Use `pydantic-settings` with `.env` file:
```python
class Settings(BaseSettings):
    database_url: str
    deepseek_api_key: str
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    max_concurrent_tasks: int = 3
    upload_dir: str = "./uploads"
    max_retries: int = 3
    zombie_task_timeout: int = 300  # 5 minutes
    
    class Config:
        env_file = ".env"
```

### Deployment Configuration

**Dockerfile** (multi-stage build):
- Stage 1: Install dependencies
- Stage 2: Copy app code + dependencies from stage 1
- Run migrations on startup: `alembic upgrade head && uvicorn ...`
- Health check every 30s

**docker-compose.yml**:
- Service `db`: postgres:15
- Service `app`: build from Dockerfile, depends on db
- Volume mount for uploads

**Railway**:
- Connect GitHub repo
- Add PostgreSQL database (automatic DATABASE_URL injection)
- Set environment variables (DEEPSEEK_API_KEY, etc.)
- Auto-deploy on push to main

### File Storage

- Save files to `uploads/{uuid}.{original_extension}`
- Create `uploads/` directory if not exists
- Stream file chunks (8KB) when computing hash to avoid memory issues
- Delete file synchronously when deleting recording

### Logging

Use Python `logging` module with INFO level:
- Log task state transitions: `Task {id} transitioned to {status}`
- Log errors with full traceback
- Log startup recovery: `Recovered {count} pending tasks`
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

### Dependencies

Core packages in `requirements.txt`:
- fastapi==0.115.0
- uvicorn[standard]==0.30.6
- sqlalchemy==2.0.35
- alembic==1.13.3
- asyncpg==0.29.0 (PostgreSQL async driver)
- pydantic==2.9.2
- pydantic-settings==2.5.2
- python-dotenv==1.0.1
- python-multipart==0.0.9 (file upload)
- openai==1.51.0 (DeepSeek SDK)
- aiofiles==24.1.0 (async file I/O)
- pytest==8.3.3
- pytest-asyncio==0.24.0
- httpx==0.27.2 (test client)

## Testing Decisions

### What Makes a Good Test

- **Test external behavior**, not implementation details
- **Use real database** (test-specific database) to validate data layer
- **Mock only external services** (LLM API) to avoid costs and flakiness
- **Test key paths** (happy path + critical error cases) rather than exhaustive coverage
- **Test should fail when user-visible behavior breaks**, not when internal refactoring happens

### Test Modules

**tests/test_api.py** - API integration tests:
- Upload: success, invalid extension, file too large, duplicate file
- Query: task status, recording detail, recording list pagination
- Retry: success on failed task, 409 on non-failed task
- Delete: success, 404 on non-existent recording

**tests/test_task_processor.py** - Task processing tests:
- State transitions: pending → transcribing → summarizing → done
- Failure handling: transcription failure, summarization failure → failed state
- Auto-retry: 3 retries with exponential backoff, then failed
- Startup recovery: reschedule pending tasks, reset zombie tasks

**tests/test_idempotency.py** - Idempotency tests:
- Same file uploaded twice returns same recording_id
- force_reprocess=true creates new recording
- Different files create different recordings

### Testing Prior Art

Similar projects in the Python + FastAPI ecosystem use:
- `pytest` with `pytest-asyncio` for async test support
- `httpx.AsyncClient` for API integration tests
- Test database with fixtures for isolation
- `@pytest.mark.asyncio` decorator for async test functions

Example pattern:
```python
@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_upload_recording(client):
    response = await client.post("/v1/recordings", files={"file": ...})
    assert response.status_code == 201
```

## Out of Scope

The following are explicitly **not** in scope for this project:

- User registration, login, authentication, authorization
- Frontend UI (web page, mobile app)
- Object storage integration (S3, Aliyun OSS) - only local disk storage
- Multiple file upload in one request
- Batch processing API
- Real ASR integration (only mock)
- LLM prompt engineering for better summaries
- Audio format validation beyond extension check (e.g., checking file headers)
- Virus scanning
- Rate limiting per client
- WebSocket for real-time status updates
- Email/SMS notifications on completion
- Admin dashboard
- User analytics
- High concurrency optimization (connection pooling tuning, etc.)
- Horizontal scaling (multiple worker instances)
- Message queue integration (RabbitMQ, Kafka)
- Caching layer (Redis)
- CDN integration
- Performance testing, load testing
- Security hardening beyond basics (WAF, DDoS protection)

## Further Notes

### Development Workflow

**Initial setup**:
1. Create project structure with directories (app/api, app/services, tests, migrations, uploads)
2. Setup Alembic for database migrations
3. Create SQLAlchemy models and generate initial migration
4. Implement configuration management (config.py, .env.example)
5. Setup FastAPI application skeleton with health check endpoint

**Core implementation order**:
1. Upload endpoint + file validation + storage
2. Database models and migrations
3. Mock transcription service
4. LLM summarization service (DeepSeek integration)
5. Task processor with state machine
6. Startup recovery logic
7. Query endpoints (task status, recording detail/list)
8. Retry endpoint
9. Delete endpoint
10. Error handling and logging

**Bonus features order**:
1. Auto-retry (already built into task processor)
2. Concurrency control (Semaphore)
3. Idempotency (file hash + duplicate detection)
4. Streaming (SSE endpoint)
5. Tests (parallel with implementation)
6. Deployment (final step)

### Git Commit Strategy

Commits should tell a story of incremental development:
- Initial commit: project structure + README
- Setup database and models
- Implement upload endpoint
- Implement mock transcription
- Integrate LLM API
- Implement task processing
- Add query endpoints
- Add retry and delete
- Implement auto-retry
- Add concurrency control
- Add upload idempotency
- Add streaming endpoint
- Add tests
- Add Docker configuration
- Deploy to Railway
- Final polish and documentation

**Anti-pattern**: Single commit with all code (explicitly forbidden by requirements)

### README Contents

Must include:
- Project overview
- Architecture diagram (simple flowchart: upload → async processing → query)
- Table structure (DDL or ER diagram)
- Tech stack justification
- One-command startup: `docker-compose up`
- API testing file (audio-insight.http)
- Known issues and incomplete items
- Deployment URL (if deployed)

### Known Limitations

Document honestly in README:
- Single instance only (no horizontal scaling)
- Zombie task detection has 5-minute lag
- File storage on local disk (not persistent across container rebuilds in some platforms)
- No authentication (anyone can upload/delete)
- Free Railway quota limits (500 hours/month)

### Time Budget Estimation

- Core functionality (P0): 6-8 hours
- Auto-retry + concurrency + recovery: 1-2 hours
- Idempotency: 1 hour
- Streaming: 1-1.5 hours
- Tests: 1 hour
- Docker + deployment: 1 hour
- Documentation: 1 hour
- **Total**: 12-15.5 hours (within 12-16 hour target)

### Success Criteria

Project is complete when:
- All core endpoints work end-to-end
- Docker Compose starts the service successfully
- API test file (.http) has examples for all endpoints
- Tests pass (`pytest tests/ -v`)
- README explains architecture and how to run
- Service is deployed and accessible via public URL
- Commit history shows incremental development (10+ meaningful commits)

---

**Specification Version**: 1.0  
**Date**: 2026-09-10  
**Status**: Ready for implementation
