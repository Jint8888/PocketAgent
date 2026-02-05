"""
行为规则引擎 - 简化版（第一步实施）

提供全局规则加载和注入功能。
未来可扩展为支持多规则文件、条件激活等高级功能。

作者: AI Assistant
版本: v1.0 (基础版)
日期: 2024-01-23
"""
import os
from typing import Optional
from pathlib import Path


# 规则目录路径
RULES_DIR = Path(__file__).parent / "rules"

# 是否启用规则系统（可用于快速开关）
ENABLE_RULES_SYSTEM = True


class RulesEngine:
    """
    行为规则引擎（简化版）

    当前功能：
    - 加载 global.md 全局规则
    - 缓存规则内容
    - 注入规则到 prompt

    未来扩展：
    - 支持多规则文件
    - 条件激活
    - 规则优先级
    """

    def __init__(self):
        self._global_rules_cache: Optional[str] = None
        self._enabled = ENABLE_RULES_SYSTEM

    def load_global_rules(self) -> str:
        """
        加载全局规则文件（带缓存）

        Returns:
            格式化的规则文本，如果加载失败或禁用则返回空字符串
        """
        # 检查是否启用
        if not self._enabled:
            return ""

        # 检查缓存
        if self._global_rules_cache is not None:
            return self._global_rules_cache

        # 构建文件路径
        file_path = RULES_DIR / "global.md"

        # 检查文件是否存在
        if not file_path.exists():
            print(f"[WARN] Global rules file not found: {file_path}")
            print(f"[INFO] Rules system disabled. Create {file_path} to enable.")
            self._global_rules_cache = ""
            return ""

        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 格式化规则
            formatted = self._format_rules(content)

            # 缓存
            self._global_rules_cache = formatted
            print(f"[OK] Global rules loaded: {len(content)} chars")

            return formatted

        except Exception as e:
            print(f"[ERROR] Failed to load global rules: {e}")
            self._global_rules_cache = ""
            return ""

    def _format_rules(self, content: str) -> str:
        """
        格式化规则文本，添加标题框

        Args:
            content: 原始规则内容

        Returns:
            格式化后的规则文本
        """
        formatted = "\n\n".join([
            "=" * 70,
            "📋 BEHAVIOR RULES (行为准则)",
            "=" * 70,
            "",
            content,
            "",
            "=" * 70,
            "⚠️  请严格遵守以上规则，确保行为一致性和质量",
            "=" * 70,
        ])

        return formatted

    def inject_rules_to_prompt(self, prompt: str, include_rules: bool = True) -> str:
        """
        将规则注入到 prompt

        Args:
            prompt: 原始 prompt
            include_rules: 是否包含规则（可用于测试对比）

        Returns:
            注入规则后的 prompt
        """
        if not include_rules or not self._enabled:
            return prompt

        # 加载规则
        rules = self.load_global_rules()

        if not rules:
            return prompt

        # 在 prompt 前注入规则
        return f"{rules}\n\n{prompt}"

    def reload(self):
        """清除缓存，重新加载规则（用于开发调试）"""
        self._global_rules_cache = None
        print("[INFO] Rules cache cleared. Will reload on next access.")

    def disable(self):
        """禁用规则系统"""
        self._enabled = False
        print("[INFO] Rules system disabled.")

    def enable(self):
        """启用规则系统"""
        self._enabled = True
        print("[INFO] Rules system enabled.")

    def is_enabled(self) -> bool:
        """检查规则系统是否启用"""
        return self._enabled


# ============================================================================
# 全局单例
# ============================================================================

_rules_engine: Optional[RulesEngine] = None


def get_rules_engine() -> RulesEngine:
    """
    获取规则引擎单例

    Returns:
        RulesEngine 实例
    """
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = RulesEngine()
    return _rules_engine


# ============================================================================
# 便捷函数
# ============================================================================

def load_rules() -> str:
    """
    便捷函数：加载全局规则

    Returns:
        格式化的规则文本
    """
    engine = get_rules_engine()
    return engine.load_global_rules()


def inject_rules(prompt: str, include_rules: bool = True) -> str:
    """
    便捷函数：将规则注入到 prompt

    Args:
        prompt: 原始 prompt
        include_rules: 是否包含规则

    Returns:
        注入规则后的 prompt
    """
    engine = get_rules_engine()
    return engine.inject_rules_to_prompt(prompt, include_rules)


def reload_rules():
    """便捷函数：重新加载规则"""
    engine = get_rules_engine()
    engine.reload()


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    """测试规则引擎"""
    print("=" * 70)
    print("规则引擎测试")
    print("=" * 70)
    print()

    # 测试 1: 加载规则
    print("【测试 1】加载全局规则")
    engine = get_rules_engine()
    rules = engine.load_global_rules()

    if rules:
        print(f"✅ 规则加载成功，长度: {len(rules)} 字符")
        print()
        print("规则预览（前 500 字符）:")
        print("-" * 70)
        print(rules[:500])
        print("-" * 70)
    else:
        print("❌ 规则加载失败")

    print()

    # 测试 2: 注入规则到 prompt
    print("【测试 2】注入规则到 prompt")
    base_prompt = "你是一个工具调用专家，请根据用户需求选择合适的工具。"

    full_prompt = engine.inject_rules_to_prompt(base_prompt)

    print(f"原始 prompt 长度: {len(base_prompt)} 字符")
    print(f"注入后 prompt 长度: {len(full_prompt)} 字符")
    print(f"规则占比: {(len(full_prompt) - len(base_prompt)) / len(full_prompt) * 100:.1f}%")
    print()

    # 测试 3: 缓存测试
    print("【测试 3】缓存测试")
    import time

    # 清除缓存
    engine.reload()

    # 第一次加载（从文件）
    start = time.time()
    engine.load_global_rules()
    first_time = time.time() - start

    # 第二次加载（从缓存）
    start = time.time()
    engine.load_global_rules()
    second_time = time.time() - start

    print(f"首次加载耗时: {first_time*1000:.2f} ms")
    print(f"缓存加载耗时: {second_time*1000:.2f} ms")
    print(f"性能提升: {(first_time/second_time):.1f}x")
    print()

    # 测试 4: 启用/禁用
    print("【测试 4】启用/禁用测试")
    print(f"当前状态: {'启用' if engine.is_enabled() else '禁用'}")

    engine.disable()
    rules_disabled = engine.load_global_rules()
    print(f"禁用后规则长度: {len(rules_disabled)}")

    engine.enable()
    rules_enabled = engine.load_global_rules()
    print(f"启用后规则长度: {len(rules_enabled)}")

    print()
    print("=" * 70)
    print("测试完成！")
    print("=" * 70)
