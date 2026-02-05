"""
记忆工具模块

提供向量嵌入和相似度搜索功能，用于 Agent 记忆。
使用本地 Sentence Transformers 进行向量检索。
"""

import os
import numpy as np
import threading
from typing import List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()


# ============================================================================
# Embedding 相关
# ============================================================================

# 默认配置
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 全局模型实例（懒加载）
_embedding_model = None
_embedding_lock = threading.Lock()  # 线程安全锁


def get_hf_endpoint() -> str:
    """获取 HuggingFace 端点地址

    优先使用环境变量 HF_ENDPOINT，否则使用国内镜像。

    Returns:
        HuggingFace 端点 URL
    """
    return os.environ.get("HF_ENDPOINT", DEFAULT_HF_ENDPOINT)


def get_embedding_model_name() -> str:
    """获取 Embedding 模型名称

    优先使用环境变量 EMBEDDING_MODEL_NAME，否则使用默认多语言模型。

    Returns:
        模型名称
    """
    return os.environ.get("EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)


def _get_embedding_model():
    """获取 Sentence Transformer 模型单例（线程安全）

    使用多语言模型 paraphrase-multilingual-MiniLM-L12-v2，
    对中文语义理解比英文模型 all-MiniLM-L6-v2 好很多。
    测试结果: 中文语义匹配准确率从 28.6% 提升到 100%

    自动配置国内镜像以解决网络超时问题。
    使用双重检查锁定模式确保线程安全。
    """
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            # 双重检查锁定（Double-Checked Locking）
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer

                # 配置 HuggingFace 镜像端点（解决国内网络超时问题）
                hf_endpoint = get_hf_endpoint()
                os.environ["HF_ENDPOINT"] = hf_endpoint

                model_name = get_embedding_model_name()

                print(f"[INFO] Loading Embedding model...")
                print(f"[INFO] HF_ENDPOINT: {hf_endpoint}")

                # 多语言模型，中文语义理解更准确
                _embedding_model = SentenceTransformer(model_name)
                print(f"[OK] Embedding model loaded ({model_name})")
    return _embedding_model


async def get_embedding_async(text: str) -> np.ndarray:
    """
    异步获取文本的向量嵌入

    使用本地 Sentence Transformers 模型，无需 API 调用。

    Args:
        text: 要嵌入的文本

    Returns:
        384 维的 numpy 数组

    Raises:
        VectorMemoryError: 当嵌入失败时抛出（不再静默返回零向量）
    """
    import asyncio
    from exceptions import VectorMemoryError

    # sentence-transformers 是同步的，用线程池包装
    loop = asyncio.get_running_loop()

    def _encode():
        model = _get_embedding_model()
        return model.encode(text, convert_to_numpy=True)

    try:
        embedding = await loop.run_in_executor(None, _encode)
        return embedding.astype(np.float32)
    except Exception as e:
        # 显式抛出异常，不再静默返回零向量
        raise VectorMemoryError(
            operation="embedding",
            reason=str(e),
            context={"text_preview": text[:100] if len(text) > 100 else text}
        )


def get_embedding(text: str) -> np.ndarray:
    """
    同步获取文本的向量嵌入

    Raises:
        VectorMemoryError: 当嵌入失败时抛出
    """
    from exceptions import VectorMemoryError

    try:
        model = _get_embedding_model()
        return model.encode(text, convert_to_numpy=True).astype(np.float32)
    except Exception as e:
        raise VectorMemoryError(
            operation="embedding",
            reason=str(e),
            context={"text_preview": text[:100] if len(text) > 100 else text}
        )


# ============================================================================
# 向量索引相关
# ============================================================================

# 性能警告阈值
MEMORY_SIZE_WARNING_THRESHOLD = 5000


class SimpleVectorIndex:
    """
    简单的向量索引实现

    使用 numpy 进行余弦相似度搜索，无需 FAISS 依赖。
    适合小规模记忆存储（< 10000 条）。
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.vectors: List[np.ndarray] = []
        self.items: List[dict] = []
        self._warned_size = False  # 避免重复打印性能警告

    def add(self, vector: np.ndarray, item: dict) -> int:
        """
        添加向量和对应的项目

        Args:
            vector: 嵌入向量
            item: 关联的数据（如对话内容）

        Returns:
            插入位置的索引
        """
        self.vectors.append(vector.flatten())
        self.items.append(item)
        return len(self.vectors) - 1

    def search(self, query_vector: np.ndarray, k: int = 3) -> List[Tuple[dict, float]]:
        """
        搜索最相似的 k 个项目

        Args:
            query_vector: 查询向量
            k: 返回结果数量

        Returns:
            列表，每项为 (item, similarity_score) 元组
        """
        if not self.vectors:
            return []

        # 性能警告：线性搜索在大数据量时会变慢（只警告一次）
        if len(self.vectors) > MEMORY_SIZE_WARNING_THRESHOLD and not self._warned_size:
            print(f"[WARN] Memory index has {len(self.vectors)} items, "
                  f"search may be slow. Consider upgrading to FAISS.")
            self._warned_size = True

        query = query_vector.flatten()

        # 计算所有向量的余弦相似度（复用 _cosine_similarity 方法）
        similarities = [
            (i, self._cosine_similarity(query, vec))
            for i, vec in enumerate(self.vectors)
        ]

        # 按相似度降序排序并返回 top-k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [(self.items[idx], sim) for idx, sim in similarities[:k]]

    def __len__(self):
        return len(self.vectors)

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算两个向量的余弦相似度"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 > 0 and norm2 > 0:
            return float(np.dot(vec1, vec2) / (norm1 * norm2))
        return 0.0

    def find_similar(self, vector: np.ndarray, threshold: float = 0.85) -> Optional[Tuple[int, float]]:
        """
        查找与给定向量相似度超过阈值的记忆

        Args:
            vector: 查询向量
            threshold: 相似度阈值（默认 0.85）

        Returns:
            如果找到相似记忆，返回 (索引, 相似度)；否则返回 None
        """
        if not self.vectors:
            return None

        query = vector.flatten()
        best_idx = -1
        best_sim = 0.0

        for i, vec in enumerate(self.vectors):
            sim = self._cosine_similarity(query, vec)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_sim >= threshold:
            return (best_idx, best_sim)
        return None

    def update(self, index: int, vector: np.ndarray, item: dict):
        """
        更新指定索引位置的记忆

        Args:
            index: 要更新的索引
            vector: 新的嵌入向量
            item: 新的关联数据
        """
        if 0 <= index < len(self.vectors):
            self.vectors[index] = vector.flatten()
            self.items[index] = item

    def add_or_update(self, vector: np.ndarray, item: dict,
                      dedup_threshold: float = 0.85) -> Tuple[int, bool]:
        """
        添加新记忆或更新相似的已有记忆（去重）

        Args:
            vector: 嵌入向量
            item: 关联的数据
            dedup_threshold: 去重相似度阈值（默认 0.85）

        Returns:
            (索引, 是否为新增) - 如果是更新则返回 (idx, False)，新增则返回 (idx, True)
        """
        similar = self.find_similar(vector, dedup_threshold)

        if similar:
            idx, sim = similar
            # 更新已有记忆
            self.update(idx, vector, item)
            return (idx, False)
        else:
            # 添加新记忆
            idx = self.add(vector, item)
            return (idx, True)


    def save(self, filepath: str):
        """
        保存索引到文件（原子性写入）

        使用临时文件 + 重命名的方式，确保写入过程中程序崩溃不会损坏数据。
        """
        import json
        import tempfile
        import shutil

        data = {
            "dimension": self.dimension,
            "vectors": [v.tolist() for v in self.vectors],
            "items": self.items
        }

        # 获取目标目录（确保临时文件和目标文件在同一文件系统）
        abs_filepath = os.path.abspath(filepath)
        dir_path = os.path.dirname(abs_filepath) or '.'

        # 先写入临时文件
        fd, temp_path = tempfile.mkstemp(suffix='.tmp', dir=dir_path)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 原子性重命名（同一文件系统内是原子操作）
            shutil.move(temp_path, abs_filepath)
            print(f"[OK] Memory saved: {filepath}")
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            print(f"[ERROR] Failed to save memory: {e}")
            raise

    def load(self, filepath: str) -> bool:
        """从文件加载索引"""
        import json
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.dimension = data["dimension"]
            self.vectors = [np.array(v, dtype=np.float32) for v in data["vectors"]]
            self.items = data["items"]
            print(f"[OK] Memory loaded: {len(self.items)} items")
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"[WARN] Load memory failed: {e}")
            return False


# 全局记忆索引
_memory_index: Optional[SimpleVectorIndex] = None
_memory_index_lock = threading.Lock()  # 线程安全锁


def get_memory_index() -> SimpleVectorIndex:
    """获取全局记忆索引单例（线程安全）

    使用双重检查锁定模式确保线程安全。
    """
    global _memory_index
    if _memory_index is None:
        with _memory_index_lock:
            # 双重检查锁定（Double-Checked Locking）
            if _memory_index is None:
                _memory_index = SimpleVectorIndex(dimension=384)
                # 尝试从文件加载
                _memory_index.load("memory_index.json")
    return _memory_index

