"""A self-contained RTF-to-text reader (standard library only).

The v2 ingest used ``striprtf``; the rebuild avoids the dependency so that a clean clone can convert the corpus with
nothing but Python, ``antiword`` and ``pdftotext``. It implements the parts of RTF 1.9 the corpus actually uses:
group nesting, control words with numeric parameters, code-page hex escapes, Unicode escapes with the ``\\ucN``
skip count, the destinations that must be dropped whole (font and colour tables, style sheets, embedded pictures
and OLE objects), and the paragraph/tab/table separators.

Table cells are joined with `` | `` and rows end with a newline, so a diet laid out as a table survives as one line
per row instead of collapsing into a wall of words -- which is how several of this corpus' diets are written.
"""
from __future__ import annotations

import re

# Destinations whose whole group is discarded. ``\*\foo`` groups are dropped as well unless listed in _KEEP_STAR.
_SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "listtable", "listoverridetable", "revtbl", "rsidtbl",
    "info", "pict", "object", "objdata", "result0", "themedata", "datastore", "latentstyles",
    "generator", "filetbl", "xmlnstbl", "mmathPr", "wgrffmtfilter", "sn", "sv", "shpinst",
    "nonshppict", "blipuid", "panose", "falt", "fname", "bkmkstart", "bkmkend", "atnid",
    "atnauthor", "annotation", "atnref", "atntime", "atnparent", "template", "operator",
    "company", "hlinkbase", "userprops", "protusertbl", "flymaincnt", "docvar", "pntxtb", "pntxta",
}
# ``\*\...`` destinations whose content is real document text.
_KEEP_STAR = {"result"}

_CODEPAGES = {
    437: "cp437", 850: "cp850", 852: "cp852", 866: "cp866", 874: "cp874", 932: "cp932",
    936: "gbk", 949: "cp949", 950: "cp950", 1250: "cp1250", 1251: "cp1251", 1252: "cp1252",
    1253: "cp1253", 1254: "cp1254", 1255: "cp1255", 1256: "cp1256", 1257: "cp1257", 1258: "cp1258",
    10000: "mac_roman", 65001: "utf-8",
}
# ANSI is the practical default for this corpus (Spanish Word/Bean documents).
_DEFAULT_CODEPAGE = "cp1252"

_BREAK_WORDS = {"par": "\n", "line": "\n", "sect": "\n", "page": "\n", "softline": "\n", "row": "\n", "nestrow": "\n"}
_CELL_WORDS = {"cell": " | ", "nestcell": " | "}
_LITERAL_WORDS = {
    "tab": "\t", "emdash": "\u2014", "endash": "\u2013", "emspace": " ", "enspace": " ",
    "qmspace": " ", "bullet": "\u2022", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "nbsp": "\u00a0",
}
_LITERAL_SYMBOLS = {"~": "\u00a0", "-": "", "_": "-", "\n": "\n", "\r": "\n"}

_TOKEN = re.compile(
    r"\\(?:"
    r"'(?P<hex>[0-9a-fA-F]{2})"
    r"|(?P<word>[a-zA-Z]+)(?P<num>-?\d+)?[ ]?"
    r"|(?P<sym>[^a-zA-Z])"
    r")"
    r"|(?P<open>\{)|(?P<close>\})|(?P<text>[^\\{}]+)"
)


class _State:
    __slots__ = ("uc", "codepage", "skip", "star")

    def __init__(self, uc: int = 1, codepage: str = _DEFAULT_CODEPAGE, skip: bool = False, star: bool = False) -> None:
        self.uc, self.codepage, self.skip, self.star = uc, codepage, skip, star

    def copy(self) -> "_State":
        return _State(self.uc, self.codepage, self.skip, self.star)


def rtf_to_text(raw: str) -> str:
    """Convert RTF source to plain text. Never raises: malformed input yields whatever text could be recovered."""
    out: list[str] = []
    stack: list[_State] = []
    st = _State()
    # A document-level code page applies to everything; read it up front rather than relying on token order.
    header = raw[:4096]
    m = re.search(r"\\ansicpg(\d+)", header)
    if m:
        st.codepage = _CODEPAGES.get(int(m.group(1)), _DEFAULT_CODEPAGE)
    elif re.search(r"\\mac\b", header):
        st.codepage = "mac_roman"

    pending_unicode_skip = 0
    pending_bytes = bytearray()

    def flush_bytes() -> None:
        if pending_bytes:
            out.append(pending_bytes.decode(st.codepage, "replace"))
            del pending_bytes[:]

    for tok in _TOKEN.finditer(raw):
        if tok.group("open") is not None:
            flush_bytes()
            stack.append(st.copy())
            st = st.copy()
            st.star = False
            continue
        if tok.group("close") is not None:
            flush_bytes()
            st = stack.pop() if stack else _State()
            pending_unicode_skip = 0
            continue

        hexval = tok.group("hex")
        if hexval is not None:
            if st.skip:
                continue
            if pending_unicode_skip > 0:
                pending_unicode_skip -= 1
                continue
            pending_bytes.append(int(hexval, 16))
            continue

        word = tok.group("word")
        if word is not None:
            flush_bytes()
            num = tok.group("num")
            value = int(num) if num else None
            if word == "uc":
                st.uc = max(0, value or 0)
                continue
            if word == "u":
                if st.skip:
                    pending_unicode_skip = st.uc
                    continue
                cp = value if value is not None else 0
                if cp < 0:
                    cp += 65536
                if 0 < cp < 0x110000:
                    out.append(chr(cp))
                pending_unicode_skip = st.uc
                continue
            if pending_unicode_skip > 0:
                pending_unicode_skip -= 1
                continue
            if word == "ansicpg" and value is not None:
                st.codepage = _CODEPAGES.get(value, _DEFAULT_CODEPAGE)
                continue
            if word in _SKIP_DESTINATIONS or (st.star and word not in _KEEP_STAR):
                st.skip = True
                st.star = False
                continue
            if st.skip:
                continue
            if word in _BREAK_WORDS:
                out.append(_BREAK_WORDS[word])
            elif word in _CELL_WORDS:
                out.append(_CELL_WORDS[word])
            elif word in _LITERAL_WORDS:
                out.append(_LITERAL_WORDS[word])
            continue

        sym = tok.group("sym")
        if sym is not None:
            if sym == "*":
                st.star = True
                continue
            if st.skip:
                continue
            if pending_unicode_skip > 0 and sym not in "{}\\":
                pending_unicode_skip -= 1
                continue
            flush_bytes()
            if sym in "{}\\":
                out.append(sym)
            elif sym in _LITERAL_SYMBOLS:
                out.append(_LITERAL_SYMBOLS[sym])
            continue

        text = tok.group("text")
        if text is not None:
            if st.skip:
                continue
            if pending_unicode_skip > 0:
                consumed = min(pending_unicode_skip, len(text))
                pending_unicode_skip -= consumed
                text = text[consumed:]
                if not text:
                    continue
            # Raw bytes in the stream are code-page bytes too; keep them in the same buffer so a
            # multi-byte sequence split across tokens still decodes.
            pending_bytes.extend(text.encode("latin-1", "replace"))

    flush_bytes()
    return "".join(out)


def read_rtf_file(path) -> str:
    with open(path, "rb") as handle:
        raw = handle.read()
    # Reading as latin-1 keeps byte<->char alignment so the hex escapes still decode against the declared code page.
    return rtf_to_text(raw.decode("latin-1", "replace"))
