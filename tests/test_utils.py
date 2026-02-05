"""
Utils 模块单元测试

测试 LLM 调用工具函数。

运行方式:
    pytest tests/test_utils.py -v
"""
import pytest
import os


class TestUtilsImports:
    """测试 utils 模块导入"""

    def test_import_call_llm(self):
        """测试导入 call_llm 函数"""
        from utils import call_llm
        assert callable(call_llm)

    def test_import_call_llm_async(self):
        """测试导入 call_llm_async 函数"""
        from utils import call_llm_async
        assert callable(call_llm_async)

    def test_import_async_input(self):
        """测试导入 async_input 函数"""
        from utils import async_input
        assert callable(async_input)


class TestUtilsConstants:
    """测试 utils 模块常量"""

    def test_default_model(self):
        """测试默认模型常量"""
        from utils import DEFAULT_MODEL
        assert DEFAULT_MODEL is not None
        assert isinstance(DEFAULT_MODEL, str)

    def test_default_temperature(self):
        """测试默认温度常量"""
        from utils import DEFAULT_TEMPERATURE
        assert DEFAULT_TEMPERATURE is not None
        assert 0 <= DEFAULT_TEMPERATURE <= 2

    def test_max_retries(self):
        """测试最大重试次数常量"""
        from utils import MAX_RETRIES
        assert MAX_RETRIES is not None
        assert MAX_RETRIES >= 1


class TestCallLlmAsync:
    """测试 call_llm_async 函数（模拟测试，不实际调用 API）"""

    def test_call_llm_async_is_coroutine(self):
        """测试 call_llm_async 是协程函数"""
        import asyncio
        from utils import call_llm_async

        # 验证返回的是协程
        messages = [{"role": "user", "content": "test"}]
        coro = call_llm_async(messages)
        assert asyncio.iscoroutine(coro)

        # 关闭协程避免警告
        coro.close()

    def test_async_input_is_coroutine(self):
        """测试 async_input 是协程函数"""
        import asyncio
        from utils import async_input

        # async_input 需要在事件循环中调用
        # 这里只验证函数存在且是异步函数
        assert asyncio.iscoroutinefunction(async_input)
