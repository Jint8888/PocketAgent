"""
统一日志配置模块

提供项目级别的日志配置，支持：
- 多级别日志（DEBUG, INFO, WARNING, ERROR）
- 文件分类（主日志、错误日志、MCP日志）
- 日志轮转（防止文件过大）
- 格式统一
- 易于调试

作者: AI Assistant
版本: v1.0
日期: 2024-01-23
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path


# ============================================================================
# 配置常量
# ============================================================================

# 日志目录
LOG_DIR = Path(__file__).parent / "logs"

# 日志文件名
MAIN_LOG_FILE = "agent.log"          # 主日志
ERROR_LOG_FILE = "error.log"         # 错误日志
DEBUG_LOG_FILE = "debug.log"         # 调试日志
MCP_LOG_FILE = "mcp_manager.log"     # MCP工具日志（已有）

# 日志级别（可通过环境变量覆盖）
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================================
# 日志开关（全局控制）
# ============================================================================

# 日志开关状态（默认开启）
_LOGGING_ENABLED = True

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# 日志轮转配置
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5              # 保留5个备份


# ============================================================================
# 日志开关控制函数
# ============================================================================

def enable_logging():
    """启用日志记录"""
    global _LOGGING_ENABLED
    _LOGGING_ENABLED = True


def disable_logging():
    """禁用日志记录"""
    global _LOGGING_ENABLED
    _LOGGING_ENABLED = False


def is_logging_enabled() -> bool:
    """检查日志是否启用"""
    return _LOGGING_ENABLED


# ============================================================================
# 日志配置函数
# ============================================================================

def setup_logging(
    logger_name: str = "agent",
    level: str = None,
    console_output: bool = True,
    file_output: bool = True
) -> logging.Logger:
    """
    配置并返回日志记录器

    Args:
        logger_name: 日志记录器名称
        level: 日志级别（DEBUG, INFO, WARNING, ERROR）
        console_output: 是否输出到控制台
        file_output: 是否输出到文件

    Returns:
        配置好的日志记录器
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(exist_ok=True)

    # 创建logger
    logger = logging.getLogger(logger_name)

    # 设置级别
    log_level = level or LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper()))

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # ========================================
    # 文件Handler - 主日志（所有级别）
    # ========================================
    if file_output:
        main_handler = RotatingFileHandler(
            LOG_DIR / MAIN_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(main_handler)

    # ========================================
    # 文件Handler - 错误日志（ERROR及以上）
    # ========================================
    if file_output:
        error_handler = RotatingFileHandler(
            LOG_DIR / ERROR_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(error_handler)

    # ========================================
    # 文件Handler - 调试日志（DEBUG级别）
    # ========================================
    if file_output and log_level == "DEBUG":
        debug_handler = RotatingFileHandler(
            LOG_DIR / DEBUG_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(debug_handler)

    # ========================================
    # 控制台Handler（用户可见）
    # ========================================
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(SIMPLE_FORMAT))
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器（简便方法）

    Args:
        name: 日志记录器名称（通常使用 __name__）

    Returns:
        日志记录器
    """
    logger_name = name or "agent"

    # 如果已配置，直接返回
    existing_logger = logging.getLogger(logger_name)
    if existing_logger.handlers:
        return existing_logger

    # 否则配置后返回
    return setup_logging(logger_name)


def log_session_start():
    """记录会话开始"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.info("=" * 80)
    logger.info(f"Agent Session Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)


def log_session_end():
    """记录会话结束"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.info("=" * 80)
    logger.info(f"Agent Session Ended - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)


def log_user_input(user_input: str):
    """记录用户输入"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.info(f"USER INPUT: {user_input}")


def log_agent_response(response: str):
    """记录Agent响应"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    # 增加截断长度到 1000 字符，只在超长时截断
    if len(response) > 1000:
        logger.info(f"AGENT RESPONSE: {response[:1000]}...")
    else:
        logger.info(f"AGENT RESPONSE: {response}")


def log_tool_call(tool_name: str, params: dict):
    """记录工具调用"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.info(f"TOOL CALL: {tool_name}")
    logger.debug(f"TOOL PARAMS: {params}")


def log_tool_result(tool_name: str, success: bool, result_preview: str = None):
    """记录工具结果"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"TOOL RESULT: {tool_name} - {status}")
    if result_preview:
        logger.debug(f"RESULT PREVIEW: {result_preview[:200]}...")


def log_decision(action: str, reason: str):
    """记录决策"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.info(f"DECISION: {action}")
    logger.debug(f"REASON: {reason}")


def log_error(error_msg: str, exc_info: bool = True):
    """记录错误"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.error(error_msg, exc_info=exc_info)


def log_node_enter(node_name: str):
    """记录进入节点"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    logger.debug(f">>> ENTER NODE: {node_name}")


def log_node_exit(node_name: str, next_action: str = None):
    """记录退出节点"""
    if not _LOGGING_ENABLED:
        return
    logger = get_logger("agent")
    msg = f"<<< EXIT NODE: {node_name}"
    if next_action:
        msg += f" -> {next_action}"
    logger.debug(msg)


# ============================================================================
# 日志清理工具
# ============================================================================

def clean_old_logs(days: int = 7):
    """
    清理旧日志文件

    Args:
        days: 保留最近N天的日志
    """
    import time

    logger = get_logger("agent")
    cutoff_time = time.time() - (days * 86400)

    cleaned_count = 0
    for log_file in LOG_DIR.glob("*.log*"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
                cleaned_count += 1
                logger.info(f"Cleaned old log: {log_file.name}")
            except Exception as e:
                logger.warning(f"Failed to clean {log_file.name}: {e}")

    if cleaned_count > 0:
        logger.info(f"Cleaned {cleaned_count} old log files")


def get_log_summary():
    """
    获取日志文件摘要信息

    Returns:
        日志文件信息字典
    """
    summary = {}

    for log_file in LOG_DIR.glob("*.log"):
        stat = log_file.stat()
        summary[log_file.name] = {
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "lines": sum(1 for _ in open(log_file, 'r', encoding='utf-8', errors='ignore'))
        }

    return summary


# ============================================================================
# 初始化（模块导入时自动执行）
# ============================================================================

# 确保日志目录存在
LOG_DIR.mkdir(exist_ok=True)

# 配置根日志记录器
# setup_logging() 会在第一次调用 get_logger() 时执行


if __name__ == "__main__":
    """测试日志配置"""
    print("=" * 80)
    print("日志系统测试")
    print("=" * 80)
    print()

    # 测试基本日志
    logger = setup_logging("test", level="DEBUG")

    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")

    print()

    # 测试便捷函数
    log_session_start()
    log_user_input("测试用户输入")
    log_tool_call("test_tool", {"param": "value"})
    log_tool_result("test_tool", True, "测试结果")
    log_decision("tool", "需要调用工具")
    log_session_end()

    print()

    # 显示日志摘要
    print("日志文件摘要:")
    print("-" * 80)
    summary = get_log_summary()
    for filename, info in summary.items():
        print(f"{filename:20} | {info['size_mb']:>8} MB | {info['lines']:>8} lines | {info['modified']}")

    print()
    print("=" * 80)
    print(f"日志文件位置: {LOG_DIR}")
    print("=" * 80)
