import unittest
from ocr_engine import RecognizedToken, BoundingBox
from paddle_postprocessor import process_paddle_page, normalize_paddle_line_text

class TestPaddlePostprocessor(unittest.TestCase):
    def test_required_spacing_cases(self):
        cases = [
            ("CivilAppealNo.10341of2011", "Civil Appeal No. 10341 of 2011"),
            ("Section34oftheArbitrationAct", "Section 34 of the Arbitration Act"),
            ("EnvironmentandForests", "Environment and Forests"),
            ("StateofHimachalPradesh", "State of Himachal Pradesh"),
            ("ImplementationAgreement", "Implementation Agreement"),
            ("the Court", "the Court"),
            ("UHL Power Company Ltd.", "UHL Power Company Ltd."),
            ("Section 34", "Section 34"),
            ("Clause 2.2", "Clause 2.2"),
        ]
        for inp, expected in cases:
            out, _ = normalize_paddle_line_text(inp)
            self.assertEqual(out, expected, f"Failed on '{inp}' -> Got '{out}', Expected '{expected}'")

    def test_required_character_corrections(self):
        cases = [
            ("1Oth February, 1992", "10th February, 1992"),
            ("lOth February", "10th February"),
            ("O5th January", "05th January"),
            ("2oo5", "2005"),
            ("1oo MwW", "100 MW"),
            ("mav interfere on merits", "may interfere on merits"),
        ]
        for inp, expected in cases:
            out, _ = normalize_paddle_line_text(inp)
            self.assertEqual(out, expected, f"Failed on '{inp}' -> Got '{out}', Expected '{expected}'")

    def test_page_postprocessing(self):
        tokens = [
            RecognizedToken(text="CivilAppealNo.10341of2011", score=0.98, bbox=BoundingBox(100, 100, 400, 130)),
            RecognizedToken(text="StateofHimachalPradesh", score=0.99, bbox=BoundingBox(100, 140, 400, 170)),
            RecognizedToken(text="TFP", score=0.95, bbox=BoundingBox(10, 10, 50, 30)),
        ]
        res = process_paddle_page(tokens, page_number=1, page_height=1000.0)
        self.assertIn("Civil Appeal No. 10341 of 2011", res.text)
        self.assertIn("State of Himachal Pradesh", res.text)
        self.assertNotIn("TFP", res.text)

if __name__ == "__main__":
    unittest.main()
