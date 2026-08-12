import unittest

from fuzztoolbox.tools.text_comparer.comparer import (
    compare_texts,
    context_diff,
    unified_diff,
)


class TextComparerTests(unittest.TestCase):
    def test_identical_text_has_no_changes(self):
        result = compare_texts("one\ntwo", "one\ntwo")
        self.assertTrue(result.stats.identical)
        self.assertEqual([line.tag for line in result.lines], ["equal", "equal"])

    def test_added_deleted_and_modified_lines_are_counted(self):
        result = compare_texts(
            "same\nold value\ndeleted\nend",
            "same\nnew value\nadded\nmore\nend",
        )
        self.assertEqual(result.stats.modified, 2)
        self.assertEqual(result.stats.added, 1)
        self.assertEqual(result.stats.deleted, 0)
        modified = [line for line in result.lines if line.tag == "replace"]
        self.assertTrue(modified[0].left_spans)
        self.assertTrue(modified[0].right_spans)

    def test_pure_insert_and_delete_have_blank_opposite_sides(self):
        inserted = compare_texts("a\nc", "a\nb\nc")
        line = next(line for line in inserted.lines if line.tag == "insert")
        self.assertIsNone(line.left_number)
        self.assertEqual(line.right_text, "b")
        deleted = compare_texts("a\nb\nc", "a\nc")
        line = next(line for line in deleted.lines if line.tag == "delete")
        self.assertEqual(line.left_text, "b")
        self.assertIsNone(line.right_number)

    def test_unified_and_context_output_have_standard_headers(self):
        left = "one\ntwo\n"
        right = "one\nchanged\n"
        unified = unified_diff(left, right)
        self.assertIn("--- 原始文本", unified)
        self.assertIn("+++ 修改后文本", unified)
        self.assertIn("@@", unified)
        context = context_diff(left, right)
        self.assertIn("*** 原始文本", context)
        self.assertIn("--- 修改后文本", context)
        self.assertIn("***************", context)

    def test_context_range_is_validated(self):
        with self.assertRaisesRegex(ValueError, "0–20"):
            unified_diff("a", "b", -1)
        with self.assertRaisesRegex(ValueError, "0–20"):
            context_diff("a", "b", 21)


if __name__ == "__main__":
    unittest.main()
