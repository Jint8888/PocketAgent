"""
pytest 配置和共享 fixtures

用于所有测试模块的共享配置和 fixtures。
"""
import sys
import os
import pytest

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture
def sample_shared_store():
    """提供一个示例 shared store 用于节点测试"""
    return {
        "messages": [],
        "current_query": "",
        "tool_results": [],
        "memory_context": "",
        "step_count": 0,
        "max_steps": 20,
    }


@pytest.fixture
def sample_user_query():
    """提供一个示例用户查询"""
    return "今天北京天气怎么样？"


@pytest.fixture
def sample_tool_list():
    """提供一个示例工具列表"""
    return [
        {
            "name": "weather_query",
            "description": "查询天气信息",
            "parameters": {"location": "string"}
        },
        {
            "name": "search_web",
            "description": "搜索网页内容",
            "parameters": {"query": "string"}
        }
    ]
