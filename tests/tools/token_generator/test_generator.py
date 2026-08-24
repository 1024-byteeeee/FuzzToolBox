import string
import unittest

from fuzztoolbox.tools.token_generator.generator import (
    DEFAULT_LENGTH,
    MAX_LENGTH,
    generate_token,
    unique_characters,
)


class TokenGeneratorTests(unittest.TestCase):
    def test_defaults_generate_a_sixty_four_character_token(self):
        token = generate_token()
        self.assertEqual(len(token), DEFAULT_LENGTH)
        self.assertTrue(any(character.islower() for character in token))
        self.assertTrue(any(character.isupper() for character in token))
        self.assertTrue(any(character.isdigit() for character in token))
        self.assertTrue(set(token) <= set(string.ascii_letters + string.digits))

    def test_each_selected_group_is_represented(self):
        token = generate_token(4, lowercase=True, uppercase=True, digits=True, symbols=True)
        self.assertTrue(any(character in string.ascii_lowercase for character in token))
        self.assertTrue(any(character in string.ascii_uppercase for character in token))
        self.assertTrue(any(character in string.digits for character in token))
        self.assertTrue(any(character in string.punctuation for character in token))

    def test_custom_only_generation_and_duplicate_removal(self):
        self.assertEqual(unique_characters("aabbcca"), "abc")
        token = generate_token(
            32,
            lowercase=False,
            uppercase=False,
            digits=False,
            custom_characters="XXYZYY",
        )
        self.assertEqual(len(token), 32)
        self.assertTrue(set(token) <= {"X", "Y", "Z"})
        self.assertTrue(set(token) & {"X", "Y", "Z"})

    def test_maximum_length_is_supported(self):
        self.assertEqual(len(generate_token(MAX_LENGTH)), MAX_LENGTH)

    def test_invalid_length_and_empty_character_pool_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "必须是整数"):
            generate_token(1.5)
        with self.assertRaisesRegex(ValueError, "1–512"):
            generate_token(0)
        with self.assertRaisesRegex(ValueError, "1–512"):
            generate_token(MAX_LENGTH + 1)
        with self.assertRaisesRegex(ValueError, "至少选择"):
            generate_token(8, lowercase=False, uppercase=False, digits=False)

    def test_length_must_cover_every_enabled_group(self):
        with self.assertRaisesRegex(ValueError, "字符类型数量"):
            generate_token(2, lowercase=True, uppercase=True, digits=True)


if __name__ == "__main__":
    unittest.main()
