import pathlib

from rgraph.hashing import HASH_RE, canonical_bytes, content_hash, file_hash


def test_key_order_does_not_change_the_hash():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_value_change_does_change_the_hash():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_canonical_bytes_are_compact_and_sorted():
    assert canonical_bytes({"b": 1, "a": [1, 2]}) == b'{"a":[1,2],"b":1}'


def test_non_ascii_survives_unescaped():
    assert "ö".encode() in canonical_bytes({"a": "ö"})


def test_hash_shape():
    assert HASH_RE.match(content_hash({"a": 1}))


def test_file_hash_matches_content(tmp_path: pathlib.Path):
    target = tmp_path / "raw.jsonl"
    target.write_bytes(b'{"run":1}\n')
    first = file_hash(target)
    assert HASH_RE.match(first)
    target.write_bytes(b'{"run":2}\n')
    assert file_hash(target) != first
