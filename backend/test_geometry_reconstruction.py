"""
test_geometry_reconstruction.py — Unit Tests for Geometry-First Token Reconstruction.
"""

import unittest
from text_postprocessor import PositionedToken, ReconstructionLog, reconstruct_page_text


class TestGeometryReconstruction(unittest.TestCase):

    def test_geometry_fragment_clustering_completely(self):
        # Tokens spaced with gap = 2px (ratio ~0.2 < 0.45 threshold) -> Must merge into 'completely'
        tokens = [
            PositionedToken("co", 0.95, 100, 100, 120, 120),
            PositionedToken("mp", 0.95, 122, 100, 142, 120),
            PositionedToken("le", 0.95, 144, 100, 164, 120),
            PositionedToken("te", 0.95, 166, 100, 186, 120),
            PositionedToken("ly", 0.95, 188, 100, 208, 120),
        ]
        log = ReconstructionLog()
        out = reconstruct_page_text(tokens, debug_mode=True, log=log)
        self.assertEqual(out, "completely")

    def test_geometry_fragment_clustering_prescribed(self):
        tokens = [
            PositionedToken("pr", 0.95, 100, 100, 120, 120),
            PositionedToken("es", 0.95, 122, 100, 142, 120),
            PositionedToken("cr", 0.95, 144, 100, 164, 120),
            PositionedToken("i",  0.95, 166, 100, 176, 120),
            PositionedToken("bed", 0.95, 178, 100, 208, 120),
        ]
        out = reconstruct_page_text(tokens)
        self.assertEqual(out, "prescribed")

    def test_geometry_fragment_clustering_disposing(self):
        tokens = [
            PositionedToken("Di", 0.95, 100, 100, 120, 120),
            PositionedToken("sp", 0.95, 122, 100, 142, 120),
            PositionedToken("os", 0.95, 144, 100, 164, 120),
            PositionedToken("i",  0.95, 166, 100, 176, 120),
            PositionedToken("ng", 0.95, 178, 100, 198, 120),
        ]
        out = reconstruct_page_text(tokens)
        self.assertEqual(out, "Disposing")

    def test_geometry_fragment_clustering_exceeded(self):
        tokens = [
            PositionedToken("ex", 0.95, 100, 100, 120, 120),
            PositionedToken("ce", 0.95, 122, 100, 142, 120),
            PositionedToken("ed", 0.95, 144, 100, 164, 120),
            PositionedToken("ed", 0.95, 166, 100, 186, 120),
        ]
        out = reconstruct_page_text(tokens)
        self.assertEqual(out, "exceeded")

    def test_geometry_word_boundary_preservation(self):
        # Genuine gap = 20px (ratio = 2.0 > 0.45 threshold) -> Must separate into 'the Court'
        tokens = [
            PositionedToken("the", 0.95, 100, 100, 130, 120),
            PositionedToken("Court", 0.95, 150, 100, 200, 120),
        ]
        out = reconstruct_page_text(tokens)
        self.assertEqual(out, "the Court")


if __name__ == "__main__":
    unittest.main()
