"""
SciPDF AI论文处理系统 v3 - FastAPI应用入口
"""
import logging
import sys
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.config import settings, ensure_directories, BASE_DIR
from backend.app.models.base import init_db, AsyncSessionLocal
from backend.app.api.v1 import pdf, ner, re, batch, domain, extraction, user, config, task, excel_extraction, jc, comprehensive
from backend.app.api import websocket
from backend.app.domain import DomainRegistry
from backend.app.domain.material import REBCOAnalyzer  # 导入以触发装饰器注册

# 日志目录
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    """配置日志（避免重复配置）"""
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    console_handler.stream = sys.stdout
    root_logger.addHandler(console_handler)

    # 文件处理器 - 主日志
    log_file = LOG_DIR / "app.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 错误日志单独记录
    error_log_file = LOG_DIR / "error.log"
    error_handler = logging.FileHandler(error_log_file, encoding="utf-8")
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

    # 降低第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("pymilvus").setLevel(logging.WARNING)


# 错误捕获中间件
class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """捕获所有请求异常并记录详细日志"""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # 记录详细错误信息
            error_logger = logging.getLogger("ERROR_HANDLER")
            error_logger.error(f"========== 请求异常 ==========")
            error_logger.error(f"时间: {datetime.now().isoformat()}")
            error_logger.error(f"请求方法: {request.method}")
            error_logger.error(f"请求URL: {request.url}")
            error_logger.error(f"请求头: {dict(request.headers)}")
            error_logger.error(f"异常类型: {type(e).__name__}")
            error_logger.error(f"异常信息: {str(e)}")
            error_logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")

            # 返回错误响应
            return JSONResponse(
                status_code=500,
                content={
                    "detail": f"Internal Server Error: {str(e)}",
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now().isoformat()
                }
            )


setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    ensure_directories()
    await init_db()  # 异步初始化数据库表
    logger.info("数据目录初始化完成")
    logger.info("数据库表初始化完成")

    # 初始化 Redis 连接
    from backend.app.core.redis_client import get_redis, close_redis
    await get_redis()
    logger.info("Redis 连接初始化完成")

    # Prompt模板表数据迁移（添加user_id列）
    from backend.app.services.prompt_service import migrate_prompt_table
    await migrate_prompt_table()

    # 导入默认Prompt模板
    from backend.app.services.prompt_service import get_prompt_service
    prompt_service = get_prompt_service()
    imported_count = await prompt_service.seed_default_prompts()
    logger.info(f"已导入 {imported_count} 个默认Prompt模板")

    # 确保默认管理员存在
    from backend.app.models.base import AsyncSessionLocal
    from backend.app.services.user_service import ensure_default_admin
    async with AsyncSessionLocal() as session:
        await ensure_default_admin(session)
    logger.info("默认管理员检查完成")

    # 初始化领域分析器
    rebco_analyzer = REBCOAnalyzer()
    DomainRegistry.register('rebco', rebco_analyzer)
    logger.info(f"已注册领域分析器: {DomainRegistry.list_domains()}")

    yield

    # 关闭时执行
    from backend.app.core.redis_client import close_redis
    await close_redis()
    logger.info("应用关闭")


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于AI的科学论文PDF处理与分析系统 - v3 重构版",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True,  # Token 在页面刷新后保留
    },
)


# 自定义 OpenAPI Schema，添加 Bearer JWT 认证支持
def custom_openapi():
    """为 Swagger UI 注入 Bearer JWT 安全方案"""
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "输入 JWT Access Token（登录接口返回的 access_token）",
        }
    }
    # 全局安全方案（各路由可通过 dependencies 覆盖）
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# 配置CORS中间件（从环境变量 CORS_ORIGINS 读取，逗号分隔）
_cors_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 错误日志中间件 - 暂时禁用，可能导致multipart上传问题
# app.add_middleware(ErrorLoggingMiddleware)

# 注册路由 - API v1
app.include_router(pdf.router, prefix=settings.API_V1_PREFIX, tags=["PDF处理"])
app.include_router(ner.router, prefix=settings.API_V1_PREFIX, tags=["NER处理"])
app.include_router(re.router, prefix=settings.API_V1_PREFIX, tags=["关系抽取"])
app.include_router(batch.router, prefix=settings.API_V1_PREFIX, tags=["批量处理"])
app.include_router(domain.router, prefix=settings.API_V1_PREFIX, tags=["领域分析"])
app.include_router(extraction.router, prefix=settings.API_V1_PREFIX, tags=["批量提取"])
app.include_router(user.router, prefix=settings.API_V1_PREFIX, tags=["用户认证"])
app.include_router(config.router, prefix=settings.API_V1_PREFIX, tags=["配置管理"])
app.include_router(task.router, prefix=settings.API_V1_PREFIX, tags=["任务管理"])
app.include_router(excel_extraction.router, prefix=settings.API_V1_PREFIX, tags=["Excel批量提取"])
app.include_router(jc.router, prefix=settings.API_V1_PREFIX, tags=["Jc数据库搜索"])
app.include_router(comprehensive.router, prefix=settings.API_V1_PREFIX, tags=["综合分析"])

# WebSocket 路由
app.include_router(websocket.router, tags=["WebSocket"])


# 全局异常处理器 - 捕获所有未处理的异常
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理的异常"""
    error_logger = logging.getLogger("ERROR_HANDLER")
    error_logger.error(f"========== 全局异常捕获 ==========")
    error_logger.error(f"时间: {datetime.now().isoformat()}")
    error_logger.error(f"请求方法: {request.method}")
    error_logger.error(f"请求URL: {request.url}")
    error_logger.error(f"异常类型: {type(exc).__name__}")
    error_logger.error(f"异常信息: {str(exc)}")
    error_logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error_type": type(exc).__name__,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "app_name": settings.APP_NAME
    }


@app.get("/", summary="根路径")
async def root():
    """根路径信息"""
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )