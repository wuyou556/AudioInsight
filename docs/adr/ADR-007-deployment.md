# ADR-007: 部署方案

**状态**: Accepted  
**日期**: 2026-09-10  
**决策者**: 开发团队

## 上下文

需要实现"简单部署"加分项，将服务部署到公网环境并提供可访问地址。关键考虑：
- 时间限制（部署不应占用过多时间）
- 成本限制（优先免费方案）
- 可靠性（演示期间可用）
- 一键启动的兼容性

可选平台：
1. **Railway** - 免费额度，原生支持 Docker Compose
2. **Render** - 免费层，但有冷启动延迟
3. **Fly.io** - 免费额度，全球部署
4. **云服务器**（阿里云/腾讯云学生机）- 完全控制，需手动配置
5. **Vercel/Netlify** - 不适合（主要面向前端和 Serverless）

## 决策

采用 **Railway** 作为部署平台。

### Railway 特性

**优势**:
- 原生支持 Docker Compose（无需修改配置）
- 提供 $5/月 免费额度（足够演示期间使用）
- GitHub 集成：push 自动部署
- 自动 HTTPS 证书
- 提供公网域名（`*.railway.app`）
- 内置数据库支持（PostgreSQL）
- 零冷启动延迟

**限制**:
- 免费额度有限（约 500 小时运行时间/月）
- 单个实例（无水平扩展）
- 美国/欧洲节点（国内访问可能稍慢）

### 部署配置

**1. railway.json** (Railway 配置):
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**2. Dockerfile 优化**:
```dockerfile
# 多阶段构建，减少镜像体积
FROM python:3.11-slim as builder

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 最终镜像
FROM python:3.11-slim

WORKDIR /app

# 复制依赖
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

# 创建 uploads 目录
RUN mkdir -p uploads

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Railway 会设置 PORT 环境变量
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

**3. 数据库配置**:
```python
# app/config.py
class Settings(BaseSettings):
    # Railway 自动提供 DATABASE_URL
    database_url: str = Field(
        default="postgresql://user:password@localhost:5432/audioinsight",
        env="DATABASE_URL"
    )
    
    # Railway 自动提供 PORT
    port: int = Field(default=8000, env="PORT")
```

**4. 环境变量** (Railway Dashboard 配置):
```bash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MAX_CONCURRENT_TASKS=3
```

### 部署流程

**本地测试**:
```bash
# 1. 构建 Docker 镜像
docker build -t audioinsight .

# 2. 本地运行测试
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e DEEPSEEK_API_KEY=sk-... \
  audioinsight
```

**部署到 Railway**:
```bash
# 1. 安装 Railway CLI
npm i -g @railway/cli

# 2. 登录
railway login

# 3. 初始化项目
railway init

# 4. 添加 PostgreSQL 服务
railway add --database postgresql

# 5. 部署
railway up

# 6. 查看部署 URL
railway domain
```

**或通过 GitHub 集成**:
1. 在 Railway 网站连接 GitHub 仓库
2. 配置环境变量
3. 每次 push 到 main 分支自动部署

### 健康检查端点

```python
# app/main.py

@app.get("/health")
async def health_check():
    """健康检查端点，供 Railway 和监控使用"""
    try:
        # 检查数据库连接
        await db.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "error": str(e)}
        )
```

## 考虑的替代方案

### 方案 2: Render

**优点**:
- 免费层永久可用
- 支持 Docker

**缺点**:
- 冷启动延迟（15 分钟不活动后休眠）
- 免费层不支持 Docker Compose（需要分离服务）
- 数据库免费层 90 天后过期

**拒绝理由**: 冷启动会影响演示体验，且数据库有时间限制。

### 方案 3: Fly.io

**优点**:
- 全球部署（包括亚洲节点）
- 免费额度充足
- 支持 Docker

**缺点**:
- 配置相对复杂（需要 fly.toml）
- 需要信用卡验证
- 文档不如 Railway 友好

**拒绝理由**: 配置复杂度高，且需要信用卡。

### 方案 4: 云服务器（学生机）

**优点**:
- 完全控制
- 国内访问速度快
- 长期可用

**缺点**:
- 需要手动配置（Nginx、SSL、防火墙）
- 运维成本高
- 不一定有学生机资格

**拒绝理由**: 时间成本高，不符合"简单部署"的定义。

## 决策理由

1. **简单**: GitHub push 自动部署，无需手动配置
2. **免费**: $5/月 额度足够演示使用
3. **可靠**: 零冷启动，演示期间始终可用
4. **兼容**: 支持 Docker Compose，本地配置可直接复用
5. **专业**: 提供 HTTPS、日志、监控等生产级功能

## 后果

### 积极影响

- ✅ 满足加分项"简单部署"要求
- ✅ 提供公网访问地址（`https://audioinsight.railway.app`）
- ✅ GitHub 集成，展示 DevOps 能力
- ✅ 自动 HTTPS，安全性好
- ✅ 演示期间稳定可用

### 消极影响

- ❌ 免费额度有限（约 500 小时/月，演示期间足够）
- ❌ 国内访问可能较慢（但可接受）
- ❌ 单实例，无高可用（本项目不要求）

### 成本预估

**Railway 免费额度**:
- 运行时间：500 小时/月
- 带宽：100 GB/月
- 预计使用：约 100-200 小时（演示 + 评审期间）

**超出后**:
- 按需付费：$0.000463/GB-秒
- 预计成本：< $5（如果演示期间持续运行）

## 部署检查清单

部署前确认：
- [ ] 所有环境变量已配置（`DEEPSEEK_API_KEY` 等）
- [ ] 数据库迁移脚本正常（`alembic upgrade head`）
- [ ] 健康检查端点返回 200
- [ ] 上传接口可正常工作
- [ ] uploads 目录可写

部署后验证：
- [ ] 访问公网 URL，查看 API 文档（`/docs`）
- [ ] 上传测试文件，验证完整流程
- [ ] 检查日志，确保无错误
- [ ] 测试幂等性、重试等加分项功能

## 监控和日志

**Railway 内置功能**:
```bash
# 查看实时日志
railway logs

# 查看指标（CPU、内存）
railway metrics
```

**应用日志**:
```python
# app/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 关键操作记录
logger.info(f"Task {task_id} started transcribing")
logger.error(f"Task {task_id} failed: {error}")
```

## README 部署说明

```markdown
## 部署

### Railway 一键部署

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template/...)

或手动部署：

1. Fork 本仓库
2. 在 [Railway](https://railway.app) 创建新项目
3. 连接 GitHub 仓库
4. 添加 PostgreSQL 数据库
5. 配置环境变量：
   - `DEEPSEEK_API_KEY`: 你的 DeepSeek API Key
   - `DEEPSEEK_API_BASE`: https://api.deepseek.com/v1
6. 部署完成后访问生成的 URL

### 部署地址

生产环境：https://audioinsight.railway.app

API 文档：https://audioinsight.railway.app/docs
```

## 相关决策

- ADR-001: 技术栈选择（Docker + FastAPI）
- ADR-002: 异步处理方案（无状态设计便于部署）
