"""
行为规则系统测试脚本

用于验证规则引擎的基本功能。

运行方式：
    python test_rules.py

作者: AI Assistant
版本: v1.0
日期: 2024-01-23
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from rules_engine import get_rules_engine, load_rules, inject_rules


def test_basic_loading():
    """测试 1: 基本加载功能"""
    print("=" * 70)
    print("测试 1: 基本规则加载")
    print("=" * 70)

    rules = load_rules()

    if rules:
        print(f"✅ 规则加载成功")
        print(f"   规则长度: {len(rules)} 字符")
        print(f"   包含关键词检查:")

        checks = [
            ("BEHAVIOR RULES", "标题"),
            ("G-01", "规则编号"),
            ("MUST", "要求级别"),
            ("response_format", "工具调用规则"),
        ]

        for keyword, desc in checks:
            if keyword in rules:
                print(f"   ✅ {desc}: 找到 '{keyword}'")
            else:
                print(f"   ❌ {desc}: 未找到 '{keyword}'")

        print()
        print("规则预览（前 300 字符）:")
        print("-" * 70)
        print(rules[:300])
        print("...")
        print("-" * 70)
    else:
        print("❌ 规则加载失败")
        print("   请检查 rules/global.md 文件是否存在")

    print()
    return rules is not None


def test_injection():
    """测试 2: 规则注入功能"""
    print("=" * 70)
    print("测试 2: 规则注入到 Prompt")
    print("=" * 70)

    base_prompt = """你是一个工具调用专家。

请根据用户需求选择合适的工具并调用。

用户需求: 请生成一张猫的图片
"""

    # 注入规则
    full_prompt = inject_rules(base_prompt)

    print(f"原始 prompt 长度: {len(base_prompt)} 字符")
    print(f"注入后 prompt 长度: {len(full_prompt)} 字符")
    print(f"规则占比: {(len(full_prompt) - len(base_prompt)) / len(full_prompt) * 100:.1f}%")
    print()

    # 验证注入成功
    if "BEHAVIOR RULES" in full_prompt and base_prompt in full_prompt:
        print("✅ 规则注入成功")
        print()
        print("注入后 prompt 预览（前 500 字符）:")
        print("-" * 70)
        print(full_prompt[:500])
        print("...")
        print("-" * 70)
    else:
        print("❌ 规则注入失败")

    print()
    return "BEHAVIOR RULES" in full_prompt


def test_caching():
    """测试 3: 缓存性能"""
    print("=" * 70)
    print("测试 3: 缓存性能测试")
    print("=" * 70)

    import time

    engine = get_rules_engine()

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

    # 第三次加载（从缓存）
    start = time.time()
    engine.load_global_rules()
    third_time = time.time() - start

    print(f"首次加载（从文件）: {first_time*1000:.2f} ms")
    print(f"第二次加载（缓存）: {second_time*1000:.2f} ms")
    print(f"第三次加载（缓存）: {third_time*1000:.2f} ms")
    print()

    if second_time < first_time and third_time < first_time:
        print(f"✅ 缓存功能正常")
        print(f"   性能提升: {(first_time/second_time):.1f}x")
    else:
        print("⚠️  缓存性能异常")

    print()
    return second_time < first_time


def test_enable_disable():
    """测试 4: 启用/禁用功能"""
    print("=" * 70)
    print("测试 4: 启用/禁用功能")
    print("=" * 70)

    engine = get_rules_engine()

    # 测试当前状态
    print(f"初始状态: {'✅ 启用' if engine.is_enabled() else '❌ 禁用'}")

    # 禁用
    engine.disable()
    print(f"禁用后状态: {'✅ 启用' if engine.is_enabled() else '❌ 禁用'}")
    rules_disabled = engine.load_global_rules()
    print(f"禁用后规则长度: {len(rules_disabled)} 字符")

    # 启用
    engine.enable()
    print(f"启用后状态: {'✅ 启用' if engine.is_enabled() else '❌ 禁用'}")
    rules_enabled = engine.load_global_rules()
    print(f"启用后规则长度: {len(rules_enabled)} 字符")

    print()

    success = (
        len(rules_disabled) == 0 and
        len(rules_enabled) > 0 and
        engine.is_enabled()
    )

    if success:
        print("✅ 启用/禁用功能正常")
    else:
        print("❌ 启用/禁用功能异常")

    print()
    return success


def test_integration_example():
    """测试 5: 集成示例"""
    print("=" * 70)
    print("测试 5: 节点集成示例（模拟）")
    print("=" * 70)

    # 模拟节点的 prep_async 方法
    def simulate_node_prep():
        """模拟节点准备阶段"""
        # 加载规则
        rules = load_rules()

        # 构建基础 prompt
        base_prompt = "你是工具调用专家，请选择工具。"

        # 注入规则
        full_prompt = inject_rules(base_prompt)

        return full_prompt

    # 执行模拟
    print("模拟节点准备阶段...")
    result_prompt = simulate_node_prep()

    print(f"生成的 prompt 长度: {len(result_prompt)} 字符")

    if "BEHAVIOR RULES" in result_prompt:
        print("✅ 节点集成示例成功")
        print()
        print("模拟节点生成的 prompt（片段）:")
        print("-" * 70)
        lines = result_prompt.split('\n')
        for i, line in enumerate(lines[:10]):
            print(line)
        print("...")
        print("-" * 70)
    else:
        print("❌ 节点集成示例失败")

    print()
    return "BEHAVIOR RULES" in result_prompt


def main():
    """运行所有测试"""
    print()
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 20 + "行为规则系统测试" + " " * 20 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    results = []

    # 运行测试
    results.append(("基本加载", test_basic_loading()))
    results.append(("规则注入", test_injection()))
    results.append(("缓存性能", test_caching()))
    results.append(("启用禁用", test_enable_disable()))
    results.append(("集成示例", test_integration_example()))

    # 汇总结果
    print()
    print("=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    passed = 0
    failed = 0

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:12} : {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"总计: {passed + failed} 个测试")
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print()
        print("🎉 所有测试通过！行为规则系统工作正常。")
    else:
        print()
        print("⚠️  部分测试失败，请检查配置和文件。")

    print()
    print("=" * 70)
    print()

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
