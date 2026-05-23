"""
SciPDF AI论文处理系统 v3 - 配置文件
基于 Pydantic Settings 的配置管理
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, Set

from dotenv import load_dotenv

# 加载 .env 文件到环境变量
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # backend/app/core -> v3 root
load_dotenv(BASE_DIR / ".env")

# 数据目录配置
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
NER_RESULTS_DIR = DATA_DIR / "ner_results"
RE_RESULTS_DIR = DATA_DIR / "re_results"
FAILED_LOGS_DIR = DATA_DIR / "failed_logs"

# Stanza 模型资源目录
STANZA_RESOURCES_DIR = BASE_DIR / "stanza_resources"


class Settings(BaseSettings):
    """应用配置类"""

    # 应用基础配置
    APP_NAME: str = "SciPDF AI论文处理系统"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = True

    # API配置
    API_PREFIX: str = "/api"
    API_V1_PREFIX: str = "/api/v1"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库配置 - MySQL (v3 使用云数据库)
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "scipdf_system")

    @property
    def DATABASE_URL(self) -> str:
        """生成数据库连接 URL (同步)"""
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """生成异步数据库连接 URL"""
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    # Milvus 向量数据库配置 (云端部署)
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "8.147.69.101")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_USER: str = os.getenv("MILVUS_USER", "")
    MILVUS_PASSWORD: str = os.getenv("MILVUS_PASSWORD", "")
    MILVUS_DATABASE: str = os.getenv("MILVUS_DATABASE", "scipdf")

    # Milvus Collection 配置
    MILVUS_COLLECTION_PAPER: str = "paper_embeddings"  # 论文摘要向量
    MILVUS_COLLECTION_ENTITY: str = "entity_embeddings"  # 实体向量
    MILVUS_COLLECTION_SENTENCE: str = "sentence_embeddings"  # 句子向量

    @property
    def MILVUS_URI(self) -> str:
        """生成 Milvus 连接 URI"""
        if self.MILVUS_USER and self.MILVUS_PASSWORD:
            return f"http://{self.MILVUS_USER}:{self.MILVUS_PASSWORD}@{self.MILVUS_HOST}:{self.MILVUS_PORT}"
        return f"http://{self.MILVUS_HOST}:{self.MILVUS_PORT}"

    # Redis 配置 (缓存 + Celery Broker)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    @property
    def REDIS_URL(self) -> str:
        """生成 Redis 连接 URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # GROBID配置
    GROBID_URL: str = os.getenv("GROBID_URL", "http://localhost:8070")

    # LLM 配置
    API_KEY: str = os.getenv("API_KEY", "")
    BASE_URL: str = os.getenv("BASE_URL", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "qwen-plus")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

    # 文件上传配置
    UPLOAD_DIR: Path = UPLOADS_DIR  # 上传目录
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: Set[str] = {".pdf"}

    # 处理配置
    MAX_PROCESSING_TIME: int = 300  # 单文件最大处理时间（秒）
    BATCH_SIZE: int = 10  # 批量处理数量

    # PDF 处理重试配置
    PDF_MAX_RETRIES: int = int(os.getenv("PDF_MAX_RETRIES", "3"))
    PDF_RETRY_DELAY: int = int(os.getenv("PDF_RETRY_DELAY", "2"))

    # JWT 认证配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Celery 配置
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Celery 使用 Redis 作为 broker
        self.CELERY_BROKER_URL = self.REDIS_URL
        self.CELERY_RESULT_BACKEND = self.REDIS_URL

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(BASE_DIR / "logs" / "app.log")

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


# 创建配置实例
settings = Settings()


def ensure_directories():
    """确保所有必要的目录都存在"""
    dirs = [UPLOADS_DIR, RESULTS_DIR, NER_RESULTS_DIR, RE_RESULTS_DIR, FAILED_LOGS_DIR]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    # 确保日志目录存在
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)