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
DEFAULT_TEMPERATURE = 0.7
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

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = completion(
                model=model,
                messages=messages,
                temperature=temperature
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


async def call_llm_async(messages: List[Dict]) -> str:
    """
    【异步版本】调用 LLM (推荐)

    使用 litellm.acompletion() 实现真正的异步调用，
    不会阻塞事件循环，可与其他异步任务并发执行。
    包含自动重试机制（指数退避）。

    Args:
        messages: 消息列表

    Returns:
        LLM 响应文本

    Raises:
        RuntimeError: 多次重试后仍失败时抛出
    """
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    temperature = float(os.environ.get("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature
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


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    # 测试同步版本
    try:
        call_llm([{"role": "user", "content": "hi"}])
        print("[OK] LLM sync connection works")
    except Exception as e:
        print(f"[ERROR] LLM sync test failed: {e}")

    # 测试异步版本
    async def test_async():
        try:
            await call_llm_async([{"role": "user", "content": "hi"}])
            print("[OK] LLM async connection works")
        except Exception as e:
            print(f"[ERROR] LLM async test failed: {e}")

    asyncio.run(test_async())
