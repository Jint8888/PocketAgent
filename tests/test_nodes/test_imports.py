"""
节点模块导入兼容性测试 (TDD RED Phase)

验证重构后的 nodes 模块保持向后兼容的导入方式。

运行方式:
    pytest tests/test_nodes/test_imports.py -v
"""
import pytest


class TestNodesImportCompatibility:
    """测试 nodes 模块导入兼容性"""

    def test_import_all_nodes_from_package(self):
        """测试从 nodes 包导入所有节点类"""
        from nodes import (
            InputNode,
            PlanningNode,
            RetrieveNode,
            DecideNode,
            ToolNode,
            ThinkNode,
            AnswerNode,
            EmbedNode,
            SupervisorNode,
        )

        # 验证所有类都存在
        assert InputNode is not None
        assert PlanningNode is not None
        assert RetrieveNode is not None
        assert DecideNode is not None
        assert ToolNode is not None
        assert ThinkNode is not None
        assert AnswerNode is not None
        assert EmbedNode is not None
        assert SupervisorNode is not None

    def test_import_action_constants(self):
        """测试导入 Action 常量类"""
        from nodes import Action

        # 验证常量存在
        assert Action.TOOL == "tool"
        assert Action.THINK == "think"
        assert Action.ANSWER == "answer"
        assert Action.INPUT == "input"
        assert Action.PLANNING == "planning"
        assert Action.RETRIEVE == "retrieve"
        assert Action.DECIDE == "decide"
        assert Action.EMBED == "embed"
        assert Action.SUPERVISOR == "supervisor"

    def test_import_utility_functions(self):
        """测试导入辅助函数"""
        from nodes import parse_yaml_response

        # 验证函数存在且可调用
        assert callable(parse_yaml_response)

    def test_nodes_inherit_async_node(self):
        """测试所有节点继承自 AsyncNode"""
        from nodes import (
            InputNode,
            PlanningNode,
            RetrieveNode,
            DecideNode,
            ToolNode,
            ThinkNode,
            AnswerNode,
            EmbedNode,
            SupervisorNode,
        )
        from pocketflow import AsyncNode

        node_classes = [
            InputNode,
            PlanningNode,
            RetrieveNode,
            DecideNode,
            ToolNode,
            ThinkNode,
            AnswerNode,
            EmbedNode,
            SupervisorNode,
        ]

        for node_class in node_classes:
            assert issubclass(node_class, AsyncNode), \
                f"{node_class.__name__} should inherit from AsyncNode"


class TestNodeInstantiation:
    """测试节点实例化"""

    def test_input_node_instantiation(self):
        """测试 InputNode 可以正常实例化"""
        from nodes import InputNode
        node = InputNode()
        assert node is not None

    def test_planning_node_instantiation(self):
        """测试 PlanningNode 可以正常实例化"""
        from nodes import PlanningNode
        node = PlanningNode()
        assert node is not None

    def test_retrieve_node_instantiation(self):
        """测试 RetrieveNode 可以正常实例化"""
        from nodes import RetrieveNode
        node = RetrieveNode()
        assert node is not None

    def test_decide_node_instantiation(self):
        """测试 DecideNode 可以正常实例化"""
        from nodes import DecideNode
        node = DecideNode()
        assert node is not None

    def test_tool_node_instantiation(self):
        """测试 ToolNode 可以正常实例化"""
        from nodes import ToolNode
        node = ToolNode()
        assert node is not None

    def test_think_node_instantiation(self):
        """测试 ThinkNode 可以正常实例化"""
        from nodes import ThinkNode
        node = ThinkNode()
        assert node is not None

    def test_answer_node_instantiation(self):
        """测试 AnswerNode 可以正常实例化"""
        from nodes import AnswerNode
        node = AnswerNode()
        assert node is not None

    def test_embed_node_instantiation(self):
        """测试 EmbedNode 可以正常实例化"""
        from nodes import EmbedNode
        node = EmbedNode()
        assert node is not None

    def test_supervisor_node_instantiation(self):
        """测试 SupervisorNode 可以正常实例化"""
        from nodes import SupervisorNode
        node = SupervisorNode()
        assert node is not None


class TestYamlParsing:
    """测试 YAML 解析辅助函数"""

    def test_parse_yaml_simple(self):
        """测试解析简单 YAML 响应"""
        from nodes import parse_yaml_response

        response = """```yaml
action: tool
tool_name: weather_query
parameters:
  location: 北京
```"""
        result = parse_yaml_response(response)

        assert result["action"] == "tool"
        assert result["tool_name"] == "weather_query"
        assert result["parameters"]["location"] == "北京"

    def test_parse_yaml_answer(self):
        """测试解析包含答案的 YAML 响应"""
        from nodes import parse_yaml_response

        response = """```yaml
action: answer
answer: |
  今天北京天气晴朗，温度 25°C。
  建议穿着轻便衣物。
```"""
        result = parse_yaml_response(response)

        assert result["action"] == "answer"
        assert "晴朗" in result["answer"]

    def test_parse_yaml_invalid_raises_error(self):
        """测试无效 YAML 应该抛出 ValueError"""
        from nodes import parse_yaml_response

        invalid_response = "this is not yaml at all { broken"

        with pytest.raises(ValueError):
            parse_yaml_response(invalid_response)
