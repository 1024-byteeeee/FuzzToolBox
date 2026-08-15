import random
import re
import unittest

from fuzztoolbox.tools.lorem_ipsum.generator import (
    PARAGRAPH_RANGE,
    SENTENCE_RANGE,
    WORD_RANGE,
    generate_lorem,
)


class LoremGeneratorTests(unittest.TestCase):
    def test_all_requested_counts_are_exact(self):
        result = generate_lorem(
            4,
            sentences_per_paragraph=3,
            words_per_sentence=9,
            rng=random.Random(11),
        )
        self.assertEqual(result.paragraph_count, 4)
        self.assertEqual(result.sentence_count, 12)
        self.assertEqual(result.word_count, 108)
        self.assertEqual(len(result.text.split("\n\n")), 4)
        self.assertEqual(result.text.count("."), 12)
        self.assertEqual(len(re.findall(r"[A-Za-z]+", result.text)), 108)

    def test_classic_opening_respects_word_count(self):
        short = generate_lorem(
            1, sentences_per_paragraph=1, words_per_sentence=3, rng=random.Random(2)
        )
        long = generate_lorem(
            1, sentences_per_paragraph=1, words_per_sentence=12, rng=random.Random(2)
        )
        self.assertEqual(short.text, "Lorem ipsum dolor.")
        self.assertTrue(long.text.startswith("Lorem ipsum dolor sit amet"))
        self.assertEqual(len(re.findall(r"[A-Za-z]+", long.text)), 12)

    def test_html_wraps_each_paragraph(self):
        result = generate_lorem(
            2,
            sentences_per_paragraph=2,
            words_per_sentence=6,
            html_output=True,
            rng=random.Random(2),
        )
        self.assertEqual(result.text.count("<p>"), 2)
        self.assertEqual(result.text.count("</p>"), 2)
        self.assertNotIn("\n\n", result.text)

    def test_classic_opening_can_be_disabled(self):
        result = generate_lorem(
            1,
            sentences_per_paragraph=1,
            words_per_sentence=8,
            start_with_lorem=False,
            rng=random.Random(4),
        )
        self.assertFalse(result.text.startswith("Lorem ipsum"))

    def test_invalid_slider_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, f"1–{PARAGRAPH_RANGE[1]}"):
            generate_lorem(PARAGRAPH_RANGE[1] + 1)
        with self.assertRaisesRegex(ValueError, f"1–{SENTENCE_RANGE[1]}"):
            generate_lorem(1, sentences_per_paragraph=SENTENCE_RANGE[1] + 1)
        with self.assertRaisesRegex(ValueError, f"3–{WORD_RANGE[1]}"):
            generate_lorem(1, words_per_sentence=WORD_RANGE[0] - 1)
        with self.assertRaisesRegex(TypeError, "必须是整数"):
            generate_lorem(True)


if __name__ == "__main__":
    unittest.main()
