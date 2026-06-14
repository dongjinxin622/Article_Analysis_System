"""
异步任务引擎核心测试

验证 TaskHandlerRegistry / TaskEngineConfig / AsyncTaskEngine 等核心组件。
"""
from __future__ import annotations

import pytest

from backend.app.core.tasks.engine import (
    TaskHandlerRegistry,
    TaskHandlerFailure,
    AsyncTaskDefinition,
    AsyncTaskEngine,
    TaskEngineConfig,
    default_task_handler_registry,
)
from backend.app.core.tasks.constants import (
    ASYNC_TASKS_ATTRIBUTE,
    DEFAULT_TASK_STREAM_NAME,
    DEFAULT_TASK_CONSUMER_GROUP,
    DEFAULT_TASK_WORKER_MAX_CONCURRENCY,
)


# ==================== TaskHandlerRegistry 测试 ====================

class TestTaskHandlerRegistry:
    """TaskHandlerRegistry 测试"""

    def test_register_handler(self):
        """测试注册任务处理器"""
        registry = TaskHandlerRegistry()

        async def dummy_handler(context):
            return {"result": "ok"}

        registry.register("test.task", dummy_handler)
        assert "test.task" in registry.keys()

    def test_get_handler(self):
        """测试获取任务处理器"""
        registry = TaskHandlerRegistry()

        async def dummy_handler(context):
            return {"result": "ok"}

        registry.register("test.task", dummy_handler)
        handler = registry.get("test.task")
        assert handler is dummy_handler

    def test_get_handler_not_found(self):
        """测试获取不存在的处理器"""
        registry = TaskHandlerRegistry()
        handler = registry.get("nonexistent.task")
        assert handler is None

    def test_register_empty_task_type(self):
        """测试注册空任务类型应抛异常"""
        registry = TaskHandlerRegistry()

        with pytest.raises(ValueError, match="任务类型不能为空"):
            registry.register("", lambda ctx: None)

    def test_keys_sorted(self):
        """测试 keys() 返回排序后的列表"""
        registry = TaskHandlerRegistry()

        async def h1(ctx): pass
        async def h2(ctx): pass
        async def h3(ctx): pass

        registry.register("c.task", h3)
        registry.register("a.task", h1)
        registry.register("b.task", h2)

        keys = registry.keys()
        assert keys == ["a.task", "b.task", "c.task"]


# ==================== TaskHandlerFailure 测试 ====================

class TestTaskHandlerFailure:
    """TaskHandlerFailure 异常测试"""

    def test_task_handler_failure_basic(self):
        """测试基本异常"""
        exc = TaskHandlerFailure("任务执行失败")
        assert str(exc) == "任务执行失败"
        assert exc.error_code == "task_handler_failed"
        assert exc.error_message == "任务执行失败"
        assert exc.result == {}

    def test_task_handler_failure_with_error_code(self):
        """测试带错误码的异常"""
        exc = TaskHandlerFailure("PDF 解析失败", error_code="pdf_parse_error")
        assert exc.error_code == "pdf_parse_error"
        assert exc.error_message == "PDF 解析失败"

    def test_task_handler_failure_with_result(self):
        """测试带诊断结果的异常"""
        exc = TaskHandlerFailure(
            "NER 提取失败",
            error_code="ner_error",
            result={"detail": "模型超时", "duration": 300},
        )
        assert exc.result == {"detail": "模型超时", "duration": 300}


# ==================== AsyncTaskDefinition 测试 ====================

class TestAsyncTaskDefinition:
    """AsyncTaskDefinition 数据类测试"""

    def test_create_definition(self):
        """测试创建任务定义"""
        async def handler(ctx):
            return {"result": "ok"}

        definition = AsyncTaskDefinition(task_type="test.task", handler=handler)
        assert definition.task_type == "test.task"
        assert definition.handler is handler


# ==================== TaskEngineConfig 测试 ====================

class TestTaskEngineConfig:
    """TaskEngineConfig 配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = TaskEngineConfig()
        assert config.stream_name == DEFAULT_TASK_STREAM_NAME
        assert config.consumer_group == DEFAULT_TASK_CONSUMER_GROUP
        assert config.worker_max_concurrency == DEFAULT_TASK_WORKER_MAX_CONCURRENCY
        assert config.modules == ()

    def test_config_from_env(self, monkeypatch):
        """测试从环境变量构建配置"""
        monkeypatch.setenv("REDIS_TASK_STREAM_NAME", "custom:stream")
        monkeypatch.setenv("REDIS_TASK_CONSUMER_GROUP", "custom-workers")
        monkeypatch.setenv("ASYNC_TASK_WORKER_MAX_CONCURRENCY", "8")
        monkeypatch.setenv("ASYNC_TASK_WORKER_MAX_RETRIES", "5")
        monkeypatch.setenv("ASYNC_TASK_MODULES", "module1,module2")

        config = TaskEngineConfig.from_env()
        assert config.stream_name == "custom:stream"
        assert config.consumer_group == "custom-workers"
        assert config.worker_max_concurrency == 8
        assert config.worker_max_retries == 5
        assert config.modules == ("module1", "module2")


# ==================== AsyncTaskEngine 测试 ====================

class TestAsyncTaskEngine:
    """AsyncTaskEngine 引擎测试"""

    def test_engine_default_registry(self):
        """测试引擎使用默认注册表"""
        engine = AsyncTaskEngine()
        assert engine.registry is default_task_handler_registry

    def test_engine_custom_registry(self):
        """测试引擎使用自定义注册表"""
        registry = TaskHandlerRegistry()
        engine = AsyncTaskEngine(registry=registry)
        assert engine.registry is registry

    def test_register_task_handler(self):
        """测试注册任务处理器"""
        engine = AsyncTaskEngine()

        async def handler(ctx):
            return {"result": "ok"}

        engine.register_task_handler("test.task", handler)
        assert "test.task" in engine.registry.keys()

    def test_register_async_tasks_single(self):
        """测试注册单个任务定义"""
        engine = AsyncTaskEngine()

        async def handler(ctx):
            return {"result": "ok"}

        definition = AsyncTaskDefinition(task_type="test.single", handler=handler)
        engine.register_async_tasks(definition)
        assert "test.single" in engine.registry.keys()

    def test_register_async_tasks_multiple(self):
        """测试注册多个任务定义"""
        engine = AsyncTaskEngine()

        async def h1(ctx): pass
        async def h2(ctx): pass

        definitions = [
            AsyncTaskDefinition(task_type="test.h1", handler=h1),
            AsyncTaskDefinition(task_type="test.h2", handler=h2),
        ]
        engine.register_async_tasks(definitions)
        assert "test.h1" in engine.registry.keys()
        assert "test.h2" in engine.registry.keys()


# ==================== 常量测试 ====================

class TestConstants:
    """常量定义测试"""

    def test_async_tasks_attribute(self):
        """测试 ASYNC_TASKS_ATTRIBUTE 常量"""
        assert ASYNC_TASKS_ATTRIBUTE == "ASYNC_TASKS"

    def test_default_stream_name(self):
        """测试默认 Stream 名称"""
        assert DEFAULT_TASK_STREAM_NAME == "task:stream"

    def test_default_consumer_group(self):
        """测试默认消费组名称"""
        assert DEFAULT_TASK_CONSUMER_GROUP == "task-workers"

    def test_default_max_concurrency(self):
        """测试默认最大并发数"""
        assert DEFAULT_TASK_WORKER_MAX_CONCURRENCY == 4
