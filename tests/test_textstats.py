"""Unit tests for decoding and text profiling (hebloc.textstats)."""

from __future__ import annotations

from hebloc.textstats import decode_bytes, looks_like_7zip_log, profile_text, split_lines

HEB = "שלום עולם"


def test_decode_variants():
    assert decode_bytes(b"") == ("", "empty", 0)
    assert decode_bytes(b"abc 123")[1] == "ascii"
    assert decode_bytes(HEB.encode("utf-8")) == (HEB, "utf-8", 0)
    assert decode_bytes(b"\xef\xbb\xbf" + HEB.encode("utf-8")) == (HEB, "utf-8-sig", 0)
    assert decode_bytes(HEB.encode("cp1255")) == (HEB, "cp1255", 0)


def test_decode_lossy_never_raises():
    # 0x81 is undefined in cp1255 and invalid as UTF-8 → lossy, errors counted.
    text, enc, errors = decode_bytes("שלום".encode("cp1255") + b"\x81")
    assert enc.endswith("-lossy") and errors == 1 and "שלום" in text


def test_cp1255_hebrew_is_not_misread_as_utf8():
    # Typical Modern-corpus line; must come out as Hebrew, not mojibake.
    line = "הוא אמר : \" שלום \" ."
    text, enc, _ = decode_bytes(line.encode("cp1255"))
    assert enc == "cp1255" and text == line


def test_split_lines_definition():
    assert split_lines("") == []
    assert split_lines("a\nb") == ["a", "b"]
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\r\nb\r\n") == ["a", "b"]
    assert split_lines("\na\n\n") == ["", "a", ""]
    # Unicode line separators are NOT line breaks in the project definition.
    assert split_lines("a b\x85c") == ["a b\x85c"]


def test_profile_counts():
    text = "\r\nבְּרֵאשִׁ֖ית בָּרָ֣א\r\n\r\nabc 12 את-הארץ\r\n"
    p = profile_text(text.encode("utf-8"))
    assert p.encoding == "utf-8" and p.line_endings == "crlf"
    assert p.n_lines == 4 and p.n_nonempty_lines == 2
    assert p.n_tokens == 5                     # בראשית, ברא, abc, 12, את-הארץ
    assert p.n_hebrew_tokens == 3              # one match per token containing a Hebrew letter
    assert p.n_hebrew_letters == len("בראשיתבראאתהארץ")
    assert p.n_cantillation == 2               # tipcha + munach
    assert p.n_niqqud > 0 and p.n_latin_letters == 3 and p.n_digits == 2
    assert not p.is_blank


def test_modern_artifacts_and_7zip_signature():
    line = "גר prefix=ב token=רח' פנלון [ IMG ] ראו http://x.co"
    p = profile_text(line.encode("cp1255"))
    assert (p.n_prefix_tags, p.n_token_tags, p.n_img_tags, p.n_urls) == (1, 1, 1, 1)
    log = b"-  Zip  7  (  A  )  4.42  Copyright  (  c  )  1999  -  2006  Igor  Pavlov  2006"
    assert looks_like_7zip_log(log)
    assert not looks_like_7zip_log("שלום Igor Pavlov".encode("cp1255"))


def test_profile_anomalies():
    p = profile_text("a\rb\x00c d﻿e\nf\r\n".encode("utf-8"))
    assert p.line_endings == "mixed"
    assert p.n_odd_line_separators == 2        # lone \r and U+2028
    assert p.n_control_chars == 1              # NUL
    assert p.n_feff == 1
    assert profile_text(b" \n\t\n").is_blank
    assert profile_text(b"").encoding == "empty" and profile_text(b"").n_lines == 0
