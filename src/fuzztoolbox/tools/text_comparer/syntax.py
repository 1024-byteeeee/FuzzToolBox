"""Dependency-free, editor-oriented syntax highlighting for common languages."""

import re
from dataclasses import dataclass

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from fuzztoolbox.ui.style_loader import on_theme_changed, theme_color

LANGUAGES = (
    ("自动检测", "auto"), ("纯文本", "text"), ("JSON", "json"),
    ("Python", "python"), ("JavaScript", "javascript"), ("TypeScript", "typescript"),
    ("Java", "java"), ("C", "c"), ("C++", "cpp"), ("C#", "csharp"),
    ("Go", "go"), ("Rust", "rust"), ("Kotlin", "kotlin"), ("Swift", "swift"),
    ("PHP", "php"), ("Ruby", "ruby"), ("Lua", "lua"), ("Perl", "perl"),
    ("R", "r"), ("Dart", "dart"), ("Scala", "scala"), ("Groovy", "groovy"),
    ("HTML", "html"), ("XML", "xml"), ("CSS", "css"), ("SQL", "sql"),
    ("Shell", "shell"), ("PowerShell", "powershell"), ("YAML", "yaml"),
    ("TOML", "toml"), ("Markdown", "markdown"),
)


C_STYLE = "break case catch class const continue default do else enum extends false finally for if import interface new null package private protected public return static struct super switch this throw true try typedef typeof union void while"
KEYWORDS = {
    "json": "true false null",
    "python": "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield match case",
    "javascript": C_STYLE + " async await delete export function instanceof let of undefined var with yield",
    "typescript": C_STYLE + " abstract any as async await boolean declare export function implements keyof let namespace never number object readonly string symbol type unknown var",
    "java": C_STYLE + " abstract boolean byte char double final float implements instanceof int long native short strictfp synchronized transient volatile",
    "c": C_STYLE + " auto double extern float inline int long register restrict short signed sizeof unsigned volatile _Bool _Complex",
    "cpp": C_STYLE + " alignas alignof auto bool constexpr decltype delete explicit friend inline mutable namespace noexcept nullptr operator override template thread_local using virtual wchar_t",
    "csharp": C_STYLE + " abstract as base bool byte checked decimal delegate event explicit extern fixed foreach implicit in int internal is lock long object out override params readonly ref sbyte sealed short sizeof stackalloc string uint ulong unchecked unsafe ushort using virtual",
    "go": "break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var",
    "rust": "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while",
    "kotlin": C_STYLE + " actual companion constructor crossinline data expect fun infix init inner internal lateinit noinline object open operator out override reified sealed suspend tailrec val var when",
    "swift": "associatedtype break case catch class continue default defer deinit do else enum extension fallthrough false fileprivate for func guard if import in init inout internal is let nil open operator private protocol public repeat rethrows return self static struct subscript super switch throw throws true try typealias var where while",
    "php": C_STYLE + " echo elseif endif endforeach namespace require include trait use function",
    "ruby": "alias and begin break case class def defined do else elsif end ensure false for if in module next nil not or redo rescue retry return self super then true undef unless until when while yield",
    "lua": "and break do else elseif end false for function goto if in local nil not or repeat return then true until while",
    "perl": "continue do else elsif for foreach given goto if last local my next no our package redo require return state sub unless until use when while",
    "r": "break else FALSE for function if in Inf NA NaN next NULL repeat return TRUE while",
    "dart": C_STYLE + " abstract async await covariant deferred dynamic extension factory get late mixin on required set sync var",
    "scala": "abstract case catch class def do else extends false final finally for forSome if implicit import lazy match new null object override package private protected return sealed super this throw trait true try type val var while with yield",
    "groovy": C_STYLE + " as def in trait",
    "sql": "add all alter and any as asc between by case check column constraint create database default delete desc distinct drop else exists foreign from full group having in index inner insert into is join key left like limit not null on or order outer primary references right row select set table then union unique update values view when where with",
    "shell": "case do done elif else esac export fi for function if in local readonly return select then time until while",
    "powershell": "begin break catch class continue data do dynamicparam else elseif end enum exit filter finally for foreach from function hidden if in param process return static switch throw trap try until using var while workflow",
}


@dataclass(frozen=True)
class LanguageSpec:
    line_comment: tuple = ()
    block_comment: tuple = ()


SPECS = {
    "python": LanguageSpec(("#",), (("'''", "'''"), ('"""', '"""'))),
    "ruby": LanguageSpec(("#",)), "r": LanguageSpec(("#",)),
    "shell": LanguageSpec(("#",)), "powershell": LanguageSpec(("#",), (("<#", "#>"),)),
    "yaml": LanguageSpec(("#",)), "toml": LanguageSpec(("#",)),
    "lua": LanguageSpec(("--",), (("--[[", "]]"),)),
    "html": LanguageSpec((), (("<!--", "-->"),)), "xml": LanguageSpec((), (("<!--", "-->"),)),
    "css": LanguageSpec((), (("/*", "*/"),)),
}
for _name in ("javascript", "typescript", "java", "c", "cpp", "csharp", "go", "rust", "kotlin", "swift", "php", "dart", "scala", "groovy"):
    SPECS[_name] = LanguageSpec(("//",), (("/*", "*/"),))
for _name in ("json", "perl", "sql", "markdown", "text"):
    SPECS.setdefault(_name, LanguageSpec())


def detect_language(text):
    sample = text[:12000]
    checks = (
        ("json", r"^\s*[\[{].*[\]}]\s*$"), ("python", r"(?m)^\s*(def|class)\s+\w+|__name__\s*=="),
        ("cpp", r"#include\s*<|\bstd::"), ("csharp", r"\busing\s+System\b|\bnamespace\s+\w+"),
        ("java", r"(?m)\bpublic\s+static\s+void\s+main\b|^\s*package\s+[\w.]+;"),
        ("go", r"(?m)^\s*package\s+(main|\w+)|\bfunc\s+\w+\s*\("),
        ("rust", r"\bfn\s+main\s*\(|\blet\s+mut\b"), ("html", r"<!DOCTYPE\s+html|<html\b"),
        ("xml", r"<\?xml\b"), ("php", r"<\?php\b"), ("css", r"(?m)^\s*[.#][\w-]+\s*\{"),
        ("sql", r"(?i)\bselect\b.+\bfrom\b|\bcreate\s+table\b"),
        ("shell", r"^#!.*\b(sh|bash|zsh)\b"), ("powershell", r"(?i)\b(Get|Set|New)-\w+"),
        ("yaml", r"(?m)^\s*[\w.-]+:\s+\S"), ("markdown", r"(?m)^#{1,6}\s+|^```"),
    )
    for language, pattern in checks:
        if re.search(pattern, sample, re.S):
            return language
    return "text"


def _format(color, bold=False, italic=False):
    value = QTextCharFormat()
    value.setForeground(QColor(color))
    if bold:
        value.setFontWeight(QFont.Bold)
    value.setFontItalic(italic)
    return value


class CodeSyntaxHighlighter(QSyntaxHighlighter):
    """Practical lexical highlighter; never paints backgrounds used by Diff."""

    def __init__(self, document, language="text", diff_mode=None):
        super().__init__(document)
        self.language = language
        self.diff_mode = diff_mode
        self._apply_theme()
        on_theme_changed(self._apply_theme)

    def _apply_theme(self):
        self.formats = {
            "keyword": _format(theme_color("syntax_keyword"), True),
            "string": _format(theme_color("syntax_string")),
            "number": _format(theme_color("syntax_number")),
            "comment": _format(theme_color("syntax_comment"), italic=True),
            "type": _format(theme_color("syntax_type")),
            "tag": _format(theme_color("syntax_tag"), True),
            "property": _format(theme_color("syntax_property")),
            "preprocessor": _format(theme_color("syntax_preprocessor"), True),
        }
        self.rehighlight()

    def set_language(self, language):
        if language == self.language:
            return
        self.language = language
        self.rehighlight()

    def set_diff_mode(self, mode):
        self.diff_mode = mode
        self.rehighlight()

    def _apply(self, text, offset, pattern, name, flags=QRegularExpression.NoPatternOption):
        expression = QRegularExpression(pattern, flags)
        iterator = expression.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(offset + match.capturedStart(), match.capturedLength(), self.formats[name])

    def highlightBlock(self, raw_text):
        offset, text = self._code_segment(raw_text)
        language = self.language
        if language in {"text", "auto"} or not text:
            self.setCurrentBlockState(0)
            return
        if language in {"html", "xml"}:
            self._apply(text, offset, r"</?[A-Za-z][\w:.-]*", "tag")
            self._apply(text, offset, r"\b[A-Za-z_:][\w:.-]*(?=\s*=)", "property")
        if language in {"yaml", "toml"}:
            self._apply(text, offset, r'"(?:\\.|[^"\\])*"(?=\s*:)|^[ \t]*[\w.-]+(?=\s*=|\s*:)', "property")
        if language == "css":
            self._apply(text, offset, r"--?[\w-]+(?=\s*:)|[\w-]+(?=\s*:)", "property")
        if language == "markdown":
            self._apply(text, offset, r"^#{1,6}\s+.*$|\*\*[^*]+\*\*|`[^`]+`", "keyword")
        keywords = KEYWORDS.get(language, "")
        if keywords:
            self._apply(text, offset, r"\b(?:" + "|".join(map(re.escape, keywords.split())) + r")\b", "keyword", QRegularExpression.CaseInsensitiveOption if language == "sql" else QRegularExpression.NoPatternOption)
        self._apply(text, offset, r"\b(?:0[xX][0-9A-Fa-f]+|0[bB][01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b", "number")
        self._apply(text, offset, r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', "string")
        # JSON keys are strings lexically, so apply their more specific style
        # after generic strings to keep key/value colors visually distinct.
        if language == "json":
            self._apply(text, offset, r'"(?:\\.|[^"\\])*"(?=\s*:)', "property")
        if language in {"c", "cpp"}:
            self._apply(text, offset, r"^\s*#\s*\w+.*$", "preprocessor")
        spec = SPECS.get(language, LanguageSpec())
        for prefix in spec.line_comment:
            self._apply(text, offset, re.escape(prefix) + r".*$", "comment")
        self._highlight_block_comments(text, offset, spec.block_comment)

    def _code_segment(self, text):
        if self.diff_mode == "unified":
            if text.startswith(("@@", "--- ", "+++ ")):
                return len(text), ""
            return (1, text[1:]) if text[:1] in {"+", "-", " "} else (0, text)
        if self.diff_mode == "context":
            if text == "***************" or text.startswith(("*** ", "--- ")):
                return len(text), ""
            return (2, text[2:]) if text[:2] in {"+ ", "- ", "! ", "  "} else (0, text)
        return 0, text

    def _highlight_block_comments(self, text, offset, delimiters):
        state = self.previousBlockState()
        self.setCurrentBlockState(0)
        for index, (start_token, end_token) in enumerate(delimiters, 1):
            start = 0 if state == index else text.find(start_token)
            while start >= 0:
                end = text.find(end_token, start + (0 if state == index else len(start_token)))
                if end < 0:
                    self.setFormat(offset + start, len(text) - start, self.formats["comment"])
                    self.setCurrentBlockState(index)
                    return
                length = end - start + len(end_token)
                self.setFormat(offset + start, length, self.formats["comment"])
                start = text.find(start_token, start + length)
            state = 0
