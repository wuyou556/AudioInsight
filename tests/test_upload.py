"""Test cases for recording upload API."""
import os
import pytest
from io import BytesIO


@pytest.mark.asyncio
async def test_upload_recording_success(client, sample_audio_file):
    """Test successful audio file upload."""
    files = {"file": ("test.wav", BytesIO(sample_audio_file), "audio/wav")}

    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 201
    data = response.json()

    assert "recording_id" in data
    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["is_duplicate"] is False


@pytest.mark.asyncio
async def test_upload_recording_mp3(client, sample_audio_file):
    """Test upload with MP3 file."""
    files = {"file": ("test.mp3", BytesIO(sample_audio_file), "audio/mpeg")}

    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_recording_invalid_extension(client, sample_audio_file):
    """Test upload with invalid file extension."""
    files = {"file": ("test.txt", BytesIO(sample_audio_file), "text/plain")}

    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_FILE_EXTENSION"
    assert "allowed_extensions" in data["error"]["details"]


@pytest.mark.asyncio
async def test_upload_recording_file_too_large(client):
    """Test upload with file exceeding size limit."""
    # Create a file larger than 50MB
    large_file = b"X" * (51 * 1024 * 1024)
    files = {"file": ("large.wav", BytesIO(large_file), "audio/wav")}

    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "FILE_TOO_LARGE"
    assert "file_size" in data["error"]["details"]
    assert "max_size" in data["error"]["details"]


@pytest.mark.asyncio
async def test_upload_all_supported_formats(client, sample_audio_file):
    """Test all supported audio formats."""
    formats = [
        ("test.wav", "audio/wav"),
        ("test.mp3", "audio/mpeg"),
        ("test.m4a", "audio/mp4"),
        ("test.aac", "audio/aac"),
    ]

    for filename, mime_type in formats:
        files = {"file": (filename, BytesIO(sample_audio_file), mime_type)}
        response = await client.post("/v1/recordings", files=files)

        assert response.status_code == 201, f"Failed for {filename}"
        data = response.json()
        assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_creates_file_on_disk(client, sample_audio_file, tmp_path, monkeypatch):
    """Test that uploaded file is saved to disk."""
    # Override upload directory
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("app.api.recordings.settings.upload_dir", str(upload_dir))

    files = {"file": ("test.wav", BytesIO(sample_audio_file), "audio/wav")}
    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 201
    data = response.json()

    # Check that file was created
    assert upload_dir.exists()
    files_in_dir = list(upload_dir.glob("*.wav"))
    assert len(files_in_dir) == 1

    # Check file content
    saved_file = files_in_dir[0]
    with open(saved_file, "rb") as f:
        content = f.read()
        assert content == sample_audio_file


@pytest.mark.asyncio
async def test_error_response_format(client, sample_audio_file):
    """Test that error responses follow standard format."""
    files = {"file": ("test.txt", BytesIO(sample_audio_file), "text/plain")}

    response = await client.post("/v1/recordings", files=files)

    assert response.status_code == 400
    data = response.json()

    # Verify error structure
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert "details" in data["error"]
    assert isinstance(data["error"]["details"], dict)
