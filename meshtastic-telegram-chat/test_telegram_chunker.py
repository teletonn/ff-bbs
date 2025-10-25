import unittest
import sys
import os

# Add the current directory to the path to import the function
sys.path.insert(0, os.path.dirname(__file__))

from meshchat_telegram import telegram_message_chunker

class TestTelegramMessageChunker(unittest.TestCase):

    def test_short_message_single_chunk(self):
        message = "This is a short message."
        chunks = telegram_message_chunker(message)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], message)
        self.assertTrue(len(chunks[0]) <= 230)

    def test_long_message_chunked_with_counters(self):
        message = "This is a very long message that should be chunked into multiple parts. " * 10  # Repeat to make it long
        chunks = telegram_message_chunker(message)
        self.assertGreater(len(chunks), 1)
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            self.assertTrue(len(chunk) <= 230)
            if total > 1:
                expected_prefix = f"({i+1}/{total}) "
                self.assertTrue(chunk.startswith(expected_prefix))

    def test_total_length_truncation(self):
        message = "a" * 1200  # Over 1000 chars
        chunks = telegram_message_chunker(message)
        # The message is truncated to 1000 chars first
        truncated_message = message[:1000]
        # Then chunked, so total content should be 1000 chars
        # But with counters, the chunks are longer
        # Check that the total length of chunks is reasonable
        total_chunk_length = sum(len(chunk) for chunk in chunks)
        self.assertLessEqual(total_chunk_length, 1000 + (len(chunks) * 10))  # Allow for counters
        # Verify the content without counters is 1000
        content = "".join(chunks)
        # Remove counters like (1/2)
        import re
        content_no_counters = re.sub(r'\(\d+/\d+\) ', '', content)
        self.assertEqual(len(content_no_counters), 1000)

    def test_chunks_not_exceed_230(self):
        message = "This is a test message that is long enough to be chunked. " * 20
        chunks = telegram_message_chunker(message)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 230)

    def test_empty_message(self):
        message = ""
        chunks = telegram_message_chunker(message)
        self.assertEqual(chunks, [""])  # Function returns single empty chunk

    def test_very_long_word(self):
        message = "a" * 500  # No spaces, very long word
        chunks = telegram_message_chunker(message)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 230)
        # Should cut at 220 for chunks without spaces

    def test_message_over_1000_chars(self):
        message = "a" * 1200
        chunks = telegram_message_chunker(message)
        # Should be truncated to 1000 chars
        reconstructed = "".join(chunk.lstrip("0123456789()/ ") for chunk in chunks)  # Remove counters and spaces
        self.assertEqual(len(reconstructed), 1000)

    def test_single_chunk_no_counter(self):
        message = "Short message under 230 chars."
        chunks = telegram_message_chunker(message)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], message)
        self.assertFalse(chunks[0].startswith("("))  # No counter

    def test_multiple_chunks_with_counters(self):
        message = "Word " * 100  # Many words to force chunking
        chunks = telegram_message_chunker(message)
        if len(chunks) > 1:
            total = len(chunks)
            for i, chunk in enumerate(chunks):
                self.assertTrue(chunk.startswith(f"({i+1}/{total}) "))

if __name__ == '__main__':
    unittest.main()