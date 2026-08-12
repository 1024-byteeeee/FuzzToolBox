import unittest

from fuzztoolbox.tools.text_comparer.syntax import LANGUAGES, detect_language


class SyntaxTests(unittest.TestCase):
    def test_language_catalog_covers_common_compiled_and_script_languages(self):
        values = {value for _, value in LANGUAGES}
        self.assertTrue({"java", "c", "cpp", "csharp", "go", "rust"} <= values)
        self.assertTrue({"python", "javascript", "typescript", "shell"} <= values)

    def test_detects_distinctive_languages_and_falls_back_to_text(self):
        self.assertEqual(detect_language('#include <iostream>\nstd::cout << "ok";'), "cpp")
        self.assertEqual(detect_language("public static void main(String[] args) {}"), "java")
        self.assertEqual(detect_language("fn main() { let mut value = 1; }"), "rust")
        self.assertEqual(detect_language("ordinary prose"), "text")


if __name__ == "__main__":
    unittest.main()
