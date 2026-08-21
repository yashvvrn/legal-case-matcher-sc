"""
test_postprocessor.py — Unit Test Suite for OCR Text Reconstruction Pipeline.

Tests all failure modes specified in Requirement 16:
  - Fragmented intra-word space merging ("co ns tr uct i on" -> "construction")
  - Concatenated missing word space splitting ("ImplementationAgreement" -> "Implementation Agreement")
  - Real word boundary preservation ("Section 34", "UHL Power Company Ltd.")
  - Punctuation spacing ("Agreement ." -> "Agreement.", "Clause 2.2")
"""

import unittest
from text_postprocessor import (
    PositionedToken,
    ReconstructionLog,
    merge_fragmented_words,
    reconstruct_page_text,
    refine_token_text,
)


class TestOCRTextReconstruction(unittest.TestCase):

    def setUp(self):
        self.median_char_w = 10.0
        self.log = ReconstructionLog()

    def test_intra_word_fragment_construction(self):
        inp = "co ns tr uct i on"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "construction")

    def test_intra_word_fragment_referable(self):
        inp = "re fer a ble"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "referable")

    def test_intra_word_fragment_prescribed(self):
        inp = "pr es cr i bed"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "prescribed")

    def test_intra_word_fragment_disputes(self):
        inp = "di sp ut es"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "disputes")

    def test_intra_word_fragment_restoring(self):
        inp = "re st or i ng"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "restoring")

    def test_intra_word_fragment_argument(self):
        inp = "ar gu me nt"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "argument")

    def test_intra_word_fragment_completely(self):
        inp = "co mp le te ly"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "completely")

    def test_missing_space_implementation_agreement(self):
        inp = "ImplementationAgreement"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "Implementation Agreement")

    def test_missing_space_state_of_himachal_pradesh(self):
        inp = "StateofHimachalPradesh"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "State of Himachal Pradesh")

    def test_missing_space_into_the(self):
        inp = "intothe"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "into the")

    def test_preserve_section_34(self):
        inp = "Section 34"
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "Section 34")

    def test_preserve_clause_2_2(self):
        inp = "Clause 2.2"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "Clause 2.2")

    def test_preserve_uhl_power_company_ltd(self):
        inp = "UHL Power Company Ltd."
        out = merge_fragmented_words(inp)
        self.assertEqual(out, "UHL Power Company Ltd.")

    def test_punctuation_agreement_period(self):
        inp = "Agreement ."
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "Agreement.")

    def test_punctuation_company_comma(self):
        inp = "Company ,"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "Company,")

    def test_clause_4_spacing(self):
        inp = "Clause4"
        out = refine_token_text(inp, 10.0, 10.0, self.log)
        self.assertEqual(out, "Clause 4")


if __name__ == "__main__":
    unittest.main()
