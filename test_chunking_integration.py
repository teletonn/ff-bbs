#!/usr/bin/env python3
"""
Test script for the new chunking mechanism in message_processor.py
"""
import sys
import os
import asyncio
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules', 'meshgram_integration'))

from message_processor import MessageProcessor

async def test_chunk_message():
    """Test the chunk_message method directly"""
    # Create a minimal processor instance for testing
    class MockConfig:
        def get(self, key, default=None):
            return default

    class MockNodeManager:
        pass

    class MockMeshtastic:
        def __init__(self):
            self.node_manager = MockNodeManager()

    class MockTelegram:
        pass

    config = MockConfig()
    meshtastic = MockMeshtastic()
    telegram = MockTelegram()

    # Create processor instance
    processor = MessageProcessor(meshtastic, telegram, config)

    # Test cases
    test_cases = [
        # Short message (should not be chunked)
        ("Hello world", ["Hello world"]),

        # Message exactly at threshold (110 chars)
        ("x" * 110, ["x" * 110]),

        # Message over threshold (should be chunked)
        ("x" * 200, ["1/2" + "x" * 110, "2/2" + "x" * 90]),

        # Very long message (should be truncated to 1000 chars and chunked)
        ("x" * 1200, None),  # 1000 chars / ~110 chars per chunk = ~10 chunks

        # Message with spaces (should break at word boundaries)
        ("This is a very long message that should be split into multiple chunks for testing purposes.",
         None)  # We'll check structure
    ]

    print("Testing chunk_message method:")
    for i, (message, expected) in enumerate(test_cases):
        print(f"\nTest case {i+1}: Message length = {len(message)}")
        chunks = processor.chunk_message(message)

        print(f"Number of chunks: {len(chunks)}")
        for j, chunk in enumerate(chunks):
            print(f"  Chunk {j+1}: {chunk[:50]}{'...' if len(chunk) > 50 else ''} (length: {len(chunk)})")

        # Basic validation
        if expected:
            assert len(chunks) == len(expected), f"Expected {len(expected)} chunks, got {len(chunks)}"

        # Check that no chunk exceeds 110 + counter length
        for chunk in chunks:
            assert len(chunk) <= 120, f"Chunk too long: {len(chunk)} > 120"

        # Check total length doesn't exceed 1000
        total_content = "".join(chunks)
        if len(chunks) > 1:
            # Remove counters for content check
            import re
            content_no_counters = re.sub(r'\d+/\d+ ', '', total_content)
            assert len(content_no_counters) <= 1000, f"Total content too long: {len(content_no_counters)} > 1000"
        else:
            assert len(total_content) <= 1000, f"Total content too long: {len(total_content)} > 1000"

    print("\n✅ All chunk_message tests passed!")

async def main():
    await test_chunk_message()

if __name__ == "__main__":
    asyncio.run(main())