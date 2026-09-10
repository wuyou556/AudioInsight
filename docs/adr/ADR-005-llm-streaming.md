# ADR-005: LLM 流式输出设计

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

需要实现"LLM 流式输出"加分项，提供 Server-Sent Events (SSE) 方式流式返回摘要生成过程。关键考虑：
- 流式输出的时机（实时生成 vs 回放已完成）
- 与普通摘要接口的关系
- 数据存储策略（是否需要存储两份）
- 用户体验（何时可以调用流式接口）

可选方案：
1. **实时生成**：只在 summarizing 状态时可调用，实时流式调用 LLM
2. **回放模式**：任务完成后，将已保存的摘要逐字流式返回（模拟）
3. **混合模式**：summarizing 时实时流式，done 后返回完整结果

## 决策

采用 **实时生成** 方案，同时在流式生成过程中完整保存到数据库。

### API 设计

**端点**:
```
GET /v1/recordings/{id}/summary/stream
```

**行为**:
```python
@router.get("/v1/recordings/{id}/summary/stream")
async def stream_summary(id: UUID):
    """
    流式返回摘要生成过程（SSE）
    
    状态要求：
    - done: 直接返回完整摘要（JSON）
    - summarizing: 实时流式返回生成过程
    - 其他状态: 返回 400 错误
    """
    # 获取最新任务
    task = await get_latest_task(id)
    
    if task.status == "done":
        # 已完成，直接返回完整结果
        return JSONResponse(task.summary_json)
    
    if task.status != "summarizing":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_TASK_STATUS",
                    "message": f"Cannot stream summary for task in '{task.status}' status",
                    "details": {"current_status": task.status, "required_status": "summarizing"}
                }
            }
        )
    
    # 实时流式生成
    async def generate():
        full_content = ""
        try:
            async for chunk in llm_stream_summarize(task.transcript):
                full_content += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            # 流式完成后，解析并保存完整摘要
            summary_json = parse_llm_response(full_content)
            await save_task_result(task.id, task.transcript, summary_json)
            await update_task_status(task.id, "done")
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            await update_task_status(task.id, "failed", str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
        }
    )
```

### LLM 调用（DeepSeek 流式）

```python
from openai import AsyncOpenAI

async def llm_stream_summarize(transcript: str):
    """流式调用 DeepSeek API 生成摘要"""
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_api_base
    )
    
    prompt = f"""请对以下转写文本生成结构化摘要，使用 JSON 格式：

转写文本：
{transcript}

JSON 格式要求：
{{
  "summary": "一句话摘要（不超过50字）",
  "key_points": ["要点1", "要点2", "要点3"],
  "todos": ["待办事项1", "待办事项2"]
}}
"""
    
    stream = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        response_format={"type": "json_object"},  # 强制 JSON 输出
        temperature=0.7,
        max_tokens=1000
    )
    
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

### 与普通摘要接口的协调

**普通接口** (`GET /v1/recordings/{id}`):
- 只返回已完成的摘要
- 如果任务还在处理中，`summary` 字段为 `null`

**流式接口** (`GET /v1/recordings/{id}/summary/stream`):
- 在 `summarizing` 状态时提供实时流式输出
- 在 `done` 状态时返回完整摘要（非流式）

**数据一致性**:
- 流式生成的内容会累积，完成后解析为结构化 JSON 并保存到数据库
- 普通接口读取的是数据库中的完整摘要
- 同一任务的两种接口返回的摘要内容一致

## 考虑的替代方案

### 方案 2: 回放模式

**实现方式**:
```python
async def generate():
    summary = task.summary_json
    text = json.dumps(summary, ensure_ascii=False)
    for char in text:
        yield f"data: {json.dumps({'chunk': char})}\n\n"
        await asyncio.sleep(0.05)  # 模拟流式速度
```

**优点**:
- 任何时候都可以调用（只要任务完成）
- 实现简单，无需处理 LLM 流式 API

**缺点**:
- 不是真正的流式生成，只是模拟
- 无法展示 LLM 实时生成的效果
- 不符合"流式输出"的本意

**拒绝理由**: 加分项明确要求"SSE 方式流式返回摘要生成过程"，回放模式不能体现"生成过程"。

### 方案 3: 混合模式

**实现方式**:
- `summarizing` 状态：实时流式
- `done` 状态：回放模式（或拒绝调用）

**优点**:
- 灵活性最高

**缺点**:
- 行为不一致，容易混淆
- 增加实现复杂度

**拒绝理由**: 用户如果想查看已完成的摘要，应该调用普通接口 `GET /v1/recordings/{id}`，无需流式。

## 决策理由

1. **真实性**: 展示 LLM 实时生成过程，符合加分项要求
2. **用户体验**: 长文本摘要时（30-60 秒），流式输出让用户感知进度
3. **DeepSeek 支持**: DeepSeek API 原生支持流式输出，无需额外工作
4. **状态清晰**: 只在 `summarizing` 状态可用，避免混淆
5. **数据一致性**: 流式内容完整保存，与普通接口一致

## 后果

### 积极影响

- ✅ 真正的流式体验，展示 LLM 生成过程
- ✅ 长时间摘要时用户可实时看到进度
- ✅ 满足加分项"LLM 流式输出"要求
- ✅ DeepSeek API 原生支持，实现简单
- ✅ 流式和非流式接口数据一致

### 消极影响

- ❌ 流式接口只能在 `summarizing` 状态调用（时间窗口短）
- ❌ 客户端需要处理 SSE 协议（相对复杂）
- ❌ 流式生成失败时客户端可能已收到部分内容

### 风险缓解

**时间窗口问题**:
- 实际上，LLM 摘要通常需要 10-30 秒，时间窗口足够
- 如果客户端错过，可以调用普通接口获取完整结果

**SSE 客户端实现**:
- 提供示例代码（JavaScript + Python）
- 在 `.http` 文件中提供测试用例

**流式失败处理**:
```python
# 客户端示例
async for event in sse_client.aiter_sse():
    if event.data == "[DONE]":
        break
    if "error" in json.loads(event.data):
        # 处理错误
        break
    # 处理正常 chunk
```

## 客户端使用示例

**JavaScript (浏览器)**:
```javascript
const eventSource = new EventSource(
  `http://localhost:8000/v1/recordings/${recordingId}/summary/stream`
);

eventSource.onmessage = (event) => {
  if (event.data === '[DONE]') {
    eventSource.close();
    return;
  }
  
  const data = JSON.parse(event.data);
  if (data.chunk) {
    document.getElementById('summary').innerText += data.chunk;
  } else if (data.error) {
    console.error('Error:', data.error);
    eventSource.close();
  }
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

**Python (httpx)**:
```python
import httpx
import json

async with httpx.AsyncClient() as client:
    async with client.stream(
        'GET',
        f'http://localhost:8000/v1/recordings/{recording_id}/summary/stream'
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith('data: '):
                data = line[6:]  # 去掉 'data: ' 前缀
                if data == '[DONE]':
                    break
                chunk_data = json.loads(data)
                print(chunk_data.get('chunk', ''), end='', flush=True)
```

**.http 文件测试**:
```http
### 流式摘要生成（需要任务在 summarizing 状态）
GET http://localhost:8000/v1/recordings/{{recordingId}}/summary/stream
Accept: text/event-stream
```

## 测试覆盖

```python
# tests/test_streaming.py

async def test_stream_summary_when_summarizing():
    """summarizing 状态时应返回 SSE 流"""
    # 创建一个处于 summarizing 状态的任务
    task = await create_task_in_status("summarizing")
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            'GET',
            f'/v1/recordings/{task.recording_id}/summary/stream'
        ) as response:
            assert response.status_code == 200
            assert response.headers['content-type'] == 'text/event-stream'
            
            chunks = []
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    chunks.append(json.loads(data)['chunk'])
            
            assert len(chunks) > 0

async def test_stream_summary_when_done_returns_json():
    """done 状态时应返回完整 JSON"""
    task = await create_completed_task()
    
    response = await client.get(f'/v1/recordings/{task.recording_id}/summary/stream')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/json'
    
    data = response.json()
    assert 'summary' in data
    assert 'key_points' in data
    assert 'todos' in data

async def test_stream_summary_when_pending_returns_400():
    """pending 状态时应返回 400 错误"""
    task = await create_task_in_status("pending")
    
    response = await client.get(f'/v1/recordings/{task.recording_id}/summary/stream')
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_TASK_STATUS'
```

## 性能考虑

**并发流式请求**:
- 流式请求会长时间占用连接（10-30 秒）
- 并发控制（`Semaphore(3)`）确保不会同时生成过多摘要
- FastAPI 的异步能力允许多个流式连接并存

**超时设置**:
```python
# config.py
LLM_STREAM_TIMEOUT = 90  # 秒，允许更长的超时
```

**缓冲控制**:
```python
# 确保 chunks 及时发送到客户端
headers = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no"  # Nginx 代理时禁用缓冲
}
```

## 相关决策

- ADR-001: 技术栈选择（DeepSeek API + FastAPI）
- ADR-002: 异步处理方案（任务状态管理）
- ADR-003: 数据库设计（summary_json 字段存储）
