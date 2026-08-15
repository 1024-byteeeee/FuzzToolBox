"""Generate Lorem Ipsum text without external dependencies."""

from __future__ import annotations

import html
import random
import re
from dataclasses import dataclass

DEFAULT_PARAGRAPHS = 3
DEFAULT_SENTENCES_PER_PARAGRAPH = 5
DEFAULT_WORDS_PER_SENTENCE = 10
PARAGRAPH_RANGE = (1, 50)
SENTENCE_RANGE = (1, 20)
WORD_RANGE = (3, 30)
CLASSIC_SENTENCE = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
CLASSIC_WORDS = tuple(re.findall(r"[A-Za-z]+", CLASSIC_SENTENCE.lower()))
WORDS = (
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
    "elit", "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore",
    "et", "dolore", "magna", "aliqua", "enim", "ad", "minim", "veniam",
    "quis", "nostrud", "exercitation", "ullamco", "laboris", "nisi", "aliquip",
    "ex", "ea", "commodo", "consequat", "duis", "aute", "irure", "in",
    "reprehenderit", "voluptate", "velit", "esse", "cillum", "eu", "fugiat",
    "nulla", "pariatur", "excepteur", "sint", "occaecat", "cupidatat", "non",
    "proident", "sunt", "culpa", "qui", "officia", "deserunt", "mollit",
    "anim", "id", "est", "laborum", "porta", "massa", "dictum", "integer",
    "malesuada", "fermentum", "viverra", "mauris", "pharetra", "pellentesque",
)


@dataclass(frozen=True)
class LoremResult:
    text: str
    word_count: int
    sentence_count: int
    paragraph_count: int


def _validate_range(value: int, limits: tuple[int, int], label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label}必须是整数")
    minimum, maximum = limits
    if not minimum <= value <= maximum:
        raise ValueError(f"{label}必须在 {minimum}–{maximum} 之间")


def _choose_words(amount: int, rng, prefix: tuple[str, ...] = ()) -> list[str]:
    values = list(prefix[:amount])
    previous = values[-1] if values else None
    while len(values) < amount:
        word = rng.choice(WORDS)
        while word == previous and len(WORDS) > 1:
            word = rng.choice(WORDS)
        values.append(word)
        previous = word
    return values


def _sentence(word_count: int, rng, classic_opening: bool = False) -> str:
    prefix = CLASSIC_WORDS if classic_opening else ()
    words = _choose_words(word_count, rng, prefix)
    if not classic_opening and len(words) >= 9 and rng.random() < 0.55:
        comma_at = rng.randint(3, len(words) - 4)
        words[comma_at] += ","
    words[0] = words[0].capitalize()
    return " ".join(words) + "."


def _render(paragraphs: list[str], html_output: bool) -> str:
    if not html_output:
        return "\n\n".join(paragraphs)
    return "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)


def generate_lorem(
    paragraphs: int = DEFAULT_PARAGRAPHS,
    *,
    sentences_per_paragraph: int = DEFAULT_SENTENCES_PER_PARAGRAPH,
    words_per_sentence: int = DEFAULT_WORDS_PER_SENTENCE,
    start_with_lorem: bool = True,
    html_output: bool = False,
    rng=None,
) -> LoremResult:
    """Generate paragraphs with exact sentence and word counts."""
    _validate_range(paragraphs, PARAGRAPH_RANGE, "段落数")
    _validate_range(sentences_per_paragraph, SENTENCE_RANGE, "每段句子数")
    _validate_range(words_per_sentence, WORD_RANGE, "每句单词数")
    source = rng if rng is not None else random.SystemRandom()

    generated: list[str] = []
    for paragraph_index in range(paragraphs):
        sentences = [
            _sentence(
                words_per_sentence,
                source,
                classic_opening=(
                    start_with_lorem
                    and paragraph_index == 0
                    and sentence_index == 0
                ),
            )
            for sentence_index in range(sentences_per_paragraph)
        ]
        generated.append(" ".join(sentences))

    sentence_count = paragraphs * sentences_per_paragraph
    return LoremResult(
        _render(generated, html_output),
        sentence_count * words_per_sentence,
        sentence_count,
        paragraphs,
    )
