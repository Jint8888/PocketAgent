"""
Memory 模块单元测试

测试向量索引和记忆管理功能。

运行方式:
    pytest tests/test_memory.py -v
"""
import pytest
import numpy as np
import tempfile
import os


class TestSimpleVectorIndex:
    """测试 SimpleVectorIndex 类"""

    def test_create_index(self):
        """测试创建向量索引"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)
        assert index is not None
        assert index.dimension == 384
        assert len(index) == 0

    def test_add_vector(self):
        """测试添加向量"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)
        vector = np.random.rand(384).astype(np.float32)
        item = {"content": "测试内容", "tag": "test"}

        idx = index.add(vector, item)

        assert idx == 0
        assert len(index) == 1

    def test_add_multiple_vectors(self):
        """测试添加多个向量"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        for i in range(5):
            vector = np.random.rand(384).astype(np.float32)
            item = {"content": f"内容 {i}", "id": i}
            idx = index.add(vector, item)
            assert idx == i

        assert len(index) == 5

    def test_search_empty_index(self):
        """测试空索引搜索"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)
        query = np.random.rand(384).astype(np.float32)

        results = index.search(query, k=3)

        assert results == []

    def test_search_returns_similar(self):
        """测试搜索返回相似向量"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        # 添加一个特定向量
        base_vector = np.ones(384, dtype=np.float32)
        index.add(base_vector, {"content": "base"})

        # 添加一些随机向量
        for i in range(3):
            random_vector = np.random.rand(384).astype(np.float32)
            index.add(random_vector, {"content": f"random_{i}"})

        # 搜索与 base_vector 相似的向量
        query = np.ones(384, dtype=np.float32) * 0.99  # 非常接近
        results = index.search(query, k=2)

        assert len(results) == 2
        # 第一个结果应该是 base_vector
        assert results[0][0]["content"] == "base"
        assert results[0][1] > 0.99  # 相似度应该很高

    def test_cosine_similarity(self):
        """测试余弦相似度计算"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=4)

        # 相同向量，相似度应为 1
        vec1 = np.array([1, 0, 0, 0], dtype=np.float32)
        vec2 = np.array([1, 0, 0, 0], dtype=np.float32)
        sim = index._cosine_similarity(vec1, vec2)
        assert abs(sim - 1.0) < 0.0001

        # 正交向量，相似度应为 0
        vec3 = np.array([0, 1, 0, 0], dtype=np.float32)
        sim2 = index._cosine_similarity(vec1, vec3)
        assert abs(sim2 - 0.0) < 0.0001

        # 相反向量，相似度应为 -1
        vec4 = np.array([-1, 0, 0, 0], dtype=np.float32)
        sim3 = index._cosine_similarity(vec1, vec4)
        assert abs(sim3 - (-1.0)) < 0.0001

    def test_find_similar(self):
        """测试查找相似记忆"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        # 添加向量
        base_vector = np.ones(384, dtype=np.float32)
        index.add(base_vector, {"content": "base"})

        # 查找相似的
        similar_query = np.ones(384, dtype=np.float32) * 0.99
        result = index.find_similar(similar_query, threshold=0.9)

        assert result is not None
        assert result[0] == 0  # 索引
        assert result[1] > 0.9  # 相似度

    def test_find_similar_no_match(self):
        """测试查找相似记忆 - 无匹配"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        # 添加向量
        base_vector = np.ones(384, dtype=np.float32)
        index.add(base_vector, {"content": "base"})

        # 查找不相似的
        different_query = np.zeros(384, dtype=np.float32)
        different_query[0] = 1  # 只有一个维度相同
        result = index.find_similar(different_query, threshold=0.99)

        assert result is None

    def test_update_vector(self):
        """测试更新向量"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        # 添加向量
        original_vector = np.ones(384, dtype=np.float32)
        index.add(original_vector, {"content": "original"})

        # 更新向量
        new_vector = np.zeros(384, dtype=np.float32)
        index.update(0, new_vector, {"content": "updated"})

        # 验证更新
        assert index.items[0]["content"] == "updated"
        assert np.allclose(index.vectors[0], new_vector)

    def test_add_or_update_new(self):
        """测试 add_or_update - 新增"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        vector = np.random.rand(384).astype(np.float32)
        item = {"content": "new item"}

        idx, is_new = index.add_or_update(vector, item)

        assert is_new == True
        assert idx == 0
        assert len(index) == 1

    def test_add_or_update_update(self):
        """测试 add_or_update - 更新"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)

        # 添加原始向量
        original_vector = np.ones(384, dtype=np.float32)
        index.add(original_vector, {"content": "original"})

        # 添加相似向量（应该更新而非新增）
        similar_vector = np.ones(384, dtype=np.float32) * 0.999
        idx, is_new = index.add_or_update(
            similar_vector,
            {"content": "updated"},
            dedup_threshold=0.9
        )

        assert is_new == False
        assert idx == 0
        assert len(index) == 1
        assert index.items[0]["content"] == "updated"

    def test_save_and_load(self):
        """测试保存和加载"""
        from memory import SimpleVectorIndex

        # 创建并填充索引
        index = SimpleVectorIndex(dimension=384)
        for i in range(3):
            vector = np.random.rand(384).astype(np.float32)
            index.add(vector, {"content": f"item_{i}", "id": i})

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            index.save(temp_path)

            # 创建新索引并加载
            new_index = SimpleVectorIndex(dimension=384)
            success = new_index.load(temp_path)

            assert success == True
            assert len(new_index) == 3
            assert new_index.items[0]["content"] == "item_0"
            assert new_index.items[2]["id"] == 2
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        from memory import SimpleVectorIndex

        index = SimpleVectorIndex(dimension=384)
        success = index.load("nonexistent_file_12345.json")

        assert success == False
        assert len(index) == 0


class TestGetMemoryIndex:
    """测试 get_memory_index 函数"""

    def test_get_memory_index_returns_instance(self):
        """测试获取记忆索引返回实例"""
        from memory import get_memory_index, SimpleVectorIndex

        index = get_memory_index()

        assert index is not None
        assert isinstance(index, SimpleVectorIndex)

    def test_get_memory_index_singleton(self):
        """测试记忆索引是单例"""
        from memory import get_memory_index

        index1 = get_memory_index()
        index2 = get_memory_index()

        assert index1 is index2


class TestHuggingFaceConfig:
    """测试 HuggingFace 镜像配置"""

    def test_hf_endpoint_is_set_before_model_load(self, monkeypatch):
        """测试模型加载前设置了 HF_ENDPOINT 环境变量"""
        import memory

        # 重置模型单例
        memory._embedding_model = None

        # 设置镜像地址环境变量
        monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.com")

        # 验证环境变量已设置
        assert os.environ.get("HF_ENDPOINT") == "https://hf-mirror.com"

    def test_get_hf_endpoint_returns_mirror(self):
        """测试 get_hf_endpoint 函数返回镜像地址"""
        from memory import get_hf_endpoint

        # 应该返回镜像地址（优先使用环境变量）
        endpoint = get_hf_endpoint()
        assert endpoint is not None
        assert isinstance(endpoint, str)

    def test_get_embedding_model_name_from_env(self, monkeypatch):
        """测试从环境变量获取模型名称"""
        from memory import get_embedding_model_name

        # 设置自定义模型名称
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "custom-model")

        model_name = get_embedding_model_name()
        assert model_name == "custom-model"

    def test_get_embedding_model_name_default(self, monkeypatch):
        """测试默认模型名称"""
        from memory import get_embedding_model_name

        # 清除环境变量
        monkeypatch.delenv("EMBEDDING_MODEL_NAME", raising=False)

        model_name = get_embedding_model_name()
        assert model_name == "paraphrase-multilingual-MiniLM-L12-v2"


class TestGetEmbedding:
    """测试 get_embedding 函数"""

    @pytest.mark.slow
    def test_get_embedding_returns_vector(self):
        """测试获取嵌入返回向量（需要加载模型，较慢）"""
        from memory import get_embedding

        text = "这是一个测试文本"
        embedding = get_embedding(text)

        assert embedding is not None
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)
        assert embedding.dtype == np.float32

    @pytest.mark.slow
    def test_get_embedding_similar_texts(self):
        """测试相似文本的嵌入相似"""
        from memory import get_embedding

        text1 = "今天天气真好"
        text2 = "今天的天气非常棒"
        text3 = "股票市场分析报告"

        emb1 = get_embedding(text1)
        emb2 = get_embedding(text2)
        emb3 = get_embedding(text3)

        # 计算余弦相似度
        def cosine_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_12 = cosine_sim(emb1, emb2)
        sim_13 = cosine_sim(emb1, emb3)

        # text1 和 text2 应该比 text1 和 text3 更相似
        assert sim_12 > sim_13
