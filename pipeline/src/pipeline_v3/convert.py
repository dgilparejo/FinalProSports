"""Deterministic document conversion for the v3 rebuild (principle 1: convert for real, never read bytes).

Every source document is routed by its **magic bytes**, not by its extension -- the corpus contains ``.doc`` files that
are really RTF, ``.doc`` files that are really OLE2, and ``.pdf`` files named ``35812.pdf``. Each conversion returns a
:class:`Conversion` record that always says what happened, so a failure is listed rather than silently producing "".

Converters, in order of preference and why:

* ``odt`` / ``docx`` / ``odt#``: the standard library. Both are ZIP + XML; parsing the XML directly preserves
  paragraphs, tabs, line breaks and *table cells*, which every "strip the tags" approach loses.
* ``rtf``: :mod:`pipeline_v3.rtf`, written for this rebuild (see that module).
* ``doc`` (OLE2, Word 97-2003): ``antiword``. Chosen over LibreOffice headless because it is already present in the
  reference machine's Git-for-Windows toolchain, needs no user profile, no lock files and no GUI, and converts in
  milliseconds instead of seconds. It is a single deterministic binary, so a clean clone reproduces it. Files antiword
  refuses (Word 6.0 and a handful of damaged headers) fall back to an OLE2 + WordDocument-stream reader implemented
  here, and anything still failing is reported, never guessed at.
* ``pdf``: ``pdftotext -layout`` (poppler/xpdf), same reasoning.

Converted text is cached under ``work_dir()/text`` keyed by the source SHA-1, so re-running any later stage costs
nothing and the conversion is reproducible byte for byte.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from xml.etree import ElementTree

from . import rtf as rtf_reader
from .paths import work_dir

ANTIWORD = shutil.which("antiword")
PDFTOTEXT = shutil.which("pdftotext")

_ODF_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_ODF_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_ODF_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass
class Conversion:
    """One source document, converted or not. ``status`` is never empty."""

    path: str
    sha1: str
    size_bytes: int
    ext: str
    detected: str            # magic-byte format: odt | docx | rtf | doc_ole | pdf | zip_other | text | unknown | empty
    converter: str           # which converter ran
    status: str              # ok | empty_output | failed | skipped_media | skipped_lock | unsupported
    chars: int = 0
    lines: int = 0
    error: str = ""
    text_cache: str = ""     # file name under work_dir()/text
    notes: list[str] = field(default_factory=list)
    scrubbed: dict = field(default_factory=dict)   # PII substitutions applied before the text hit the disk
    residual_name_tokens: int = 0                  # roster tokens still present afterwards (must trend to zero)

    def to_json(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------------------- magic-byte detection

def sniff(path: Path) -> str:
    """Detect the real format from the first bytes (and, for ZIPs, from the entries)."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(8)
    except OSError:
        return "unreadable"
    if not head:
        return "empty"
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "doc_ole"
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:5] == b"{\\rtf":
        return "rtf"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
        except Exception:
            return "zip_broken"
        if "word/document.xml" in names:
            return "docx"
        if "content.xml" in names:
            return "odt"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        return "zip_other"
    if head[:2] in (b"\xff\xd8",) or head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if head[:4] in (b".snd", b"RIFF", b"ID3\x03", b"ID3\x04"):
        return "audio"
    # Some Bean/Word exports start with whitespace before the RTF header.
    try:
        with open(path, "rb") as handle:
            probe = handle.read(512)
    except OSError:
        return "unreadable"
    if b"{\\rtf" in probe[:64]:
        return "rtf"
    try:
        probe.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "unknown"


# --------------------------------------------------------------------------------------- ODF / OOXML

def _odf_walk(node, out: list[str]) -> None:
    tag = node.tag
    if tag == f"{{{_ODF_TEXT}}}tab":
        out.append("\t")
    elif tag == f"{{{_ODF_TEXT}}}line-break":
        out.append("\n")
    elif tag == f"{{{_ODF_TEXT}}}s":
        out.append(" " * int(node.get(f"{{{_ODF_TEXT}}}c", "1") or 1))
    if node.text:
        out.append(node.text)
    for child in node:
        _odf_walk(child, out)
        if child.tail:
            out.append(child.tail)
    if tag in (f"{{{_ODF_TEXT}}}p", f"{{{_ODF_TEXT}}}h"):
        out.append("\n")
    elif tag == f"{{{_ODF_TABLE}}}table-cell":
        out.append(" | ")
    elif tag == f"{{{_ODF_TABLE}}}table-row":
        out.append("\n")


def from_odt(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        parts = [n for n in ("content.xml",) if n in names]
        if not parts:
            raise ValueError("no content.xml")
        chunks: list[str] = []
        for name in parts:
            root = ElementTree.fromstring(zf.read(name))
            body = root.find(f"{{urn:oasis:names:tc:opendocument:xmlns:office:1.0}}body")
            out: list[str] = []
            _odf_walk(body if body is not None else root, out)
            chunks.append("".join(out))
    return "\n".join(chunks)


def _docx_walk(node, out: list[str]) -> None:
    tag = node.tag
    if tag == f"{{{_W}}}tab":
        out.append("\t")
    elif tag == f"{{{_W}}}br" or tag == f"{{{_W}}}cr":
        out.append("\n")
    elif tag == f"{{{_W}}}t":
        out.append(node.text or "")
    for child in node:
        _docx_walk(child, out)
    if tag == f"{{{_W}}}p":
        out.append("\n")
    elif tag == f"{{{_W}}}tc":
        out.append(" | ")
    elif tag == f"{{{_W}}}tr":
        out.append("\n")


def from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ElementTree.fromstring(zf.read("word/document.xml"))
    out: list[str] = []
    _docx_walk(root, out)
    return "".join(out)


# --------------------------------------------------------------------------------------- Word 97 (OLE2) fallback

def _ole_streams(data: bytes) -> dict[str, bytes]:
    """Minimal OLE2/CFB reader: returns the named streams of the root storage.

    Only used when ``antiword`` refuses a file; it is a fallback, not the primary path.
    """
    if len(data) < 512 or data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError("not an OLE2 container")
    sector_shift = struct.unpack_from("<H", data, 30)[0]
    mini_shift = struct.unpack_from("<H", data, 32)[0]
    sector_size = 1 << sector_shift
    mini_size = 1 << mini_shift
    num_fat = struct.unpack_from("<I", data, 44)[0]
    dir_start = struct.unpack_from("<I", data, 48)[0]
    mini_cutoff = struct.unpack_from("<I", data, 56)[0]
    mini_fat_start = struct.unpack_from("<I", data, 60)[0]
    difat_start = struct.unpack_from("<I", data, 68)[0]
    num_difat = struct.unpack_from("<I", data, 72)[0]

    def sector_offset(sid: int) -> int:
        return 512 + sid * sector_size

    difat = list(struct.unpack_from("<109I", data, 76))
    sid = difat_start
    for _ in range(num_difat):
        if sid >= 0xFFFFFFFA:
            break
        off = sector_offset(sid)
        entries = struct.unpack_from("<%dI" % (sector_size // 4), data, off)
        difat.extend(entries[:-1])
        sid = entries[-1]

    fat: list[int] = []
    for fsid in difat[:num_fat]:
        if fsid >= 0xFFFFFFFA:
            continue
        off = sector_offset(fsid)
        fat.extend(struct.unpack_from("<%dI" % (sector_size // 4), data, off))

    def chain(start: int, limit: int = 1_000_000) -> list[int]:
        out, cur, seen = [], start, set()
        while cur < 0xFFFFFFFA and len(out) < limit:
            if cur in seen or cur >= len(fat):
                break
            seen.add(cur)
            out.append(cur)
            cur = fat[cur]
        return out

    def read_chain(start: int, size: int | None = None) -> bytes:
        buf = b"".join(data[sector_offset(s): sector_offset(s) + sector_size] for s in chain(start))
        return buf[:size] if size is not None else buf

    dir_bytes = read_chain(dir_start)
    entries = []
    for i in range(0, len(dir_bytes) - 127, 128):
        raw = dir_bytes[i:i + 128]
        name_len = struct.unpack_from("<H", raw, 64)[0]
        if name_len < 2:
            entries.append(("", 0, 0, 0))
            continue
        name = raw[:name_len - 2].decode("utf-16-le", "replace")
        etype = raw[66]
        start = struct.unpack_from("<I", raw, 116)[0]
        size = struct.unpack_from("<I", raw, 120)[0]
        entries.append((name, etype, start, size))

    root = next((e for e in entries if e[1] == 5), None)
    mini_stream = read_chain(root[2]) if root and root[2] < 0xFFFFFFFA else b""
    mini_fat_bytes = read_chain(mini_fat_start) if mini_fat_start < 0xFFFFFFFA else b""
    mini_fat = list(struct.unpack_from("<%dI" % (len(mini_fat_bytes) // 4), mini_fat_bytes, 0)) if mini_fat_bytes else []

    def read_mini(start: int, size: int) -> bytes:
        out, cur, seen = [], start, set()
        while cur < 0xFFFFFFFA and cur < len(mini_fat) and cur not in seen:
            seen.add(cur)
            out.append(mini_stream[cur * mini_size:(cur + 1) * mini_size])
            cur = mini_fat[cur]
        return b"".join(out)[:size]

    streams: dict[str, bytes] = {}
    for name, etype, start, size in entries:
        if etype != 2 or not name:
            continue
        streams[name] = read_mini(start, size) if size < mini_cutoff else read_chain(start, size)
    return streams


def from_doc_ole_fallback(path: Path) -> str:
    """Read the text of a Word 97-2003 document from its WordDocument stream and piece table."""
    data = path.read_bytes()
    streams = _ole_streams(data)
    wd = streams.get("WordDocument")
    if not wd:
        raise ValueError("no WordDocument stream")
    flags = struct.unpack_from("<H", wd, 10)[0]
    table_name = "1Table" if (flags & 0x0200) else "0Table"
    table = streams.get(table_name) or streams.get("0Table") or streams.get("1Table")
    fc_min = struct.unpack_from("<i", wd, 24)[0]
    ccp_text = struct.unpack_from("<i", wd, 76)[0]
    if not table:
        return wd[fc_min:fc_min + max(ccp_text, 0)].decode("cp1252", "replace")
    fc_clx = struct.unpack_from("<I", wd, 418)[0]
    lcb_clx = struct.unpack_from("<I", wd, 422)[0]
    clx = table[fc_clx:fc_clx + lcb_clx]
    # Walk the Clx: skip Prc entries (0x01), stop at the Pcdt (0x02).
    pos = 0
    pcdt = b""
    while pos < len(clx):
        if clx[pos] == 0x01:
            size = struct.unpack_from("<h", clx, pos + 1)[0]
            pos += 3 + size
        elif clx[pos] == 0x02:
            size = struct.unpack_from("<I", clx, pos + 1)[0]
            pcdt = clx[pos + 5:pos + 5 + size]
            break
        else:
            break
    if not pcdt:
        return wd[fc_min:fc_min + max(ccp_text, 0)].decode("cp1252", "replace")
    n = (len(pcdt) - 4) // 12
    cps = list(struct.unpack_from("<%dI" % (n + 1), pcdt, 0))
    out: list[str] = []
    for i in range(n):
        off = 4 * (n + 1) + i * 8
        fc = struct.unpack_from("<I", pcdt, off + 2)[0]
        compressed = bool(fc & 0x40000000)
        fc &= 0x3FFFFFFF
        length = cps[i + 1] - cps[i]
        if compressed:
            chunk = wd[fc // 2: fc // 2 + length]
            out.append(chunk.decode("cp1252", "replace"))
        else:
            chunk = wd[fc: fc + length * 2]
            out.append(chunk.decode("utf-16-le", "replace"))
    text = "".join(out)
    # Word control characters -> readable separators.
    text = text.replace("\r", "\n").replace("\x07", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    text = text.replace("\x1e", "-").replace("\x1f", "").replace("\x13", "").replace("\x14", "").replace("\x15", "")
    return text


@contextlib.contextmanager
def _ascii_copy(path: Path):
    """Yield an ASCII-only path to the same bytes.

    Both external converters are old Win32 binaries that open their argument with the *ANSI* API: every source path
    here contains accented characters (the corpus lives under ``Educacion``/``Master`` spelled with accents), and
    xpdf 4.00 fails all 488 PDFs with ``I/O Error: Couldn't open file``. Copying to a plain temp name is the only
    thing that makes them reproducible, and it costs one file copy.
    """
    tmpdir = tempfile.mkdtemp(prefix="fps_v3_")
    try:
        target = Path(tmpdir) / ("src" + path.suffix.lower())
        shutil.copy2(path, target)
        yield target
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def from_doc(path: Path) -> tuple[str, str, str]:
    """Return ``(text, converter, note)``. Tries antiword first, then the in-process OLE reader."""
    note = ""
    if ANTIWORD:
        env = dict(os.environ)
        env.setdefault("ANTIWORDHOME", str(Path(ANTIWORD).parent.parent / "share" / "antiword"))
        try:
            with _ascii_copy(path) as tmp:
                proc = subprocess.run(
                    [ANTIWORD, "-m", "UTF-8.txt", "-w", "0", str(tmp)],
                    capture_output=True, timeout=120, env=env,
                )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.decode("utf-8", "replace"), "antiword", note
            note = (proc.stderr.decode("utf-8", "replace").strip() or f"antiword rc={proc.returncode}")[:200]
        except subprocess.TimeoutExpired:
            note = "antiword timeout"
        except Exception as exc:  # pragma: no cover - defensive
            note = f"antiword {type(exc).__name__}: {exc}"[:200]
    text = from_doc_ole_fallback(path)
    return text, "ole_piece_table", note


def from_pdf(path: Path) -> tuple[str, str]:
    if not PDFTOTEXT:
        raise RuntimeError("pdftotext not available")
    with _ascii_copy(path) as tmp:
        proc = subprocess.run(
            [PDFTOTEXT, "-layout", "-enc", "UTF-8", "-nopgbrk", str(tmp), "-"],
            capture_output=True, timeout=300,
        )
    text = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace").strip()
    if proc.returncode != 0 and not text.strip():
        raise RuntimeError(err[:200] or f"pdftotext rc={proc.returncode}")
    return text, err[:200]


def from_xlsx(path: Path) -> str:
    """Minimal spreadsheet reader: shared strings plus inline values, one row per line, cells joined with `` | ``."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            for si in root.findall(f"{ns}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{ns}t")))
        lines: list[str] = []
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        for sheet in sorted(n for n in names if n.startswith("xl/worksheets/sheet")):
            root = ElementTree.fromstring(zf.read(sheet))
            for row in root.iter(f"{ns}row"):
                cells: list[str] = []
                for cell in row.findall(f"{ns}c"):
                    value = cell.find(f"{ns}v")
                    text = value.text if value is not None else ""
                    if cell.get("t") == "s" and text and text.isdigit():
                        text = shared[int(text)] if int(text) < len(shared) else ""
                    if cell.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(f"{ns}t"))
                    cells.append((text or "").strip())
                if any(cells):
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------- normalisation + driver

_CONTROL = {c: None for c in range(32) if c not in (9, 10)}


def normalise(text: str) -> str:
    """Whitespace and control-character clean-up. Deliberately conservative: no word joining, no case changes."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_CONTROL)
    text = unicodedata.normalize("NFC", text)
    text = text.replace(" ", " ").replace("​", "")
    text = text.expandtabs(4)
    text = re.sub(r" {9,}", " " * 8, text)
    text = re.sub(r"[ ]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_dir() -> Path:
    d = work_dir() / "text"
    d.mkdir(parents=True, exist_ok=True)
    return d


MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".au", ".mp3", ".wav", ".aup", ".m4a", ".ogg"}
LOCK_PREFIX = ".~lock"


def convert_file(path: Path, use_cache: bool = True, registry=None, code: str | None = None) -> Conversion:
    """Convert one document.

    When ``registry`` is given the text is anonymised *before* it is written to the cache, so no file on disk ever
    holds a real name, e-mail or phone (las reglas de manejo de datos personales de la memoria, rules 1 and 6). Callers that omit it get raw text in memory only.
    """
    ext = path.suffix.lower()
    size = path.stat().st_size
    if path.name.startswith(LOCK_PREFIX) or ext.endswith("#"):
        # LibreOffice lock files: `.~lock.foo.odt#` and the stray `foo.odt#` leftovers.
        if path.name.startswith(LOCK_PREFIX):
            return Conversion(str(path), "", size, ext, "lock", "-", "skipped_lock")
    sha = sha1_of(path)
    cache = text_dir() / f"{sha}.txt"
    detected = sniff(path)

    if ext in MEDIA_EXT or detected in ("image", "audio"):
        return Conversion(str(path), sha, size, ext, detected, "-", "skipped_media")

    if use_cache and cache.exists():
        text = cache.read_text(encoding="utf-8")
        meta_path = text_dir() / f"{sha}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return Conversion(
            str(path), sha, size, ext, detected, meta.get("converter", "cache"),
            "ok" if text.strip() else "empty_output", len(text), text.count("\n") + 1,
            meta.get("error", ""), cache.name, meta.get("notes", []),
            meta.get("scrubbed", {}), meta.get("residual_name_tokens", 0),
        )

    notes: list[str] = []
    converter, error, text = "-", "", ""
    try:
        if detected == "odt":
            text, converter = from_odt(path), "stdlib_odf"
        elif detected == "docx":
            text, converter = from_docx(path), "stdlib_ooxml"
        elif detected == "rtf":
            text, converter = rtf_reader.read_rtf_file(path), "stdlib_rtf"
        elif detected == "doc_ole":
            text, converter, note = from_doc(path)
            if note:
                notes.append(note)
        elif detected == "pdf":
            text, warn = from_pdf(path)
            converter = "pdftotext"
            if warn:
                notes.append(warn)
        elif detected == "xlsx":
            text, converter = from_xlsx(path), "stdlib_xlsx"
        elif detected == "text":
            text, converter = path.read_text(encoding="utf-8", errors="replace"), "plain"
        elif detected == "empty":
            return Conversion(str(path), sha, size, ext, detected, "-", "failed", error="zero-byte file")
        else:
            return Conversion(str(path), sha, size, ext, detected, "-", "unsupported",
                              error=f"no converter for detected format {detected!r}")
    except Exception as exc:
        return Conversion(str(path), sha, size, ext, detected, converter or "-", "failed",
                          error=f"{type(exc).__name__}: {exc}"[:300], notes=notes)

    text = normalise(text)
    scrub: dict[str, int] = {}
    residual = 0
    if registry is not None:
        text, scrub = registry.anonymise(text, code)
        residual = len(registry.residual_name_tokens(text))
    cache.write_text(text, encoding="utf-8", newline="\n")
    (text_dir() / f"{sha}.json").write_text(
        json.dumps({"converter": converter, "error": error, "notes": notes,
                    "scrubbed": scrub, "residual_name_tokens": residual}, ensure_ascii=False),
        encoding="utf-8", newline="\n",
    )
    return Conversion(
        str(path), sha, size, ext, detected, converter,
        "ok" if text.strip() else "empty_output", len(text), text.count("\n") + 1,
        error, cache.name, notes, scrub, residual,
    )


def cached_text(sha1: str) -> str:
    path = text_dir() / f"{sha1}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""
