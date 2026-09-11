"""LLM summarization service using DeepSeek API."""
import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client with DeepSeek API
client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_api_base,
    timeout=60.0,  # 60 seconds timeout
)

# System prompt for structured summarization
SUMMARIZATION_PROMPT = """你是一个专业的会议记录和对话分析助手。请分析以下转写文本，提取关键信息。

请严格按照以下 JSON 格式返回结果：
{
  "summary": "简明扼要的总结（100-200字）",
  "key_points": ["要点1", "要点2", "要点3"],
  "todos": ["待办事项1", "待办事项2"]
}

要求：
1. summary: 概括对话的主要内容和目的
2. key_points: 提取 3-5 个关键讨论点或决策
3. todos: 识别明确提到的待办事项、行动项或下一步计划（如果没有则返回空数组）

必须返回有效的 JSON 格式，不要包含任何其他文本。"""


async def llm_summarize(transcript: str, max_retries: int = 1) -> Dict[str, Any]:
    """
    Generate structured summary from transcript using DeepSeek LLM.

    Args:
        transcript: The transcribed text to summarize
        max_retries: Maximum number of retries on JSON parse failure (default: 1)

    Returns:
        Dictionary with summary, key_points, and todos

    Raises:
        Exception: If API call fails or JSON parsing fails after retries
    """
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty or invalid")

    attempt = 0
    last_error = None

    while attempt <= max_retries:
        try:
            logger.info(f"LLM summarization attempt {attempt + 1}/{max_retries + 1}")

            # Call DeepSeek API
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SUMMARIZATION_PROMPT},
                    {"role": "user", "content": f"转写文本：\n\n{transcript}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1000,
            )

            # Extract content
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")

            # Parse JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed on attempt {attempt + 1}: {e}")
                logger.debug(f"Raw content: {content}")
                last_error = e
                attempt += 1
                continue

            # Validate structure
            required_fields = ["summary", "key_points", "todos"]
            missing_fields = [f for f in required_fields if f not in result]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Validate types
            if not isinstance(result["summary"], str):
                raise ValueError("summary must be a string")
            if not isinstance(result["key_points"], list):
                raise ValueError("key_points must be a list")
            if not isinstance(result["todos"], list):
                raise ValueError("todos must be a list")

            logger.info(
                f"LLM summarization completed: "
                f"{len(result['key_points'])} key points, "
                f"{len(result['todos'])} todos"
            )

            return result

        except json.JSONDecodeError as e:
            # Already handled above
            last_error = e
            attempt += 1
            continue

        except Exception as e:
            # API errors, network errors, etc.
            logger.error(f"LLM summarization failed on attempt {attempt + 1}: {e}")
            if attempt >= max_retries:
                raise
            last_error = e
            attempt += 1

    # If we get here, all retries failed
    error_msg = f"LLM summarization failed after {max_retries + 1} attempts"
    if last_error:
        error_msg += f": {str(last_error)}"
    raise Exception(error_msg)
