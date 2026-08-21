import unittest
import os
from ocr_engine import OpenOCREngine
from paddleocr_engine import PaddleOCREngine
from ocr_comparison import OCRComparisonEngine

class TestPaddleOCRComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img_path = "/tmp/ocr_pipeline/1787297971249_2022_1_1_17_EN_rasterized_150dpi_page0001.png"

    def test_openocr_engine(self):
        engine = OpenOCREngine()
        if os.path.exists(self.img_path):
            res = engine.process_page(self.img_path, page_number=1)
            self.assertIsNotNone(res)
            self.assertEqual(res.page_number, 1)
            self.assertTrue(len(res.text) > 0)
            self.assertTrue(len(res.raw_text) > 0)
            self.assertTrue(len(res.geometry_text) > 0)

    def test_paddleocr_engine(self):
        engine = PaddleOCREngine()
        if os.path.exists(self.img_path):
            res = engine.process_page(self.img_path, page_number=1)
            self.assertIsNotNone(res)
            self.assertEqual(res.page_number, 1)
            self.assertTrue(len(res.text) > 0)
            self.assertTrue(len(res.raw_text) > 0)
            self.assertTrue(len(res.geometry_text) > 0)
            self.assertIsNotNone(res.confidence)

    def test_ocr_comparison_engine(self):
        comp_engine = OCRComparisonEngine()
        if os.path.exists(self.img_path):
            page_comp = comp_engine.compare_page(self.img_path, page_number=1)
            self.assertIsNotNone(page_comp)
            self.assertEqual(page_comp.page_number, 1)
            d = page_comp.to_dict()
            self.assertIn("openocr", d)
            self.assertIn("paddleocr", d)
            self.assertIn("raw_text", d["openocr"])
            self.assertIn("geometry_text", d["openocr"])
            self.assertIn("final_text", d["openocr"])
            self.assertIn("raw_text", d["paddleocr"])
            self.assertIn("geometry_text", d["paddleocr"])
            self.assertIn("final_text", d["paddleocr"])

            summary = comp_engine.generate_comparison_summary([page_comp])
            self.assertEqual(summary["total_pages"], 1)
            self.assertIn("openocr_metrics", summary)
            self.assertIn("paddleocr_metrics", summary)

if __name__ == "__main__":
    unittest.main()
