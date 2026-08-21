import unittest
from backend.services.text_cleaner import clean_extracted_text
from backend.services.chunker import chunk_text

class TestBackendServices(unittest.TestCase):
    def test_text_cleaner_broken_hyphens(self):
        raw = "The peti-\ntioner filed an appeal."
        cleaned = clean_extracted_text(raw)
        self.assertEqual(cleaned, "The petitioner filed an appeal.")

    def test_text_cleaner_excessive_whitespace(self):
        raw = "High    Court  of   Judicature\n\n\n\n\nPage 1"
        cleaned = clean_extracted_text(raw)
        self.assertIn("High Court of Judicature", cleaned)
        self.assertNotIn("\n\n\n", cleaned)

    def test_chunker_short_text(self):
        text = "[Page 1]\nShort judgement text."
        chunks = chunk_text(text, chunk_size=6000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["total_chunks"], 1)

    def test_chunker_long_text(self):
        paragraph = "[Page 1]\n" + ("Legal paragraph text sample. " * 50) + "\n\n"
        paragraph_2 = "[Page 2]\n" + ("Second section paragraph sample. " * 50)
        full_text = paragraph + paragraph_2
        
        chunks = chunk_text(full_text, chunk_size=500, chunk_overlap=100)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_index"], 1)
        self.assertEqual(chunks[0]["total_chunks"], len(chunks))

if __name__ == "__main__":
    unittest.main()
