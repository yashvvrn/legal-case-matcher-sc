"""
test_extended_postprocessor.py — Comprehensive Test Suite for all 17 Requirements.
"""

import unittest
from text_postprocessor import (
    PositionedToken,
    ReconstructionLog,
    is_noise_token,
    merge_fragmented_words,
    reconstruct_page_text,
    refine_token_text,
)


class TestExtendedOCRPostprocessor(unittest.TestCase):

    def setUp(self):
        self.log = ReconstructionLog()

    def test_intra_word_spaces_all_examples(self):
        cases = {
            "co ns tr uct i on": "construction",
            "re fer a ble": "referable",
            "pr es cr i bed": "prescribed",
            "co mp le te ly": "completely",
            "di sp ut es": "disputes",
            "re st or i ng": "restoring",
            "ar gu me nt": "argument",
            "re qu i red": "required",
            "co mp ou nd": "compound",
            "pr inc i pal": "principal",
            "ar bi tr al": "arbitral",
        }
        for inp, expected in cases.items():
            out = merge_fragmented_words(inp, self.log)
            self.assertEqual(out, expected, f"Failed on '{inp}'")

    def test_missing_word_spaces_all_examples(self):
        cases = {
            "ImplementationAgreement": "Implementation Agreement",
            "intothe": "into the",
            "StateofHimachalPradesh": "State of Himachal Pradesh",
            "Clause4": "Clause 4",
        }
        for inp, expected in cases.items():
            out = refine_token_text(inp, 10.0, 10.0, self.log)
            self.assertEqual(out, expected, f"Failed on '{inp}'")

    def test_preserve_real_word_boundaries(self):
        cases = [
            "the Court",
            "UHL Power Company",
            "UHL Power Company Ltd.",
            "Section 34",
            "Clause 2.2",
            "Section 34 (2)(b)(ii)",
        ]
        for c in cases:
            out = merge_fragmented_words(c, self.log)
            self.assertEqual(out, c, f"Preservation failed for '{c}'")

    def test_punctuation_normalization(self):
        cases = {
            "Agreement .": "Agreement.",
            "Company ,": "Company,",
        }
        for inp, expected in cases.items():
            out = refine_token_text(inp, 10.0, 10.0, self.log)
            self.assertEqual(out, expected, f"Failed on '{inp}'")

    def test_artifact_noise_removal(self):
        artifacts = ["TFP", "上", "DB"]
        for art in artifacts:
            tok = PositionedToken(art, 0.9, 2500, 100, 2550, 120)
            self.assertTrue(is_noise_token(tok, self.log), f"Artifact '{art}' should be removed")

    def test_valid_legal_markers_not_removed(self):
        valid = ["§", "¶", "No.", "s.", "Art.", "Cl."]
        for val in valid:
            tok = PositionedToken(val, 0.9, 100, 100, 120, 120)
            self.assertFalse(is_noise_token(tok, self.log), f"Marker '{val}' should be kept")

    def test_debug_log_tracking(self):
        log = ReconstructionLog()
        reconstruct_page_text([
            PositionedToken("co ns tr uct i on", 0.95, 100, 100, 200, 120),
            PositionedToken("ImplementationAgreement", 0.95, 210, 100, 400, 120),
        ], debug_mode=True, log=log)
        self.assertTrue(len(log.tokens_merged) > 0 or len(log.spaces_inserted) > 0)
        self.assertIn("median_char_w", log.thresholds_used)


if __name__ == "__main__":
    unittest.main()
