# ADR-001: 技术栈选择

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

AudioInsight 是一个后端笔试项目，需要在 4 个自然日内完成（12-16 小时实际工作量）。项目要求实现录音转写和智能摘要功能，支持异步处理、任务状态查询、失败重试等核心能力。

需要选择合适的技术栈，平衡以下因素：
- 开发效率（时间限制）
- 异步处理能力（核心需求）
- LLM 集成的便利性
- 一键启动的可行性
- 代码质量和可维护性

可选方案：
1. **Python + FastAPI**
2. **Go + Gin/Echo**
3. **Node.js + Express/NestJS**

## 决策

选择 **Python 3.11+ + FastAPI + PostgreSQL + Docker Compose** 作为核心技术栈。

### 具体组件

**Web 框架**: FastAPI 0.115+
- 原生异步支持（基于 asyncio）
- 自动 API 文档生成（OpenAPI/Swagger）
- Pydantic 集成提供强类型验证
- 高性能（基于 Starlette 和 uvicorn）

**数据库**: PostgreSQL 15
- 成熟的关系型数据库
- JSONB 类型高效存储结构化摘要
- 支持完整的事务和外键约束
- 通过 Docker 容器运行，满足一键启动要求

**ORM**: SQLAlchemy 2.0
- 支持异步操作（asyncpg driver）
- 强大的查询能力
- 与 Alembic 无缝集成进行数据库迁移

**LLM SDK**: OpenAI Python SDK
- DeepSeek API 兼容 OpenAI 格式
- 支持流式输出（SSE）
- 成熟稳定，文档完善

**部署**: Docker Compose
- 单个 `docker-compose.yml` 包含应用和数据库
- 真正的"一键启动"（`docker-compose up`）
- 环境一致性保证

## 考虑的替代方案

### 方案 2: Go + Gin + PostgreSQL

**优点**:
- 并发原语强大（goroutine）
- 性能优异
- 单二进制部署简单

**缺点**:
- LLM SDK 生态不如 Python 丰富
- 开发速度较慢（需要更多样板代码）
- 数据库操作相对繁琐（缺少成熟的 async ORM）

**拒绝理由**: 在 12-16 小时的时间限制下，开发效率是关键因素。Go 的性能优势在本项目中无法体现（不考察高并发性能）。

### 方案 3: Node.js + Express + PostgreSQL

**优点**:
- 异步 I/O 天然支持
- JavaScript 生态成熟
- npm 包丰富

**缺点**:
- 类型安全较弱（即使使用 TypeScript）
- LLM SDK 不如 Python 成熟
- 数据库 ORM（Sequelize/TypeORM）的异步支持不如 SQLAlchemy

**拒绝理由**: Python 在 LLM 领域有更好的工具链和文档，FastAPI 的开发体验优于 Express。

## 决策理由

1. **开发效率**: FastAPI 的自动文档生成、类型验证、异步支持大幅减少样板代码
2. **LLM 集成**: Python 是 LLM 开发的首选语言，DeepSeek/OpenAI SDK 文档完善
3. **异步处理**: asyncio 成熟稳定，SQLAlchemy 2.0 的异步支持完善
4. **一键启动**: Docker Compose 完美满足要求，PostgreSQL 容器化运行
5. **学习曲线**: Python + FastAPI 容易上手，适合短期项目

## 后果

### 积极影响

- ✅ 快速实现功能，满足时间限制
- ✅ LLM 调用简单直接，错误处理成熟
- ✅ FastAPI 自动生成的 API 文档提升项目专业性
- ✅ Docker Compose 确保评审者可以一键运行
- ✅ 代码简洁，易于答辩和解释

### 消极影响

- ❌ Python GIL 限制了 CPU 密集型任务的并行性（但本项目是 I/O 密集型，影响小）
- ❌ 运行时性能不如 Go（但性能不是考察重点）
- ❌ Docker 镜像较大（Python + 依赖，约 500MB）

### 风险缓解

- **内存占用**: 通过流式计算文件哈希避免大文件全部读入内存
- **并发限制**: 使用 `asyncio.Semaphore` 控制最大并发数为 3
- **部署体积**: 使用 Python 3.11-slim 基础镜像，减少镜像大小

## 相关决策

- ADR-002: 异步处理方案（基于 asyncio）
- ADR-003: 数据库设计（PostgreSQL + SQLAlchemy）
