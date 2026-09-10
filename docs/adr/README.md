# Architecture Decision Records

本目录包含 AudioInsight 项目的所有架构决策记录。

## ADR 列表

- [ADR-001: 技术栈选择](./ADR-001-technology-stack.md) - Python + FastAPI + PostgreSQL + Docker Compose
- [ADR-002: 异步处理方案](./ADR-002-async-processing.md) - asyncio + 后台协程池 + 数据库状态机
- [ADR-003: 数据库设计](./ADR-003-database-design.md) - 两张独立表（recordings + tasks），一对多关系
- [ADR-004: 上传幂等实现](./ADR-004-upload-idempotency.md) - 文件哈希 + 可选覆盖参数
- [ADR-005: LLM 流式输出设计](./ADR-005-llm-streaming.md) - 实时生成 + SSE
- [ADR-006: 测试策略](./ADR-006-testing-strategy.md) - 最小有效测试集，重点覆盖核心功能
- [ADR-007: 部署方案](./ADR-007-deployment.md) - Railway 平台部署

## 阅读指南

如果你是新加入项目的开发者，建议按以下顺序阅读：

1. 先阅读根目录的 [CONTEXT.md](../../CONTEXT.md) 了解项目概览和领域知识
2. 阅读 ADR-001（技术栈）和 ADR-002（异步处理）了解核心架构
3. 阅读 ADR-003（数据库）了解数据模型
4. 根据具体任务，阅读相关的其他 ADR

## ADR 状态说明

- **Proposed**: 提议中，尚未实施
- **Accepted**: 已接受并正在实施或已实施
- **Deprecated**: 已废弃，不再使用
- **Superseded**: 已被新的 ADR 取代

## 创建新 ADR

当需要记录新的架构决策时：

1. 复制现有 ADR 作为模板
2. 使用下一个序号（ADR-008, ADR-009, ...）
3. 遵循标准格式：
   - 状态、日期、决策者
   - 上下文（问题背景）
   - 决策（选择的方案）
   - 考虑的替代方案
   - 决策理由
   - 后果（积极影响、消极影响、风险缓解）
   - 相关决策
4. 更新本索引文件
