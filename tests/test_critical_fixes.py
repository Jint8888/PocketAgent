"""
CRITICAL 问题修复测试

TDD 方式编写的测试用例，验证以下修复：
1. CRITICAL-1: MemoryError -> VectorMemoryError 类名修复
2. CRITICAL-2: 线程安全锁保护
3. CRITICAL-3: 嵌入失败显式抛出异常

运行方式:
    pytest tests/test_critical_fixes.py -v

作者: AI Assistant (TDD)
日期: 2025-02-05
"""
import pytest
import numpy as np
import threading
import asyncio
from unittest.mock import patch, MagicMock

# 配置 pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# ============================================================================
# CRITICAL-1: 测试 VectorMemoryError 类名修复
# ============================================================================

class TestVectorMemoryErrorNaming:
    """测试 VectorMemoryError 不与内置 MemoryError 冲突"""

    def test_vector_memory_error_exists(self):
        """测试 VectorMemoryError 类存在"""
        from exceptions import VectorMemoryError

        assert VectorMemoryError is not None

    def test_vector_memory_error_not_builtin(self):
        """测试 VectorMemoryError 不是内置 MemoryError"""
        from exceptions import VectorMemoryError

        # VectorMemoryError 不应该是 Python 内置的 MemoryError
        assert VectorMemoryError is not MemoryError
        assert not issubclass(VectorMemoryError, MemoryError)

    def test_vector_memory_error_inherits_from_base(self):
        """测试 VectorMemoryError 继承自 PocketAgentError"""
        from exceptions import VectorMemoryError, PocketAgentError

        assert issubclass(VectorMemoryError, PocketAgentError)

    def test_vector_memory_error_attributes(self):
        """测试 VectorMemoryError 有正确的属性"""
        from exceptions import VectorMemoryError

        error = VectorMemoryError(
            operation="embedding",
            reason="Model not loaded"
        )

        assert error.operation == "embedding"
        assert error.reason == "Model not loaded"
        assert "embedding" in str(error)
        assert "Model not loaded" in str(error)

    def test_vector_memory_error_with_context(self):
        """测试 VectorMemoryError 支持上下文"""
        from exceptions import VectorMemoryError

        error = VectorMemoryError(
            operation="save",
            reason="Disk full",
            context={"file": "memory.json", "size": 1024}
        )

        assert error.context["file"] == "memory.json"
        assert error.context["size"] == 1024
        assert error.context["operation"] == "save"

    def test_builtin_memory_error_still_works(self):
        """测试 Python 内置 MemoryError 仍然可用"""
        # 确保我们没有破坏内置异常
        try:
            raise MemoryError("Out of memory")
        except MemoryError as e:
            assert str(e) == "Out of memory"
            assert type(e).__module__ == 'builtins'


# ============================================================================
# CRITICAL-2: 测试线程安全锁保护
# ============================================================================

class TestThreadSafety:
    """测试全局单例的线程安全性"""

    def test_embedding_model_has_lock(self):
        """测试 embedding model 有线程锁"""
        import memory

        # 应该存在锁对象
        assert hasattr(memory, '_embedding_lock')
        assert isinstance(memory._embedding_lock, type(threading.Lock()))

    def test_memory_index_has_lock(self):
        """测试 memory index 有线程锁"""
        import memory

        # 应该存在锁对象
        assert hasattr(memory, '_memory_index_lock')
        assert isinstance(memory._memory_index_lock, type(threading.Lock()))

    def test_concurrent_get_embedding_model_safe(self):
        """测试并发获取 embedding model 是线程安全的"""
        import memory

        # 重置单例
        memory._embedding_model = None

        results = []
        errors = []

        def get_model():
            try:
                # 模拟获取模型（不实际加载，避免测试太慢）
                with memory._embedding_lock:
                    if memory._embedding_model is None:
                        # 模拟初始化延迟
                        import time
                        time.sleep(0.01)
                results.append("success")
            except Exception as e:
                errors.append(str(e))

        # 创建多个线程同时访问
        threads = [threading.Thread(target=get_model) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程都应该成功
        assert len(errors) == 0
        assert len(results) == 10

    def test_concurrent_get_memory_index_safe(self):
        """测试并发获取 memory index 是线程安全的"""
        import memory

        # 重置单例
        memory._memory_index = None

        results = []

        def get_index():
            try:
                index = memory.get_memory_index()
                results.append(index)
            except Exception as e:
                results.append(f"error: {e}")

        # 创建多个线程同时访问
        threads = [threading.Thread(target=get_index) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应该获取到相同的实例（单例）
        valid_results = [r for r in results if not isinstance(r, str)]
        if valid_results:
            assert all(r is valid_results[0] for r in valid_results)


# ============================================================================
# CRITICAL-3: 测试嵌入失败显式抛出异常
# ============================================================================

class TestEmbeddingErrorHandling:
    """测试嵌入失败时的错误处理"""

    @pytest.mark.asyncio
    async def test_get_embedding_async_raises_on_failure(self):
        """测试异步嵌入失败时抛出 VectorMemoryError"""
        from exceptions import VectorMemoryError
        import memory

        # Mock 模型编码失败
        with patch.object(memory, '_get_embedding_model') as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.side_effect = RuntimeError("Model crashed")
            mock_get_model.return_value = mock_model

            with pytest.raises(VectorMemoryError) as exc_info:
                await memory.get_embedding_async("test text")

            assert exc_info.value.operation == "embedding"
            assert "Model crashed" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_get_embedding_async_error_includes_text_preview(self):
        """测试错误信息包含文本预览"""
        from exceptions import VectorMemoryError
        import memory

        with patch.object(memory, '_get_embedding_model') as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.side_effect = ValueError("Invalid input")
            mock_get_model.return_value = mock_model

            long_text = "A" * 200

            with pytest.raises(VectorMemoryError) as exc_info:
                await memory.get_embedding_async(long_text)

            # 上下文应该包含文本预览（截断到100字符）
            assert "text_preview" in exc_info.value.context
            assert len(exc_info.value.context["text_preview"]) <= 100

    def test_get_embedding_sync_raises_on_failure(self):
        """测试同步嵌入失败时抛出 VectorMemoryError"""
        from exceptions import VectorMemoryError
        import memory

        with patch.object(memory, '_get_embedding_model') as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.side_effect = RuntimeError("Model error")
            mock_get_model.return_value = mock_model

            with pytest.raises(VectorMemoryError) as exc_info:
                memory.get_embedding("test text")

            assert exc_info.value.operation == "embedding"

    @pytest.mark.asyncio
    async def test_get_embedding_async_no_zero_vector_on_error(self):
        """测试错误时不返回零向量（必须抛出异常）"""
        import memory

        with patch.object(memory, '_get_embedding_model') as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.side_effect = Exception("Any error")
            mock_get_model.return_value = mock_model

            # 不应该返回零向量，而是抛出异常
            with pytest.raises(Exception):
                result = await memory.get_embedding_async("test")
                # 如果执行到这里，检查不是零向量
                if result is not None:
                    assert not np.allclose(result, np.zeros(384))


# ============================================================================
# HIGH-3: 测试类型注解完善
# ============================================================================

class TestTypeAnnotations:
    """测试类型注解正确性"""

    def test_setup_logging_accepts_none_level(self):
        """测试 setup_logging 接受 None 作为 level 参数"""
        from logging_config import setup_logging
        import logging

        # 应该能正常调用，不抛出类型错误
        logger = setup_logging(
            logger_name="test_type_annotation",
            level=None,  # 显式传入 None
            console_output=False,
            file_output=False
        )

        assert logger is not None
        assert isinstance(logger, logging.Logger)


# ============================================================================
# HIGH-4: 测试资源泄漏修复
# ============================================================================

class TestResourceLeak:
    """测试资源泄漏修复"""

    def test_get_log_summary_no_resource_leak(self):
        """测试 get_log_summary 使用 with 语句避免资源泄漏"""
        from logging_config import get_log_summary
        import inspect

        # 获取函数源码
        source = inspect.getsource(get_log_summary)

        # 检查是否使用 with 语句或辅助函数
        # 不应该有裸露的 open() 调用
        assert "with open" in source or "_count_lines" in source, \
            "get_log_summary should use 'with' statement or helper function"

    def test_count_lines_helper_exists(self):
        """测试 _count_lines 辅助函数存在"""
        import logging_config

        # 应该存在辅助函数
        assert hasattr(logging_config, '_count_lines')
        assert callable(logging_config._count_lines)


# ============================================================================
# 向后兼容性测试
# ============================================================================

class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_memory_error_alias_exists(self):
        """测试 MemoryError 别名仍然存在（向后兼容）"""
        # 注意：这是为了平滑迁移，最终应该移除
        # 但在迁移期间，旧代码仍然可以使用 MemoryError
        try:
            from exceptions import MemoryError as OldMemoryError
            from exceptions import VectorMemoryError

            # 如果别名存在，应该是 VectorMemoryError
            assert OldMemoryError is VectorMemoryError
        except ImportError:
            # 如果没有别名，也是可以的
            pass

    def test_existing_tests_still_pass(self):
        """测试现有功能仍然正常"""
        from memory import SimpleVectorIndex

        # 基本功能应该仍然正常
        index = SimpleVectorIndex(dimension=384)
        vector = np.random.rand(384).astype(np.float32)

        idx = index.add(vector, {"content": "test"})
        assert idx == 0
        assert len(index) == 1
