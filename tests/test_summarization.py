"""Test cases for LLM summarization service."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json

from app.services.summarization import llm_summarize


@pytest.mark.asyncio
async def test_llm_summarize_success():
    """Test successful summarization."""
    # Mock OpenAI response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "summary": "这是一个关于产品规划的会议讨论",
                    "key_points": [
                        "技术架构升级完成",
                        "UI设计获得积极反馈",
                        "下月初进入开发阶段"
                    ],
                    "todos": [
                        "准备详细方案书",
                        "安排开发资源"
                    ]
                })
            )
        )
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        result = await llm_summarize("会议记录：讨论产品规划...")

        assert result["summary"] == "这是一个关于产品规划的会议讨论"
        assert len(result["key_points"]) == 3
        assert len(result["todos"]) == 2
        assert isinstance(result["key_points"], list)
        assert isinstance(result["todos"], list)

        # Verify API was called with correct parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == "deepseek-chat"
        assert call_args.kwargs["response_format"] == {"type": "json_object"}
        assert call_args.kwargs["temperature"] == 0.3


@pytest.mark.asyncio
async def test_llm_summarize_json_parse_retry():
    """Test retry on JSON parse failure."""
    # First call returns invalid JSON, second call succeeds
    mock_response_invalid = MagicMock()
    mock_response_invalid.choices = [
        MagicMock(message=MagicMock(content="This is not JSON"))
    ]

    mock_response_valid = MagicMock()
    mock_response_valid.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "summary": "测试摘要",
                    "key_points": ["要点1"],
                    "todos": []
                })
            )
        )
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        # Return invalid JSON first, then valid JSON
        mock_create.side_effect = [mock_response_invalid, mock_response_valid]

        result = await llm_summarize("测试文本", max_retries=1)

        assert result["summary"] == "测试摘要"
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_llm_summarize_json_parse_failure_exhausted():
    """Test failure after exhausting retries."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Invalid JSON"))
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            await llm_summarize("测试文本", max_retries=1)

        assert "failed after 2 attempts" in str(exc_info.value)
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_llm_summarize_empty_transcript():
    """Test error on empty transcript."""
    with pytest.raises(ValueError) as exc_info:
        await llm_summarize("")

    assert "empty or invalid" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_summarize_missing_fields():
    """Test error when response missing required fields."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "summary": "只有摘要"
                    # Missing key_points and todos
                })
            )
        )
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        with pytest.raises(ValueError) as exc_info:
            await llm_summarize("测试文本")

        assert "Missing required fields" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_summarize_invalid_types():
    """Test error when field types are incorrect."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "summary": "摘要",
                    "key_points": "应该是数组但是字符串",  # Wrong type
                    "todos": []
                })
            )
        )
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        with pytest.raises(ValueError) as exc_info:
            await llm_summarize("测试文本")

        assert "must be a list" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_summarize_empty_response():
    """Test error when API returns empty content."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=None))
    ]

    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        with pytest.raises(ValueError) as exc_info:
            await llm_summarize("测试文本")

        assert "Empty response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_summarize_api_error():
    """Test handling of API errors."""
    with patch('app.services.summarization.client.chat.completions.create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = Exception("API connection error")

        with pytest.raises(Exception) as exc_info:
            await llm_summarize("测试文本", max_retries=0)

        assert "API connection error" in str(exc_info.value)
