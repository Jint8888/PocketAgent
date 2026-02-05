"""
LLM 调用工具模块

提供同步和异步两种 LLM 调用方式，推荐使用异步版本。
"""

from litellm import completion, acompletion
import os
import asyncio
from typing import List, Dict, Optional
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 屏蔽 Pydantic 的序列化警告（常见于使用自定义 OpenAI 接口时）
import warnings
warnings.filterwarnings("ignore", module="pydantic")


# ============================================================================
# 配置常量
# ============================================================================

DEFAULT_MODEL = "deepseek/deepseek-chat"
DEFAULT_FAST_MODEL = "gemini/gemini-1.5-flash"  # 快速模型（用于简单任务）
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096  # 默认最大响应 token 数
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # 指数退避基数（秒）


# ============================================================================
# LLM 调用函数
# ============================================================================

def call_llm(messages: List[Dict]) -> str:
    """
    【同步版本】调用 LLM

    警告：此函数会阻塞事件循环，在异步代码中请使用 call_llm_async()

    Args:
        messages: 消息列表

    Returns:
        LLM 响应文本

    Raises:
        RuntimeError: LLM 调用失败时抛出
    """
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    temperature = float(os.environ.get("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                import time
                delay = RETRY_DELAY_BASE ** attempt
                print(f"[WARN] LLM call failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"       Retrying in {delay}s...")
                time.sleep(delay)

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")


async def call_llm_async(
    messages: List[Dict],
    model: Optional[str] = None,
    use_fast: bool = False,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> str:
    """
    【异步版本】调用 LLM (推荐)

    使用 litellm.acompletion() 实现真正的异步调用，
    不会阻塞事件循环，可与其他异步任务并发执行。
    包含自动重试机制（指数退避）。

    Args:
        messages: 消息列表
        model: 指定使用的模型（优先级最高）
        use_fast: 是否使用快速模型（适用于简单任务，如格式转换、参数解析）
        temperature: 生成温度（可选，默认使用环境变量）
        max_tokens: 最大 token 数（可选，默认使用环境变量）

    Returns:
        LLM 响应文本

    Raises:
        RuntimeError: 多次重试后仍失败时抛出

    模型选择优先级：
        1. 显式指定的 model 参数
        2. use_fast=True 时使用快速模型（LLM_FAST_MODEL 环境变量）
        3. 环境变量 LLM_MODEL
        4. 默认模型
    """
    # 模型选择
    if model is None:
        if use_fast:
            model = os.environ.get("LLM_FAST_MODEL", DEFAULT_FAST_MODEL)
        else:
            model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)

    # 参数配置
    if temperature is None:
        temperature = float(os.environ.get("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    if max_tokens is None:
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE ** attempt
                print(f"[WARN] LLM call failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"       Retrying in {delay}s...")
                await asyncio.sleep(delay)

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")


async def async_input(prompt: str) -> str:
    """
    【异步】获取用户输入

    使用 run_in_executor 将阻塞的 input() 放到线程池执行，
    避免阻塞事件循环。
    """
    loop = asyncio.get_running_loop()
    return (await loop.run_in_executor(None, input, prompt)).strip()


