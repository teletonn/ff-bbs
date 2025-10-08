import unittest
from modules.system import messageChunker

class TestMessageChunker(unittest.TestCase):

    def test_short_message(self):
        message = "This is a short message."
        chunks = messageChunker(message, 160)
        self.assertEqual(chunks, ["This is a short message."])

    def test_exact_multiple_message(self):
        message = "a" * 320
        chunks = messageChunker(message, 160)
        self.assertEqual(chunks, ["a" * 160, "a" * 160])

    def test_long_message(self):
        message = "a" * 400
        chunks = messageChunker(message, 160)
        self.assertEqual(chunks, ["a" * 160, "a" * 160, "a" * 80])

    def test_empty_message(self):
        message = ""
        chunks = messageChunker(message, 160)
        self.assertEqual(chunks, [])

    def test_all_chunks_under_max_size(self):
        message = "a" * 1000
        chunk_size = 160
        chunks = messageChunker(message, chunk_size)
        for chunk in chunks:
            self.assertTrue(len(chunk) <= chunk_size)

if __name__ == '__main__':
    unittest.main()