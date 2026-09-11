"""Test cases for mock transcription service."""
import pytest
import asyncio
from unittest.mock import patch

from app.services.transcription import mock_transcribe, TRANSCRIPTION_SAMPLES


@pytest.mark.asyncio
async def test_mock_transcribe_success():
    """Test successful transcription."""
    # Mock random to ensure success (not in 20% failure range)
    with patch('app.services.transcription.random.random', return_value=0.5):
        with patch('app.services.transcription.random.uniform', return_value=0.1):  # Fast delay
            transcript = await mock_transcribe("test.wav")

            assert transcript is not None
            assert len(transcript) > 0
            assert transcript in TRANSCRIPTION_SAMPLES


@pytest.mark.asyncio
async def test_mock_transcribe_failure():
    """Test transcription failure (20% probability)."""
    # Mock random to ensure failure (in 20% failure range)
    with patch('app.services.transcription.random.random', return_value=0.1):
        with patch('app.services.transcription.random.uniform', return_value=0.1):
            with pytest.raises(Exception) as exc_info:
                await mock_transcribe("test.wav")

            # Check that error message is one of the expected ones
            error_msg = str(exc_info.value)
            expected_errors = [
                "音频格式解码失败",
                "音频质量过低，无法识别",
                "音频时长超出限制",
                "ASR 服务暂时不可用",
                "音频文件损坏"
            ]
            assert error_msg in expected_errors


@pytest.mark.asyncio
async def test_mock_transcribe_delay():
    """Test that transcription takes time (5-15 seconds)."""
    import time

    # Use small delay for test
    with patch('app.services.transcription.random.uniform', return_value=0.5):
        with patch('app.services.transcription.random.random', return_value=0.5):
            start = time.time()
            await mock_transcribe("test.wav")
            duration = time.time() - start

            # Should take at least the mocked delay (0.5 seconds)
            assert duration >= 0.4  # Allow small margin


@pytest.mark.asyncio
async def test_mock_transcribe_returns_valid_samples():
    """Test that all returned transcripts are from predefined samples."""
    with patch('app.services.transcription.random.uniform', return_value=0.1):
        # Run multiple times to check different samples
        for _ in range(5):
            with patch('app.services.transcription.random.random', return_value=0.5):
                transcript = await mock_transcribe("test.wav")
                assert transcript in TRANSCRIPTION_SAMPLES


@pytest.mark.asyncio
async def test_transcription_samples_exist():
    """Test that transcription samples are properly defined."""
    assert len(TRANSCRIPTION_SAMPLES) >= 5
    assert len(TRANSCRIPTION_SAMPLES) <= 10

    # All samples should be non-empty strings
    for sample in TRANSCRIPTION_SAMPLES:
        assert isinstance(sample, str)
        assert len(sample) > 0
