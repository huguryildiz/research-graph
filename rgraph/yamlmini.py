"""A strict YAML subset. Refuses anything it does not fully understand.

Supported: block mappings, block sequences, inline flow mappings and flow
sequences, ``#`` comments, quoted and bare scalars, null/true/false, integers
and floats. Refused, with a line number: anchors, aliases, tags,
multi-document streams, block scalars, tab indentation.
"""

from __future__ import annotations

import pathlib
import re

_BANNED = (
    (re.compile(r"(?<![\w\"'])&[A-Za-z0-9_-]+"), "anchor"),
    (re.compile(r"(?<![\w\"'*])\*[A-Za-z0-9_-]+"), "alias"),
    (re.compile(r"(?<![\w\"'])!!?[A-Za-z]"), "tag"),
    (re.compile(r":\s*[|>][-+0-9]*\s*$"), "block scalar"),
)
_NUM = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+([eE][-+]?\d+)?$")
_KEY = re.compile(r"^([A-Za-z0-9_.$/-]+|\"[^\"]*\"|'[^']*')\s*:(\s|$)")


class YamlError(Exception):
    def __init__(self, message: str, line: int, source: str) -> None:
        super().__init__(f"{source}:{line}: {message}")
        self.line = line
        self.source = source


class _Line:
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent: int, text: str, no: int) -> None:
        self.indent, self.text, self.no = indent, text, no


def load_file(path: pathlib.Path) -> dict | list:
    return loads(path.read_text(encoding="utf-8"), source=str(path))


def loads(text: str, *, source: str = "<string>") -> dict | list:
    lines = _prepare(text, source)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0].indent, source)
    if index != len(lines):
        raise YamlError("unexpected content after document end", lines[index].no, source)
    return value


def _prepare(text: str, source: str) -> list[_Line]:
    joined: list[_Line] = []
    pending: str | None = None
    pending_no = 0
    pending_indent = 0
    for no, line in enumerate(text.splitlines(), start=1):
        if line.strip() in ("---", "..."):
            raise YamlError("multi-document streams are not supported", no, source)
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise YamlError("tab indentation is not supported", no, source)
        stripped = _strip_comment(line)
        if not stripped.strip():
            continue
        for pattern, name in _BANNED:
            if pattern.search(stripped):
                raise YamlError(f"{name}s are not supported", no, source)
        indent = len(stripped) - len(stripped.lstrip())
        body = stripped.strip()
        if pending is None:
            pending, pending_no, pending_indent = body, no, indent
        else:
            pending += " " + body
        depth = (
            pending.count("{") - pending.count("}")
            + pending.count("[") - pending.count("]")
        )
        if depth > 0:
            continue
        if depth < 0:
            raise YamlError("unbalanced flow brackets", no, source)
        joined.append(_Line(pending_indent, pending, pending_no))
        pending = None
    if pending is not None:
        raise YamlError("unclosed flow collection", pending_no, source)
    return joined


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _parse_block(lines: list[_Line], index: int, indent: int, source: str):
    if lines[index].text.startswith("- "):
        return _parse_seq(lines, index, indent, source)
    return _parse_map(lines, index, indent, source)


def _parse_map(lines: list[_Line], index: int, indent: int, source: str):
    result: dict = {}
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        match = _KEY.match(line.text)
        if not match:
            raise YamlError(f"expected 'key: value', got {line.text!r}", line.no, source)
        key = _scalar(match.group(1), line.no, source)
        rest = line.text[match.end(1) + 1 :].strip()
        if rest:
            result[key] = _parse_inline(rest, line.no, source)
            index += 1
            continue
        if index + 1 < len(lines) and lines[index + 1].indent > indent:
            result[key], index = _parse_block(lines, index + 1, lines[index + 1].indent, source)
        else:
            result[key] = None
            index += 1
    return result, index


def _parse_seq(lines: list[_Line], index: int, indent: int, source: str):
    result: list = []
    while (
        index < len(lines)
        and lines[index].indent == indent
        and lines[index].text.startswith("- ")
    ):
        line = lines[index]
        body = line.text[2:].strip()
        if _KEY.match(body):
            inner = [_Line(indent + 2, body, line.no)]
            probe = index + 1
            while probe < len(lines) and lines[probe].indent > indent:
                inner.append(lines[probe])
                probe += 1
            item, consumed = _parse_map(inner, 0, indent + 2, source)
            if consumed != len(inner):
                raise YamlError("ragged indentation inside sequence item", line.no, source)
            result.append(item)
            index = probe
        else:
            result.append(_parse_inline(body, line.no, source))
            index += 1
    return result, index


def _parse_inline(text: str, no: int, source: str):
    text = text.strip()
    if text.startswith("{"):
        value, rest = _flow_map(text, no, source)
    elif text.startswith("["):
        value, rest = _flow_seq(text, no, source)
    else:
        return _scalar(text, no, source)
    if rest.strip():
        raise YamlError(f"trailing content after flow collection: {rest!r}", no, source)
    return value


def _flow_map(text: str, no: int, source: str):
    result: dict = {}
    cursor = 1
    while True:
        cursor = _skip_ws(text, cursor)
        if cursor >= len(text):
            raise YamlError("unclosed flow mapping", no, source)
        if text[cursor] == "}":
            return result, text[cursor + 1 :]
        try:
            key_end = text.index(":", cursor)
        except ValueError:
            raise YamlError("unclosed flow mapping", no, source) from None
        key = _scalar(text[cursor:key_end].strip(), no, source)
        value, text = _flow_value(text[key_end + 1 :], no, source)
        result[key] = value
        cursor = _skip_ws(text, 0)
        if cursor < len(text) and text[cursor] == ",":
            cursor += 1


def _flow_seq(text: str, no: int, source: str):
    result: list = []
    cursor = 1
    while True:
        cursor = _skip_ws(text, cursor)
        if cursor >= len(text):
            raise YamlError("unclosed flow sequence", no, source)
        if text[cursor] == "]":
            return result, text[cursor + 1 :]
        value, text = _flow_value(text[cursor:], no, source)
        result.append(value)
        cursor = _skip_ws(text, 0)
        if cursor < len(text) and text[cursor] == ",":
            cursor += 1


def _flow_value(text: str, no: int, source: str):
    text = text.lstrip()
    if text.startswith("{"):
        return _flow_map(text, no, source)
    if text.startswith("["):
        return _flow_seq(text, no, source)
    end = 0
    quote = None
    while end < len(text):
        char = text[end]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in ",}]":
            break
        end += 1
    return _scalar(text[:end].strip(), no, source), text[end:]


def _skip_ws(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    return cursor


def _scalar(token: str, no: int, source: str):
    if not token:
        raise YamlError("empty scalar", no, source)
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    if token in ("null", "~"):
        return None
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    if _NUM.match(token):
        return int(token)
    if _FLOAT.match(token):
        return float(token)
    return token
