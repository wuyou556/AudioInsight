# ADR-004: 上传幂等实现

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

需要实现"上传幂等"加分项，防止用户重复上传相同文件时创建重复任务。典型场景：
- 网络不稳定，客户端重试上传
- 用户误操作，多次上传同一文件
- 评审者测试时反复上传测试文件

可选方案：
1. **文件哈希（服务端自动去重）**
2. **客户端幂等键**
3. **文件哈希 + 可选幂等键（混合）**

关键考虑因素：
- 用户意图识别：网络重试 vs 真正想重新处理
- 实现复杂度
- 客户端集成成本
- 大文件内存占用

## 决策

采用 **文件哈希 + 可选覆盖参数** 方案。

### 实现方式

**1. 数据库字段**:
```sql
ALTER TABLE recordings ADD COLUMN file_hash VARCHAR(64) UNIQUE NOT NULL;
CREATE INDEX idx_recordings_file_hash ON recordings(file_hash);
```

**2. API 接口**:
```python
@router.post("/v1/recordings")
async def upload_recording(
    file: UploadFile = File(...),
    force_reprocess: bool = Form(False)  # 强制重新处理
) -> UploadResponse:
    """
    上传录音文件
    
    Args:
        file: 音频文件（wav/mp3/m4a/aac，≤50MB）
        force_reprocess: 强制重新处理，即使文件已存在
    
    Returns:
        {
            "recording_id": "uuid",
            "task_id": "uuid",
            "status": "pending",
            "is_duplicate": false  # 是否是重复文件
        }
    """
    # 验证文件
    validate_file(file)
    
    # 流式计算哈希（避免大文件内存占用）
    file_content = await file.read()
    file_hash = hashlib.sha256(file_content).hexdigest()
    await file.seek(0)
    
    # 检查幂等性（除非 force_reprocess=True）
    if not force_reprocess:
        existing = await db.query(Recording).filter_by(file_hash=file_hash).first()
        if existing:
            # 返回最新的任务
            latest_task = await db.query(Task).filter_by(
                recording_id=existing.id
            ).order_by(Task.created_at.desc()).first()
            
            return UploadResponse(
                recording_id=existing.id,
                task_id=latest_task.id,
                status=latest_task.status,
                is_duplicate=True
            )
    
    # 新文件或强制重新处理，保存并创建任务
    recording = Recording(
        filename=file.filename,
        file_path=f"uploads/{uuid4()}.{get_extension(file.filename)}",
        file_size=len(file_content),
        file_hash=file_hash,
        mime_type=file.content_type
    )
    
    # 保存文件到磁盘
    async with aiofiles.open(recording.file_path, 'wb') as f:
        await f.write(file_content)
    
    db.add(recording)
    await db.flush()
    
    # 创建任务
    task = Task(recording_id=recording.id, status="pending")
    db.add(task)
    await db.commit()
    
    # 调度任务
    await schedule_task(task.id)
    
    return UploadResponse(
        recording_id=recording.id,
        task_id=task.id,
        status="pending",
        is_duplicate=False
    )
```

**3. 流式哈希计算优化**:
```python
async def compute_hash_streaming(file: UploadFile) -> str:
    """流式计算文件哈希，避免大文件全部读入内存"""
    hasher = hashlib.sha256()
    while chunk := await file.read(8192):  # 8KB chunks
        hasher.update(chunk)
    await file.seek(0)  # 重置文件指针供后续使用
    return hasher.hexdigest()
```

## 考虑的替代方案

### 方案 2: 客户端幂等键

**实现方式**:
```python
@router.post("/v1/recordings")
async def upload_recording(
    file: UploadFile,
    idempotency_key: Optional[str] = Form(None)
):
    if idempotency_key:
        existing = await db.query(Recording).filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            return get_existing_response(existing)
    # ...
```

**优点**:
- 客户端完全控制重试行为
- 不需要读取文件内容，性能好
- 符合 Stripe、AWS 等标准 API 设计模式

**缺点**:
- 客户端需要配合实现（增加集成复杂度）
- 不同客户端上传相同文件仍会重复处理
- 需要设置幂等键过期时间（管理复杂）

**拒绝理由**: 对于笔试项目，自动去重更符合"幂等性"的直观理解，且评审者无需修改客户端代码即可体验。

### 方案 3: 混合方案（哈希 + 幂等键）

**实现方式**:
```python
# 优先检查客户端幂等键，再检查文件哈希
if idempotency_key:
    existing = check_by_key(idempotency_key)
if not existing and not force_new:
    existing = check_by_hash(file_hash)
```

**优点**:
- 最大灵活性

**缺点**:
- 实现复杂度最高
- 两层去重逻辑可能让用户困惑

**拒绝理由**: 过度设计，增加复杂度但收益有限。

## 决策理由

1. **自动生效**: 评审者无需修改客户端代码，上传相同文件自动去重
2. **直观**: 相同内容不应重复处理，符合幂等性的语义
3. **节省资源**: 避免重复存储和处理
4. **灵活性**: `force_reprocess` 参数支持"确实想重新处理"的场景
5. **演示效果**: 评审者可以立即看到去重效果（`is_duplicate: true`）

## 后果

### 积极影响

- ✅ 防止网络重试导致的重复任务
- ✅ 节省存储空间和计算资源
- ✅ `is_duplicate` 标志让客户端明确知道这是重复文件
- ✅ 流式计算哈希避免内存占用问题
- ✅ 满足加分项"上传幂等"的要求

### 消极影响

- ❌ 上传时需要计算哈希，增加约 50-100ms 延迟（可接受）
- ❌ 用户可能确实想重新处理同一文件（通过 `force_reprocess` 缓解）
- ❌ 不支持"相同文件但不同用户"的场景（本项目无多用户系统）

### 边界情况处理

**哈希冲突**:
- SHA256 冲突概率极低（2^-256），实际可忽略
- 如发生冲突，数据库 UNIQUE 约束会拒绝插入，返回 500 错误
- 未来可优化：检测冲突后使用文件大小 + 部分内容二次验证

**文件内容相同但文件名不同**:
- 行为：返回已有录音的 task，`is_duplicate: true`
- 理由：内容相同则无需重复处理

**用户确实想重新处理**:
- 场景：LLM 模型升级后，想用新模型重新生成摘要
- 解决：传 `force_reprocess=true`，创建新录音和新任务

## 测试覆盖

```python
# tests/test_idempotency.py

async def test_upload_same_file_twice_returns_same_recording():
    """上传相同文件两次，应返回相同的 recording_id"""
    file_content = b"test audio content"
    
    response1 = await client.post("/v1/recordings", files={"file": ("test.mp3", file_content)})
    response2 = await client.post("/v1/recordings", files={"file": ("test_copy.mp3", file_content)})
    
    assert response1.json()["recording_id"] == response2.json()["recording_id"]
    assert response2.json()["is_duplicate"] is True

async def test_force_reprocess_creates_new_recording():
    """force_reprocess=True 应创建新录音"""
    file_content = b"test audio content"
    
    response1 = await client.post("/v1/recordings", files={"file": ("test.mp3", file_content)})
    response2 = await client.post(
        "/v1/recordings",
        files={"file": ("test.mp3", file_content)},
        data={"force_reprocess": "true"}
    )
    
    assert response1.json()["recording_id"] != response2.json()["recording_id"]
    assert response2.json()["is_duplicate"] is False

async def test_different_files_create_different_recordings():
    """不同文件应创建不同录音"""
    response1 = await client.post("/v1/recordings", files={"file": ("test1.mp3", b"content1")})
    response2 = await client.post("/v1/recordings", files={"file": ("test2.mp3", b"content2")})
    
    assert response1.json()["recording_id"] != response2.json()["recording_id"]
```

## API 文档示例

**.http 文件**:
```http
### 上传新文件
POST http://localhost:8000/v1/recordings
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="meeting.mp3"
Content-Type: audio/mpeg

< ./test_files/meeting.mp3
------WebKitFormBoundary--

### 重复上传（应返回 is_duplicate=true）
POST http://localhost:8000/v1/recordings
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="meeting_copy.mp3"
Content-Type: audio/mpeg

< ./test_files/meeting.mp3
------WebKitFormBoundary--

### 强制重新处理
POST http://localhost:8000/v1/recordings
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="meeting.mp3"
Content-Type: audio/mpeg

< ./test_files/meeting.mp3
------WebKitFormBoundary
Content-Disposition: form-data; name="force_reprocess"

true
------WebKitFormBoundary--
```

## 相关决策

- ADR-003: 数据库设计（file_hash 字段定义）
- ADR-005: LLM 流式输出设计（不影响幂等性）
