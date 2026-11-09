"""Install the corpora on a new machine from the course download, and prove they are the exact files.

``hebloc corpora install --from <download> [--from <part 2> ...]`` accepts what a partner is likely
to have after downloading the course corpora:

- the archive itself: ``.zip`` (also multi-part downloads such as Google Drive's ``…-001.zip``,
  ``…-002.zip``: give every part, or the folder that holds them), ``.tar``/``.tar.gz``/``.tgz``/
  ``.tar.bz2``/``.tar.xz``, and ``.7z``/``.rar`` through the system ``bsdtar`` (built into Windows 10+
  and macOS as ``tar``);
- archives inside the archive (e.g. one zip per corpus);
- a folder the user already extracted.

It locates the folder that holds the five corpus folders (Mikra Hazal Medieval Haskala Modern) at any
depth, then checks the FILE NAMES against ``config/reference/corpora_names.json`` (names-only
digests derived from the anchored baseline). 320 Haskala file names are Hebrew; zip tools that do not
mark UTF-8 names, and Windows Explorer extracting such zips, turn them into mojibake (e.g. ``×'×``).
If the names do not match as they are, the installer tries the reversible re-decodings
(cp437/cp850/cp862/cp1252 bytes read as UTF-8/cp1255/cp862, plus Unicode NFC) and uses the one under
which EVERY name matches the reference. It never guesses partially.

Everything is written to a staging folder next to ``corpora/`` and hashed there; ``corpora/`` is
created (by one rename) only if all 404,294 files match the git-tracked anchor (names, sizes,
sha256 manifest). A failed or interrupted install leaves no ``corpora/`` behind. The user's download
is only read, never modified. OS junk (``__MACOSX``, ``.DS_Store``, ``Thumbs.db``, ``desktop.ini``,
``._*``) is skipped and reported; anything else extra makes the names check fail.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import unicodedata
import zipfile
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CONFIG_DIR, CORPORA, CORPORA_DIR

FOLDERS = tuple(CORPORA.values())
NAMES_PATH = CONFIG_DIR / "reference" / "corpora_names.json"
STAGING_NAME = ".corpora-staging"
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
BSDTAR_SUFFIXES = (".7z", ".rar")
ARCHIVE_SUFFIXES = (".zip",) + TAR_SUFFIXES + BSDTAR_SUFFIXES
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
WINDOWS = platform.system() == "Windows"


class InstallError(RuntimeError):
    pass


# ------------------------------------------------------------------ helpers

def _long(p: Path) -> Path:
    """Extended-length path on Windows (bypasses the 260-character limit inside the staging area)."""
    p = Path(p).resolve()
    if WINDOWS and not str(p).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(p))
    return p


def long_paths_enabled() -> bool:
    if not WINDOWS:
        return True
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return bool(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except OSError:
        return False


def _is_archive(name: str) -> bool:
    n = name.lower()
    return n.endswith(ARCHIVE_SUFFIXES)


def _is_junk(parts: tuple[str, ...]) -> bool:
    base = parts[-1].lower()
    return "__MACOSX" in parts or base in JUNK_NAMES or base.startswith("._")


def names_digest(paths: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(paths)).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ names reference (Ori)

def names_from_baseline(table) -> dict:
    rels = table.column("rel_path").to_pylist()
    per = {}
    for f in FOLDERS:
        mine = [r for r in rels if r.split("/", 1)[0] == f]
        per[f] = {"files": len(mine), "names_sha256": names_digest(mine)}
    return {"format": 1,
            "description": "Names-only digests of corpora/ (sha256 over the sorted rel_paths joined by LF, per "
                           "top folder). Derived from the anchored baseline; lets `hebloc corpora install` check "
                           "and repair file-name encodings before hashing. Do not edit by hand.",
            "files": len(rels), "max_rel_path_chars": max(len(r) for r in rels),
            "non_ascii_names": sum(1 for r in rels if not r.isascii()), "per_folder": per}


def write_names_reference(path: Path = NAMES_PATH) -> dict:
    from hebloc.baseline import anchor_mismatches, read_anchor, read_baseline
    from hebloc.store.io import atomic_write_json

    table = read_baseline(BASELINE_PATH)
    if anchor_mismatches(table, read_anchor(ANCHOR_PATH)):
        raise InstallError("the baseline does not match the anchor: refusing to derive a names reference")
    ref = names_from_baseline(table)
    atomic_write_json(ref, path)
    return ref


def read_names_reference(path: Path = NAMES_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ sources → entries

@dataclass
class Entry:
    name: str                              # posix path inside the source, as the source decodes it
    size: int
    open: Callable[[], object]             # -> binary file object
    origin: str                            # which download / part it came from
    move_from: Path | None = None          # a file WE extracted into staging (moved, not copied)


def _safe_parts(name: str) -> tuple[str, ...]:
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    parts = tuple(x for x in p.parts if x not in ("", "."))
    if p.is_absolute() or ".." in parts or (parts and ":" in parts[0]):
        raise InstallError(f"unsafe path in the download: {name!r}")
    return parts


def _folder_entries(root: Path, origin: str, moved: bool = False) -> list[Entry]:
    from hebloc.baseline import iter_files

    lr = _long(root)
    out = []
    for st in iter_files(lr):
        f = lr / st.rel_path
        out.append(Entry(st.rel_path, st.size, (lambda f=f: open(f, "rb")), origin, f if moved else None))
    return out


def _zip_entries(path: Path, stack: ExitStack) -> list[Entry]:
    zf = stack.enter_context(zipfile.ZipFile(_long(path)))
    out = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        out.append(Entry(info.filename, info.file_size, (lambda i=info: zf.open(i)), str(path)))
    return out


def _tar_entries(path: Path, stack: ExitStack) -> list[Entry]:
    tf = stack.enter_context(tarfile.open(_long(path)))
    out = []
    for m in tf.getmembers():
        if m.issym() or m.islnk():
            raise InstallError(f"links are not allowed in the corpora archive: {m.name!r}")
        if m.isfile():
            out.append(Entry(m.name, m.size, (lambda m=m: tf.extractfile(m)), str(path)))
    return out


def bsdtar() -> str | None:
    """libarchive's bsdtar: Windows 10+ ships it as System32\\tar.exe; macOS as /usr/bin/tar."""
    cands = []
    if WINDOWS:
        cands.append(str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"))
    cands += [shutil.which("bsdtar"), shutil.which("tar")]
    for c in cands:
        if c and Path(c).exists():
            try:
                v = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=20).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if "bsdtar" in v or "libarchive" in v:
                return c
    return None


def _bsdtar_extract(path: Path, into: Path) -> None:
    tool = bsdtar()
    if tool is None:
        raise InstallError(f"cannot open {path.name}: no bsdtar found. Extract it with 7-Zip and give the "
                           "extracted folder instead")
    into.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([tool, "-xf", str(path.resolve()), "-C", str(into)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise InstallError(f"extracting {path.name} failed: {r.stderr.strip()[-500:]}")


def _source_entries(src: Path, stack: ExitStack, scratch: Path, counter: list[int]) -> list[Entry]:
    name = src.name.lower()
    if src.is_dir():
        return _folder_entries(src, str(src))
    if not src.is_file():
        raise InstallError(f"{src} does not exist")
    if name.endswith(".zip") or (not _is_archive(name) and zipfile.is_zipfile(src)):
        return _zip_entries(src, stack)
    if name.endswith(TAR_SUFFIXES):
        return _tar_entries(src, stack)
    counter[0] += 1
    out = scratch / f"x{counter[0]}"
    _bsdtar_extract(src, out)
    return _folder_entries(out, str(src), moved=True)


# ------------------------------------------------------------------ locate the corpora root

def _find_root(entries: list[Entry]) -> tuple[tuple[str, ...] | None, list[tuple[str, ...]]]:
    """The directory prefix that contains all five corpus folders (shallowest wins)."""
    seen: dict[tuple[str, ...], set[str]] = {}
    for e in entries:
        parts = _safe_parts(e.name)
        for i, part in enumerate(parts[:-1]):
            if part in FOLDERS:
                seen.setdefault(parts[:i], set()).add(part)
    roots = sorted((r for r, fs in seen.items() if len(fs) == len(FOLDERS)), key=lambda r: (len(r), r))
    if not roots:
        return None, []
    shallow = [r for r in roots if len(r) == len(roots[0])]
    return roots[0], shallow


def find_root(base: Path, max_depth: int = 3) -> Path | None:
    """(Folder API kept for tests and doctor.) The directory under ``base`` holding all five folders."""
    base = Path(base)
    frontier = [base]
    for _ in range(max_depth + 1):
        nxt = []
        for d in frontier:
            if all((d / f).is_dir() for f in FOLDERS):
                return d
            nxt += [c for c in sorted(d.iterdir()) if c.is_dir()] if d.is_dir() else []
        frontier = nxt
    return None


# ------------------------------------------------------------------ name repair

def _transforms() -> list[tuple[str, Callable[[str], str]]]:
    def recode(wrong: str, right: str) -> Callable[[str], str]:
        def f(s: str) -> str:
            return s if s.isascii() else s.encode(wrong).decode(right)
        return f

    base: list[tuple[str, Callable[[str], str]]] = [("as-is", lambda s: s)]
    for wrong in ("cp437", "cp850", "cp862", "cp1252"):
        for right in ("utf-8", "cp1255", "cp862"):
            if wrong != right:
                base.append((f"{wrong}->{right}", recode(wrong, right)))
    out = []
    for label, f in base:
        out.append((label, f))
        out.append((label + "+NFC", lambda s, f=f: unicodedata.normalize("NFC", f(s))))
    return out


def choose_names(rels: list[str], ref: dict) -> tuple[str | None, Callable[[str], str] | None, dict]:
    """The first decoding under which every folder's names digest equals the reference."""
    by_folder: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for r in rels:
        by_folder.setdefault(r.split("/", 1)[0], []).append(r)
    ascii_only = {f: all(r.isascii() for r in by_folder[f]) for f in FOLDERS}
    cache: dict[str, bool] = {}                  # ASCII-only folders give the same answer for every decoding
    best, best_n = None, -1
    for label, f in _transforms():
        per = {}
        try:
            for folder in FOLDERS:
                if ascii_only[folder] and folder in cache:
                    match = cache[folder]
                else:
                    match = names_digest(f(r) for r in by_folder[folder]) == ref["per_folder"][folder]["names_sha256"]
                    if ascii_only[folder]:
                        cache[folder] = match
                per[folder] = {"files": len(by_folder[folder]), "expected_files": ref["per_folder"][folder]["files"],
                               "names_match": match}
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        n_ok = sum(d["names_match"] for d in per.values())
        if n_ok == len(FOLDERS):
            return label, f, per
        if n_ok > best_n:
            best, best_n = per, n_ok
    return None, None, best or {}


# ------------------------------------------------------------------ verify / install

def _hash_and_compare(root: Path, workers: int, anchor_path: Path):
    from hebloc.baseline import anchor_mismatches, compute_baseline, read_anchor

    table = compute_baseline(_long(root), workers=workers)
    return table, anchor_mismatches(table, read_anchor(anchor_path))


def verify(root: Path = CORPORA_DIR, *, workers: int = 8, write: bool = True,
           baseline_path: Path = BASELINE_PATH, anchor_path: Path = ANCHOR_PATH) -> dict:
    """Hash every file under ``root`` and compare with the anchor (writes the baseline if equal)."""
    from hebloc.baseline import write_baseline

    table, problems = _hash_and_compare(root, workers, anchor_path)
    if not problems and write:
        write_baseline(table, baseline_path, force=True)
    return {"ok": not problems, "files": table.num_rows,
            "bytes": int(sum(table.column("size").to_pylist())), "problems": problems[:20]}


def install(sources: Path | list[Path], dest: Path = CORPORA_DIR, *, workers: int = 8,
            baseline_path: Path = BASELINE_PATH, anchor_path: Path = ANCHOR_PATH,
            names_path: Path = NAMES_PATH, progress: bool = True) -> dict:
    """Extract/copy the download into a staging folder, check names, hash, and only then create ``dest``."""
    from hebloc.baseline import compare_to_baseline, read_anchor, read_baseline

    sources = [Path(s) for s in ([sources] if isinstance(sources, (str, Path)) else sources)]
    dest = Path(dest).absolute()
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} already exists and is not empty: corpora are never overwritten. "
                              "Run `uv run hebloc corpora verify` to check it instead.")
    ref = read_names_reference(names_path)
    anchor = read_anchor(anchor_path)
    longest = len(str(dest)) + 1 + ref["max_rel_path_chars"]
    if longest > 259 and not long_paths_enabled():
        raise InstallError(f"the project folder path is too long for Windows: corpora file paths would reach "
                           f"{longest} characters (limit 259). Clone the repository into a shorter folder, e.g. "
                           f"C:\\hebloc\\hebrew-locative-verbs, and start again")
    for s in sources:
        r = s.resolve()
        if r == dest.resolve() or dest.resolve() in r.parents:
            raise InstallError("the download must be outside the project's corpora/ folder")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging_root = dest.parent / STAGING_NAME
    shutil.rmtree(_long(staging_root), ignore_errors=True)       # leftovers of an interrupted install (ours)
    staging_root.mkdir()
    free = shutil.disk_usage(staging_root).free
    need = 2 * anchor["total_bytes"] + (1 << 30)
    if free < need:
        shutil.rmtree(_long(staging_root), ignore_errors=True)
        raise InstallError(f"not enough free disk space: {free / 2**30:.1f} GB free, need {need / 2**30:.1f} GB")

    report: dict = {"from": [str(s) for s in sources], "installed": None}
    try:
        with ExitStack() as stack:
            scratch = staging_root / "x"
            counter = [0]
            # A single folder that holds archive parts (e.g. Google Drive's -001.zip, -002.zip) and no corpus
            # folders yet: use the archives in it.
            expanded: list[Path] = []
            for s in sources:
                if s.is_dir() and find_root(s) is None:
                    parts = sorted(p for p in s.iterdir() if p.is_file() and _is_archive(p.name))
                    expanded += parts or [s]
                else:
                    expanded.append(s)
            entries: list[Entry] = []
            for s in expanded:
                entries += _source_entries(s, stack, scratch, counter)
            nested_rounds = 0
            root, shallow = _find_root(entries)
            while root is None and nested_rounds < 2:
                inner = [e for e in entries if _is_archive(e.name)]
                if not inner:
                    break
                nested_rounds += 1
                for e in inner:
                    counter[0] += 1
                    tmp = scratch / f"a{counter[0]}{''.join(PurePosixPath(e.name).suffixes[-2:])}"
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    with e.open() as src, open(_long(tmp), "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    entries += _source_entries(tmp, stack, scratch, counter)
                root, shallow = _find_root(entries)
            if root is None:
                raise InstallError(f"could not find a folder containing {', '.join(FOLDERS)} in the download. "
                                   "Is the download complete (all parts)? Give the path of the archive file, or "
                                   "of the folder that holds all its parts")
            if len(shallow) > 1:
                raise InstallError(f"the download contains more than one copy of the corpora: {['/'.join(r) or '.' for r in shallow]}")
            report["root_in_download"] = "/".join(root) or "."
            n = len(root)
            chosen: dict[str, Entry] = {}
            junk, dup = [], 0
            for e in entries:
                parts = _safe_parts(e.name)
                if parts[:n] != root or len(parts) <= n + 1 or parts[n] not in FOLDERS:
                    continue
                if _is_junk(parts):
                    junk.append("/".join(parts))
                    continue
                rel = "/".join(parts[n:])
                if rel in chosen:
                    if chosen[rel].size != e.size:
                        raise InstallError(f"two parts of the download disagree about {rel} "
                                           f"({chosen[rel].origin} vs {e.origin})")
                    dup += 1
                    continue
                chosen[rel] = e
            report.update({"ignored_os_files": len(junk), "ignored_os_examples": junk[:5], "duplicate_entries": dup,
                           "files_found": len(chosen)})
            label, fix, per = choose_names(list(chosen), ref)
            report["names"] = {"decoding": label, "per_folder": per}
            if fix is None:
                bad = {f: d for f, d in per.items() if not d["names_match"]}
                raise InstallError("the file names in the download are not the project's corpora (no encoding "
                                   f"repair makes them match). Per folder: {bad}. Is this the right, complete download?")
            size_by = {}
            for rel, e in chosen.items():
                size_by[rel.split("/", 1)[0]] = size_by.get(rel.split("/", 1)[0], 0) + e.size
            exp = {f: anchor["per_corpus"][f]["bytes"] for f in FOLDERS}
            if size_by != exp:
                raise InstallError(f"the download's sizes differ from the project's corpora: {size_by} vs {exp}")

            target = staging_root / "corpora"
            lt = _long(target)
            made: set[Path] = set()
            items = list(chosen.items())
            bar = None
            if progress:
                from tqdm import tqdm
                bar = tqdm(total=sum(e.size for _, e in items), unit="B", unit_scale=True, desc="extract")
            for rel, e in items:
                out = lt / fix(rel)
                if out.parent not in made:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    made.add(out.parent)
                if e.move_from is not None:
                    os.replace(e.move_from, out)
                else:
                    with e.open() as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                if bar:
                    bar.update(e.size)
            if bar:
                bar.close()

        table, problems = _hash_and_compare(target, workers, anchor_path)
        report["verify"] = {"ok": not problems, "files": table.num_rows,
                            "bytes": int(sum(table.column("size").to_pylist())), "problems": problems[:20]}
        if problems:
            return report                                   # nothing installed; staging removed below
        if dest.exists():
            dest.rmdir()                                    # empty placeholder only
        os.replace(lt, _long(dest))
        from hebloc.baseline import write_baseline

        write_baseline(table, baseline_path, force=True)
        drift = compare_to_baseline(read_baseline(baseline_path), dest, deep=False)
        report["installed"] = str(dest)
        report["after_move_unchanged"] = drift.clean
        report["verify"]["ok"] = drift.clean
    finally:
        shutil.rmtree(_long(staging_root), ignore_errors=True)
    return report
