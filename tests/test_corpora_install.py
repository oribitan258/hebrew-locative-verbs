"""`hebloc corpora install`: every plausible shape of the course download, with Hebrew file names.

A miniature corpus with a Hebrew Haskala file name is packed the ways a partner may receive it
(folder, zip with/without the UTF-8 flag, legacy code pages, Explorer-mangled folder, multi-part
zips, nested archives, tar.gz, 7z) and must install IDENTICALLY, or fail with nothing installed.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from hebloc.team import corpora as C

HEB = "אברהם דב--זיכרונות (חלק א)--שנת 1879--Ytext1072001.txt"
FILES = {
    "Mikra/Genesis.txt": b"verse one\nverse two\n",
    "Hazal/Mishna/Avot.txt": b"mishna text\n",
    "Medieval/Rambam/empty.txt": b"",
    f"Haskala/{HEB}": "טקסט עברי\n".encode("utf-8"),
    "Haskala/plain--title--1800--prose--Ytext1.txt": b"plain\n",
    "Modern/haaretz/6/60.7z.txt": b"7-Zip log, not an archive\n",
    "Modern/haaretz/6/1.txt": "שורה\n".encode("cp1255"),
}


def _write_tree(root: Path, files: dict[str, bytes], name_fn=lambda s: s) -> None:
    for rel, data in files.items():
        p = root / name_fn(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


@pytest.fixture()
def refs(tmp_path):
    from hebloc.baseline import compute_baseline, make_anchor, write_anchor

    src = tmp_path / "reference_tree"
    _write_tree(src, FILES)
    table = compute_baseline(src, workers=1, progress=False)
    anchor = tmp_path / "anchor.json"
    write_anchor(make_anchor(table), anchor)
    names = tmp_path / "names.json"
    names.write_text(json.dumps(C.names_from_baseline(table)), encoding="utf-8")
    counter = iter(range(1000))

    def kw():
        return {"baseline_path": tmp_path / f"b{next(counter)}.parquet", "anchor_path": anchor,
                "names_path": names, "workers": 1, "progress": False}
    return kw


def _dest(tmp_path, tag):
    return tmp_path / f"clone_{tag}" / "corpora"


def _assert_installed(r, dest):
    assert r["verify"]["ok"], r
    assert r["installed"] == str(dest) and r["after_move_unchanged"]
    assert (dest / "Haskala" / HEB).read_bytes() == FILES[f"Haskala/{HEB}"]
    assert not (dest.parent / C.STAGING_NAME).exists()


def _zip(path: Path, files: dict[str, bytes], prefix: str = "") -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in files.items():
            zf.writestr(prefix + rel, data)


def _legacy_zip(path: Path, files: dict[str, bytes], encoding: str, prefix: str = "corpora/") -> None:
    """A zip whose names are raw ``encoding`` bytes WITHOUT the UTF-8 flag (old Windows/Linux zip tools)."""
    raws, placeholders = {}, {}
    for i, rel in enumerate(files):
        raw = (prefix + rel).encode(encoding)
        ph = f"P{i:04d}".encode() + b"x" * (len(raw) - 5)
        assert len(ph) == len(raw)
        raws[rel], placeholders[rel] = raw, ph
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in files.items():
            zf.writestr(placeholders[rel].decode(), data)
    data = buf.getvalue()
    for rel in files:
        assert data.count(placeholders[rel]) == 2          # local header + central directory
        data = data.replace(placeholders[rel], raws[rel])
    path.write_bytes(data)
    with zipfile.ZipFile(path) as zf:                       # really unflagged
        assert all(not (i.flag_bits & 0x800) for i in zf.infolist())


def test_from_extracted_folder_keeps_the_original(tmp_path, refs):
    src = tmp_path / "Downloads" / "corpora_course"
    _write_tree(src / "corpora", FILES)
    (src / "README.txt").write_text("course readme")
    dest = _dest(tmp_path, "f")
    r = C.install(src, dest, **refs())
    _assert_installed(r, dest)
    assert r["names"]["decoding"] == "as-is" and r["root_in_download"] == "corpora"
    assert (src / "corpora" / "Haskala" / HEB).exists()              # the download is untouched
    with pytest.raises(FileExistsError):
        C.install(src, dest, **refs())


def test_from_zip_with_utf8_names(tmp_path, refs):
    z = tmp_path / "corpora.zip"
    _zip(z, FILES, prefix="Corpora 2026/")
    dest = _dest(tmp_path, "z")
    _assert_installed(C.install(z, dest, **refs()), dest)


@pytest.mark.parametrize("encoding,label", [("utf-8", "cp437->utf-8"), ("cp1255", "cp437->cp1255")])
def test_from_zip_with_unflagged_legacy_names(tmp_path, refs, encoding, label):
    z = tmp_path / "corpora.zip"
    _legacy_zip(z, FILES, encoding)
    dest = _dest(tmp_path, encoding)
    r = C.install(z, dest, **refs())
    _assert_installed(r, dest)
    assert r["names"]["decoding"] == label


def test_from_folder_mangled_by_windows_explorer(tmp_path, refs):
    """Explorer extracting an unflagged UTF-8 zip on an English Windows writes cp437 mojibake names."""
    src = tmp_path / "extracted"
    _write_tree(src, FILES, name_fn=lambda s: s.encode("utf-8").decode("cp437"))
    assert not (src / "Haskala" / HEB).exists()
    dest = _dest(tmp_path, "m")
    r = C.install(src, dest, **refs())
    _assert_installed(r, dest)
    assert r["names"]["decoding"] == "cp437->utf-8"


def test_from_multipart_download_given_as_parts_or_folder(tmp_path, refs):
    """Google Drive splits a folder download into name-001.zip, name-002.zip with the same top folder."""
    items = list(FILES.items())
    parts = tmp_path / "drive"
    parts.mkdir()
    _zip(parts / "corpora-20261108T000000Z-001.zip", dict(items[:4]), prefix="corpora/")
    _zip(parts / "corpora-20261108T000000Z-002.zip", dict(items[3:]), prefix="corpora/")   # item 3 in both
    d1 = _dest(tmp_path, "p1")
    r = C.install(sorted(parts.glob("*.zip")), d1, **refs())
    _assert_installed(r, d1)
    assert r["duplicate_entries"] == 1
    d2 = _dest(tmp_path, "p2")
    _assert_installed(C.install(parts, d2, **refs()), d2)          # the folder holding the parts
    d3 = _dest(tmp_path, "p3")
    with pytest.raises(C.InstallError, match="could not find"):     # only one part: incomplete download
        C.install(parts / "corpora-20261108T000000Z-001.zip", d3, **refs())
    assert not d3.exists()


def test_from_nested_archives(tmp_path, refs):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        for rel, data in FILES.items():
            zf.writestr("corpora/" + rel, data)
    outer = tmp_path / "course_download.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("corpora.zip", inner.getvalue())
        zf.writestr("instructions.pdf", b"%PDF")
    dest = _dest(tmp_path, "n")
    _assert_installed(C.install(outer, dest, **refs()), dest)


def test_from_tar_gz(tmp_path, refs):
    t = tmp_path / "corpora.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        for rel, data in FILES.items():
            info = tarfile.TarInfo("corpora/" + rel)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    dest = _dest(tmp_path, "t")
    _assert_installed(C.install(t, dest, **refs()), dest)


def test_from_7z_via_system_bsdtar(tmp_path):
    """READING a .7z through the system bsdtar. (Windows' tar.exe crashes when WRITING a 7z with Hebrew
    names, so this archive uses ASCII names; Hebrew names inside a real .7z are untested.)"""
    from hebloc.baseline import compute_baseline, make_anchor, write_anchor

    tool = C.bsdtar()
    if tool is None:
        pytest.skip("no bsdtar on this machine")
    files = {k.replace(HEB, "ascii--title--1879--Ytext2.txt"): v for k, v in FILES.items()}
    src = tmp_path / "tree"
    _write_tree(src / "corpora", files)
    table = compute_baseline(src / "corpora", workers=1, progress=False)
    write_anchor(make_anchor(table), tmp_path / "anchor.json")
    (tmp_path / "names.json").write_text(json.dumps(C.names_from_baseline(table)), encoding="utf-8")
    seven = tmp_path / "corpora.7z"
    r = subprocess.run([tool, "--format", "7zip", "-cf", str(seven), "-C", str(src), "corpora"], capture_output=True)
    assert r.returncode == 0 and seven.stat().st_size > 0
    dest = _dest(tmp_path, "7")
    rep = C.install(seven, dest, baseline_path=tmp_path / "b.parquet", anchor_path=tmp_path / "anchor.json",
                    names_path=tmp_path / "names.json", workers=1, progress=False)
    assert rep["verify"]["ok"] and (dest / "Mikra" / "Genesis.txt").read_bytes() == FILES["Mikra/Genesis.txt"]


def test_os_junk_is_ignored_and_reported(tmp_path, refs):
    z = tmp_path / "mac.zip"
    junk = {"Haskala/.DS_Store": b"x", "Modern/haaretz/Thumbs.db": b"y"}
    _zip(z, FILES | junk, prefix="corpora/")
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("__MACOSX/corpora/._Genesis.txt", b"z")
    dest = _dest(tmp_path, "j")
    r = C.install(z, dest, **refs())
    _assert_installed(r, dest)
    assert r["ignored_os_files"] == 2 and not (dest / "Haskala" / ".DS_Store").exists()


def test_wrong_content_installs_nothing(tmp_path, refs):
    bad = dict(FILES)
    bad["Mikra/Genesis.txt"] = b"verse ONE\nverse two\n"        # same size, different bytes
    z = tmp_path / "bad.zip"
    _zip(z, bad, prefix="corpora/")
    dest = _dest(tmp_path, "w")
    r = C.install(z, dest, **refs())
    assert not r["verify"]["ok"] and r["installed"] is None
    assert any("manifest_sha256" in p for p in r["verify"]["problems"])
    assert not dest.exists() and not (dest.parent / C.STAGING_NAME).exists()


def test_wrong_names_or_extra_files_fail_before_hashing(tmp_path, refs):
    z = tmp_path / "extra.zip"
    _zip(z, FILES | {"Hazal/notes_by_student.txt": b"mine"}, prefix="corpora/")
    dest = _dest(tmp_path, "e")
    with pytest.raises(C.InstallError, match="file names"):
        C.install(z, dest, **refs())
    assert not dest.exists()


def test_two_copies_of_the_corpora_are_refused(tmp_path, refs):
    z = tmp_path / "two.zip"
    _zip(z, FILES, prefix="copy1/")
    with zipfile.ZipFile(z, "a") as zf:
        for rel, data in FILES.items():
            zf.writestr("copy2/" + rel, data)
    with pytest.raises(C.InstallError, match="more than one copy"):
        C.install(z, _dest(tmp_path, "2"), **refs())


def test_unsafe_paths_are_refused(tmp_path, refs):
    z = tmp_path / "evil.zip"
    _zip(z, FILES, prefix="corpora/")
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(C.InstallError, match="unsafe"):
        C.install(z, _dest(tmp_path, "u"), **refs())


def test_too_long_project_path_is_refused_up_front(tmp_path, refs, monkeypatch):
    monkeypatch.setattr(C, "long_paths_enabled", lambda: False)
    kw = refs()
    ref = json.loads(Path(kw["names_path"]).read_text(encoding="utf-8"))
    ref["max_rel_path_chars"] = 400
    Path(kw["names_path"]).write_text(json.dumps(ref), encoding="utf-8")
    src = tmp_path / "src"
    _write_tree(src, FILES)
    with pytest.raises(C.InstallError, match="too long"):
        C.install(src, _dest(tmp_path, "l"), **kw)


def test_real_names_reference_matches_the_anchor():
    from hebloc.paths import ANCHOR_PATH

    ref = C.read_names_reference()
    anchor = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
    assert ref["files"] == anchor["file_count"]
    assert {f: d["files"] for f, d in ref["per_folder"].items()} == {f: d["files"] for f, d in anchor["per_corpus"].items()}


def test_real_names_reference_matches_this_machines_baseline():
    from hebloc.paths import BASELINE_PATH

    if not BASELINE_PATH.exists():
        pytest.skip("no baseline on this machine yet")
    from hebloc.baseline import read_baseline

    assert C.names_from_baseline(read_baseline(BASELINE_PATH))["per_folder"] == C.read_names_reference()["per_folder"]


# ------------------------------------------------------------------ identity

def test_identity_set_resolve_and_refuse(tmp_path, monkeypatch):
    from hebloc.team import identity as I

    monkeypatch.setattr(I, "IDENTITY_PATH", tmp_path / "identity.json")
    monkeypatch.setattr(I, "_people", lambda: ("ori", "efrat", "adi"))
    with pytest.raises(I.IdentityError, match="who are you"):
        I.resolve(None)
    assert I.resolve(" Efrat ") == "efrat"                    # explicit name works before setting
    with pytest.raises(I.IdentityError, match="not a team member"):
        I.set_identity("mallory")
    I.set_identity("Efrat")
    assert I.get() == "efrat" and I.resolve(None) == "efrat" and I.resolve("EFRAT") == "efrat"
    with pytest.raises(I.IdentityError, match="set up for Efrat, not Adi"):
        I.resolve("adi")
    with pytest.raises(I.IdentityError, match="--change"):
        I.set_identity("adi")
    rec = I.set_identity("adi", change=True)
    assert I.get() == "adi" and [h["person"] for h in rec["history"]] == ["efrat", "adi"]
    shutil.rmtree(tmp_path, ignore_errors=True)
