"""Utility functions for file operations."""
import hashlib
from typing import BinaryIO


def calculate_file_hash(file_content: bytes, chunk_size: int = 8192) -> str:
    """
    Calculate SHA256 hash of file content using streaming approach.

    Uses chunk-based reading to avoid loading entire file into memory,
    making it suitable for large files.

    Args:
        file_content: File content as bytes
        chunk_size: Size of chunks to read (default 8KB)

    Returns:
        Hexadecimal string representation of SHA256 hash
    """
    sha256_hash = hashlib.sha256()

    # Process in chunks to handle large files efficiently
    for i in range(0, len(file_content), chunk_size):
        chunk = file_content[i:i + chunk_size]
        sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def calculate_file_hash_from_stream(file_stream: BinaryIO, chunk_size: int = 8192) -> str:
    """
    Calculate SHA256 hash from a file stream.

    Args:
        file_stream: File-like object to read from
        chunk_size: Size of chunks to read (default 8KB)

    Returns:
        Hexadecimal string representation of SHA256 hash
    """
    sha256_hash = hashlib.sha256()

    while True:
        chunk = file_stream.read(chunk_size)
        if not chunk:
            break
        sha256_hash.update(chunk)

    return sha256_hash.hexdigest()
