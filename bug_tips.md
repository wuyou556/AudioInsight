# Bug Tips - 代码审查发现的问题分类

本文档记录了代码审查（/code-review）发现的问题，并标注哪些属于当前需要修复的 bug，哪些属于后续 issue 的范围。

## 当前需要修复的 Bug (P0-P2)

### P0 - 严重问题

#### 1. 未绑定变量引用 (app/services/task_processor.py:67)
**问题**: 数据库查询失败时，`task` 变量未定义，异常处理器会崩溃
**影响**: 导致异常处理器本身抛出 NameError
**修复**: 在 try 块外初始化 `task = None`

#### 2. 回调函数签名错误 (app/services/task_processor.py:87)
**问题**: `task.add_done_callback(_background_tasks.discard)` 签名不匹配
**影响**: 任务完成后无法从 set 中移除，导致内存泄漏
**修复**: 使用 lambda: `task.add_done_callback(lambda t: _background_tasks.discard(t))`

#### 3. 关系刷新后未检查 null (app/services/task_processor.py:38)
**问题**: Recording 被删除后访问 `task.recording.file_path` 抛出 AttributeError
**影响**: 错误信息不清晰，调试困难
**修复**: 添加 `if not task.recording: raise Exception("Recording not found")`

### P1 - 高优先级

#### 4. commit 失败未捕获 (app/services/task_processor.py:54)
**问题**: 转写成功后 db.commit() 失败未被内层 try-except 捕获
**影响**: 数据库状态不一致
**修复**: 内层 try-except 包含 commit 操作

### P2 - 中优先级

#### 5. 任务调度错误被吞没 (app/api/recordings.py:164)
**问题**: `schedule_task()` 失败时返回 500，但文件已保存
**影响**: 用户不知道上传是否成功
**修复**: 添加 try-except，记录错误但返回成功响应

#### 6. N+1 查询问题 (app/services/task_processor.py:28)
**问题**: 两次数据库往返获取 task 和 recording
**影响**: 性能下降
**修复**: 使用 `selectinload(Task.recording)` 预加载

#### 7. 嵌套异常处理吞没错误 (app/services/task_processor.py:66)
**问题**: 内层 try-except 使用 bare `pass`，错误静默失败
**影响**: 无法调试
**修复**: 至少记录日志或删除内层 try-except

#### 8. 未验证文件存在 (app/services/task_processor.py:39)
**问题**: 转写前未检查文件是否在磁盘上
**影响**: 文件被手动删除后转写失败，错误信息不清晰
**修复**: 添加 `if not os.path.exists(file_path): raise FileNotFoundError(...)`

#### 9. 数据库会话创建无超时 (app/services/task_processor.py:25)
**问题**: 连接池耗尽时 `AsyncSessionLocal()` 无限等待
**影响**: 系统死锁
**修复**: 配置连接池参数或添加超时处理

#### 10. 测试竞态条件 (tests/test_task_processor.py:159)
**问题**: 测试中的 sleep 时间假设可能不成立
**影响**: 测试不稳定
**修复**: 增加 sleep 时间或使用更可靠的同步机制

---

## 属于后续 Issue 的功能 (不是 Bug)

### Issue #5 - 真实 LLM 摘要生成
**代码审查发现**: 当前实现缺少摘要阶段（transcribing → done，跳过 summarizing）
**说明**: 这是 Issue #4 的正常范围限制，#4 只实现 Mock 转写，摘要是 #5 的任务
**不需要在 #4 中修复**

### Issue #10 - 自动重试与并发控制
**代码审查发现**: 缺少自动重试逻辑（应重试 3 次，指数退避）
**说明**: 这是后续功能，不是 #4 的 bug
**不需要在 #4 中修复**

### Issue #11 - 服务重启恢复
**代码审查发现**: 
- 无僵尸任务检测（处理中任务 >5 分钟未更新）
- 无启动时任务恢复逻辑
**说明**: 这些是 Issue #11 的内容，不是 #4 的 bug
**不需要在 #4 中修复**

### Issue #15 - Docker 化与本地一键启动
**代码审查发现**: 多进程部署时全局状态 `_background_tasks` 失效
**说明**: 
- 当前 docker-compose.yml 已存在但还需完善
- 多 worker 部署是生产环境优化，超出基础实现范围
- 可在 README 中注明"单实例限制"
**可以文档化，不需要立即修复代码**

### Issue #6 - 查询任务状态和录音详情
**代码审查发现**: 无
**说明**: 这是下一个 issue，还未实现

### Issue #12 - 上传幂等性（文件哈希去重）
**代码审查发现**: file_hash 字段当前使用 UUID 占位
**说明**: 这是已知的临时实现，Issue #12 会替换为真实 SHA256
**不需要在 #4 中修复**

---

## 修复优先级建议

### 立即修复（阻塞测试和功能）
1. P0-1: 未绑定变量
2. P0-2: 回调函数签名
3. P0-3: null 检查

### 近期修复（影响可靠性）
4. P1-4: commit 失败处理
5. P2-5: 任务调度错误处理
6. P2-7: 嵌套异常处理

### 渐进优化（性能和健壮性）
7. P2-6: N+1 查询
8. P2-8: 文件存在检查
9. P2-9: 数据库会话超时
10. P2-10: 测试竞态条件

### 后续 Issue 中实现
- 摘要阶段 → Issue #5
- 自动重试 → Issue #10  
- 僵尸任务检测 → Issue #11
- 多进程支持 → 文档说明限制，或作为独立优化项

---

## 修复策略

1. **先修 P0**：确保基本功能不崩溃
2. **提交一次**：将 P0 的 3 个问题作为一个 commit
3. **再修 P1-P2**：根据时间和优先级选择修复
4. **更新测试**：确保修复后测试通过
5. **文档化限制**：在 README 中说明单实例限制等已知问题

---

## 代码审查工具输出

完整的代码审查报告由 `/code-review` 技能生成，包含 15 个发现。
本文档是对这些发现的分类和行动计划。
