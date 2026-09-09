"""Client identity and anonymisation-on-write for the v3 rebuild (F5, applied from the very first stage).

Two rules from `las reglas de manejo de datos personales de la memoria` shape this module:

* rule 1 -- no real name, e-mail or phone is ever printed or written by the pipeline; findings are counts or masked
  tokens;
* rule 6 -- the project tree stays at criterion **zero**, with no per-file exception.

The consequence for a rebuild that starts from documents full of real names is that anonymisation cannot be a late
stage: it runs inside the converter, so the scrubbed text is what reaches the disk cache in the first place. The
mapping from pseudonym to the original folder name is written once, to ``_dataset_v3/_private/id_map.json``, which is
the same private location and the same excluded file name the v2 dataset already uses.

The v3 pseudonym numbering is **its own**: ``CLIENTE_NNN`` here is assigned by sorting the source folders and does not
in general agree with the v2 code for the same person. :mod:`pipeline_v3.compare` resolves the two by name digest, and
``id_map_v2_v3.json`` records the correspondence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .paths import dataset_dir_v2, dataset_dir_v3

_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,}")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\dA-Fa-f])(?:\+?34[\s.-]?)?[6-9]\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}(?![\dA-Fa-f])")
DNI = re.compile(r"(?<![A-Za-z0-9])\d{8}[\s-]?[A-Za-z](?![A-Za-z0-9])")
NIE = re.compile(r"(?<![A-Za-z0-9])[XYZxyz][\s-]?\d{7}[\s-]?[A-Za-z](?![A-Za-z0-9])")
IBAN = re.compile(r"(?<![A-Za-z0-9])ES\s?\d{2}(?:\s?\d{4}){5}(?![0-9])", re.I)
SSN = re.compile(r"(?<!\d)\d{2}[\s/-]?\d{8,10}[\s/-]?\d{2}(?!\d)")
# A full date next to a pseudonymous client is quasi-identifying, and v2 strips it. The diet's own date is kept
# separately in meta.doc_date, where it is a field rather than free text.
FULL_DATE = re.compile(r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)?\d{2}(?!\d)")
URL = re.compile(r"https?://\S+|www\.\S+", re.I)

def _load_professional_tokens() -> tuple[str, frozenset[str]]:
    """Salted digests of the professional's own name, which runs through the whole corpus (author lines, the scale
    export, signatures).

    Stored and matched as **digests, never as literals**. The obvious design -- a small private JSON holding the
    surname -- puts a real name inside ``FPS_DATA_DIR`` and the tree audit finds it, and the answer to that is not a
    new per-file exception (rule 6 admits none) but not writing the name down at all. The digests are seeded once from
    ``FPS_PROFESSIONAL_TOKENS`` and the plaintext is discarded; with no digests available the substitution simply does
    not run, and the count reports zero rather than the scrubber guessing.
    """
    path = dataset_dir_v3() / "_private" / "professional_tokens.json"
    salt, digests = "", set()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        salt = data.get("salt", "")
        digests = set(data.get("token_digests", []))
    env = os.environ.get("FPS_PROFESSIONAL_TOKENS", "")
    tokens = [norm(t.strip()) for t in env.split(",") if t.strip()]
    if tokens:
        salt = salt or hashlib.sha256(("fps-v3-prof:" + "|".join(sorted(tokens))).encode("utf-8")).hexdigest()[:32]
        digests |= {hashlib.sha256((salt + t).encode("utf-8")).hexdigest() for t in tokens}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"salt": salt, "token_digests": sorted(digests),
                        "note": "salted digests of the professional's name tokens; no literal is stored anywhere"},
                       ensure_ascii=False, indent=1),
            encoding="utf-8", newline="\n")
    return salt, frozenset(digests)


# Labels whose VALUE is a person's name. The value runs to the end of the line or to the next label on the same
# line ("Nombre: X  Sexo: Masculino"), whichever comes first.
_LABELLED_NAME = re.compile(
    r"(?im)^(\s*(?:NOMBRE\s+Y\s+APELLIDOS|NOMBRE|APELLIDOS|PACIENTE|CLIENTE|TITULAR|DEPORTISTA|"
    r"FDO\.?|FIRMADO|M[EÉ]DICO(?:/A)?(?:\s+(?:REALIZADOR|SOLICITANTE|PETICIONARIO))?|ENFERMERO(?:/A)?|"
    r"DOCTOR(?:A)?|DR\.?|DRA\.?|ANALIZADOR|REALIZADO\s+POR|SOLICITADO\s+POR|DIRECTOR\s+T[EÉ]CNICO)"
    r"\s*[:.\-]\s*)"
    r"(?!\s*$)[^\n:]{1,80}?(?=\s{2,}[A-ZÁÉÍÓÚÑ][^\n:]{0,30}:|\s*$)"
)

# A capitalised word glued to an identifier that was already substituted is the rest of that same name.
# It must not swallow the NEXT FIELD LABEL: "Nombre: X  Sexo: Masculino" is one line in every lab report, and
# eating "Sexo" would silently cost the extractor a field. A word followed by a colon is a label, never a surname.
_NOT_A_LABEL = r"(?!(?:[A-ZÁÉÍÓÚÑa-záéíóúñ]{2,20}\s*[:.]))"
_NAME_WORD = r"(?:[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ']{1,}|[A-ZÁÉÍÓÚÑ]\.|D[EA]L?|DE|LA|LOS|Mª|M\.)"
_ADJACENT_AFTER = re.compile(
    r"((?:CLIENTE_\d{3}|\[NOMBRE\]|\[PROFESIONAL\])(?:\s*,)?)"
    r"(?:[ \t]+" + _NOT_A_LABEL + _NAME_WORD + r"){1,4}\b"
)
_ADJACENT_BEFORE = re.compile(
    r"(?:\b" + _NOT_A_LABEL + _NAME_WORD + r"[ \t]+){1,4}"
    r"((?:CLIENTE_\d{3}|\[NOMBRE\]|\[PROFESIONAL\]))"
)

_PROFESSIONAL_CACHE: list = []


def _professional() -> tuple[str, frozenset[str]]:
    if not _PROFESSIONAL_CACHE:
        _PROFESSIONAL_CACHE.append(_load_professional_tokens())
    return _PROFESSIONAL_CACHE[0]


def _scrub_professional(text: str) -> tuple[str, int]:
    """Replace whole words whose digest is one of the professional's. Digest comparison, never a literal match."""
    salt, digests = _professional()
    if not digests:
        return text, 0
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        token = norm(match.group(0))
        if hashlib.sha256((salt + token).encode("utf-8")).hexdigest() in digests:
            count += 1
            return "[PROFESIONAL]"
        return match.group(0)

    return _WORD.sub(replace, text), count


# Words allowed to survive verbatim in a masked file name: document kinds, goals, months and structural words.
# An allowlist, so an unexpected word is hashed rather than leaked.
SAFE_FILENAME_WORDS = frozenset({
    "DIETA", "DIETAS", "DIET", "ENTRENO", "ENTRENOS", "ENTRENAMIENTO", "ENTRENAMIENTOS", "RUTINA", "RUTINAS",
    "ANALITICA", "ANALITICAS", "ANALISIS", "DATOS", "PERSONALES", "CUESTIONARIO", "HOJA", "HOJAS", "SEGUIMIENTO",
    "PERFIL", "OTRO", "OTROS", "TXT", "COPIA", "NUEVA", "NUEVO", "FINAL", "REVISADA", "REVISADO", "CORREGIDA",
    "VOLUMEN", "DEFINICION", "MANTENIMIENTO", "MASA", "FUERZA", "HIPERTROFIA", "CETOSIS", "KETO", "AYUNO",
    "PERDER", "GANAR", "TONIFICAR", "PESO", "GRASA", "MUSCULAR", "CARGA", "DESCARGA", "SEMANA", "SEMANAS",
    "DIA", "DIAS", "MES", "MESES", "ANO", "ANOS", "CLIENTE", "PACIENTE", "SEXO", "HOMBRE", "MUJER",
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "SETIEMBRE",
    "OCTUBRE", "NOVIEMBRE", "DICIEMBRE", "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO",
    "BASCULA", "MEDIDAS", "PESAJE", "CONTROL", "INFORME", "RESULTADOS", "PLAN", "PDF", "DOC", "ODT", "RTF", "DOCX",
    "BIS", "TER", "DEF", "PRE", "POST", "ANTIGUA", "ANTIGUO", "VIEJA", "VIEJO", "ACTUAL", "ULTIMA", "ULTIMO",
})

# ``V01``, ``N3``, ``2A``, ``VOL2`` and friends: a version marker, never a name.
_VERSION_TOKEN = re.compile(r"(?:V|N|S|VOL|NUM|Nº|D)?\d{1,3}[A-Z]?|[A-Z]\d{1,3}")


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def norm(text: str) -> str:
    return strip_accents(text).upper()


def mask(token: str) -> str:
    return token[0] + "*" * (len(token) - 1) if token else token


def _stopwords() -> frozenset[str]:
    """Words that look like surnames but are corpus vocabulary. Reuses the reviewed Phase-2 list."""
    try:
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "data_tools"))
        from pii_common import STOPWORDS  # type: ignore
        return frozenset(STOPWORDS)
    except Exception:
        return frozenset()


STOPWORDS = _stopwords()


@dataclass
class ClientRegistry:
    """Real folder name <-> ``CLIENTE_NNN``, plus the token dictionary used to scrub text."""

    codes: dict[str, str]                 # folder name -> CLIENTE_NNN
    tokens: dict[str, list[str]]          # CLIENTE_NNN -> its own name tokens (normalised)
    salt: str
    _all_tokens: frozenset[str]
    _owner_re: dict[str, re.Pattern]
    _global_re: re.Pattern | None
    _token_re: re.Pattern | None = None   # any roster token written like a name (see anonymise step 6)

    def code_for(self, folder_name: str | None) -> str | None:
        return self.codes.get(folder_name) if folder_name else None

    def digest(self, value: str) -> str:
        return hashlib.sha256((self.salt + norm(value)).encode("utf-8")).hexdigest()[:16]

    def mask_file_name(self, file_name: str) -> str:
        """Reduce a file name to an ALLOWLISTED descriptor plus a stable salted token.

        Deliberately an allowlist, not a filter. The first version removed words found in the v3 roster and left the
        rest, and the manifest went into the audited tree with 741 name hits: file names carry the names of people who
        are not among these 301 folders at all. Only words that are known-safe corpus vocabulary survive; everything
        else becomes ``T<digest>``, so the manifest is clean by construction rather than by exhaustive blocking.
        """
        stem, dot, ext = file_name.rpartition(".")
        stem = stem or file_name
        out = []
        for word in re.split(r"([\s_\-.()]+)", stem):
            if not word or not word.strip(" _-.()"):
                out.append(word)
                continue
            n = norm(word)
            if n.isdigit() or _VERSION_TOKEN.fullmatch(n) or n in SAFE_FILENAME_WORDS:
                out.append(word)
            else:
                out.append("T" + self.digest(word)[:8])
        masked = "".join(out)
        return f"{masked}.{ext}" if dot else masked

    def anonymise(self, text: str, code: str | None) -> tuple[str, dict[str, int]]:
        """Scrub a converted document. Returns the text and a count of substitutions by kind."""
        if not text:
            return text, {}
        counts: dict[str, int] = {}

        def sub(pattern: re.Pattern, repl: str, key: str, value: str) -> str:
            value, n = pattern.subn(repl, value)
            if n:
                counts[key] = counts.get(key, 0) + n
            return value

        # 1. The document owner's own name -> the pseudonym.
        if code and code in self._owner_re:
            text = sub(self._owner_re[code], code, "owner_name", text)
        # 2. Anybody else from the roster -> a generic marker.
        if self._global_re is not None:
            text = sub(self._global_re, "[NOMBRE]", "other_name", text)
        # 3. The professional himself.
        text, n_prof = _scrub_professional(text)
        if n_prof:
            counts["professional"] = counts.get("professional", 0) + n_prof
        # 4. Names introduced by a label. Lab reports and questionnaires name people the roster does not know at
        #    all -- the referring doctor, the nurse, the technical director, a second surname the folder omits --
        #    so the value of a naming label is redacted wholesale rather than matched against a dictionary.
        text = sub(_LABELLED_NAME, lambda m: m.group(1) + "[NOMBRE]", "labelled_name", text)
        # 5. Words stuck to an identifier already replaced: a capitalised word after "CLIENTE_105" is the rest of the same name.
        text = sub(_ADJACENT_AFTER, lambda m: m.group(1), "adjacent_name", text)
        text = sub(_ADJACENT_BEFORE, lambda m: m.group(1), "adjacent_name", text)
        # 6. Any remaining roster token, but only where it is written like a name. The same letters appear as
        #    ordinary vocabulary in the corpus ("tintes de cabello" occurs 1.670 times in the bioanalyser template
        #    and is a surname too); capitalisation is what separates the two, so lower-case occurrences are left
        #    alone and counted instead of being destroyed.
        text = sub(self._token_re, "[NOMBRE]", "single_token_name", text) if self._token_re is not None else text
        # 7. Direct identifiers.
        text = sub(EMAIL, "[EMAIL]", "email", text)
        text = sub(URL, "[URL]", "url", text)
        text = sub(IBAN, "[IBAN]", "iban", text)
        text = sub(DNI, "[DNI]", "dni", text)
        text = sub(NIE, "[NIE]", "nie", text)
        text = sub(SSN, "[NUMSS]", "ssn", text)
        text = sub(PHONE, "[TEL]", "phone", text)
        text = sub(FULL_DATE, "[FECHA]", "full_date", text)
        return text, counts

    def scrub_for_dataset(self, text: str) -> str:
        """The stricter pass applied to every string written into the public dataset.

        The converter's pass is tuned to keep the corpus readable and therefore leaves lower-case roster tokens
        alone, because the same letters are ordinary vocabulary. That is the right trade for a working cache and the
        wrong one for the deliverable: 79 names reached ``diets.jsonl`` that way. Here any roster token of four
        characters or more goes, *unless* it is reviewed corpus vocabulary (the Phase-2 stopwords) or a food name --
        which is what keeps "aceite de oliva" and "jamon serrano" intact while the surnames disappear.
        """
        if not text:
            return text
        text, _counts = self.anonymise(text, None)
        protected = STOPWORDS | _food_vocabulary()

        def replace(match: re.Match) -> str:
            token = norm(match.group(0))
            if len(token) >= 4 and token in self._all_tokens and token not in protected:
                return "[NOMBRE]"
            return match.group(0)

        return _WORD.sub(replace, text)

    def residual_name_tokens(self, text: str) -> list[str]:
        """Roster tokens still present after scrubbing. Returns NORMALISED tokens for counting, never for printing."""
        out = []
        for word in _WORD.findall(text or ""):
            n = norm(word)
            if len(n) >= 3 and n in self._all_tokens and n not in STOPWORDS:
                out.append(n)
        return out


def _tokens_of(folder_name: str) -> list[str]:
    return [norm(t) for t in _WORD.findall(folder_name) if len(norm(t)) >= 2]


def build_registry(sources_root: Path, salt: str | None = None) -> ClientRegistry:
    folders = sorted((p.name for p in sources_root.iterdir() if p.is_dir()), key=lambda s: norm(s))
    salt = salt or hashlib.sha256(("fps-v3:" + "|".join(sorted(folders))).encode("utf-8")).hexdigest()[:32]

    codes = {name: f"CLIENTE_{i:03d}" for i, name in enumerate(folders, 1)}
    tokens = {codes[name]: _tokens_of(name) for name in folders}
    all_tokens = frozenset(t for toks in tokens.values() for t in toks if len(t) >= 3)

    owner_re: dict[str, re.Pattern] = {}
    for name, code in codes.items():
        toks = [t for t in _tokens_of(name) if len(t) >= 3 and t not in STOPWORDS]
        if not toks:
            continue
        alts = [r"\s+".join(_accent_insensitive(t) for t in toks)]          # the full sequence
        if len(toks) >= 2:
            alts.append(_accent_insensitive(toks[0]) + r"\s+" + _accent_insensitive(toks[-1]))
        alts.extend(_accent_insensitive(t) for t in toks if len(t) >= 4)     # single distinctive tokens
        owner_re[code] = re.compile(r"(?i)\b(?:" + "|".join(alts) + r")\b")

    global_pats: list[str] = []
    for name in folders:
        toks = [t for t in _tokens_of(name) if len(t) >= 3 and t not in STOPWORDS]
        if len(toks) >= 2:
            global_pats.append(r"\s+".join(_accent_insensitive(t) for t in toks))
            global_pats.append(_accent_insensitive(toks[0]) + r"\s+" + _accent_insensitive(toks[-1]))
    global_re = re.compile(r"(?i)\b(?:" + "|".join(global_pats) + r")\b") if global_pats else None

    # Step 6 of anonymise(): a single roster token, matched ONLY where it is capitalised like a name.
    # Case-sensitive on purpose -- see the comment there. Food vocabulary is excluded outright.
    single = sorted({t for t in all_tokens
                     if len(t) >= 4 and t not in STOPWORDS and t not in _food_vocabulary()})
    token_re = re.compile(r"\b(?:" + "|".join(_capitalised(t) for t in single) + r")\b") if single else None

    return ClientRegistry(codes, tokens, salt, all_tokens, owner_re, global_re, token_re)


_UPPER_CLASS = {
    "A": "[AÁÀÂÄ]", "E": "[EÉÈÊË]", "I": "[IÍÌÎÏ]", "O": "[OÓÒÔÖ]", "U": "[UÚÙÛÜ]", "N": "[NÑ]", "C": "[CÇ]",
}


def _capitalised(token: str) -> str:
    """Match ``Apellido`` and ``APELLIDO`` (however accented) but never ``apellido``."""
    head = _UPPER_CLASS.get(token[0], re.escape(token[0]))
    body = "".join(_ACCENT_CLASS.get(c, re.escape(c)) for c in token[1:])
    return head + body


_FOOD_VOCAB: frozenset[str] | None = None


def _food_vocabulary() -> frozenset[str]:
    """Tokens of the v2 food catalogue: a roster token that is also a food name is vocabulary, not a name."""
    global _FOOD_VOCAB
    if _FOOD_VOCAB is not None:
        return _FOOD_VOCAB
    vocab: set[str] = set()
    try:
        from .paths import dataset_dir_v2
        data = json.loads((dataset_dir_v2() / "foods.json").read_text(encoding="utf-8"))
        for food in data.get("foods", []):
            for value in [food.get("canonical_name", ""), *food.get("synonyms", []), *food.get("keys", [])]:
                for word in str(value).replace("/", " ").split():
                    vocab.add(norm(word))
    except Exception:
        pass
    _FOOD_VOCAB = frozenset(vocab)
    return _FOOD_VOCAB


_ACCENT_CLASS = {
    "A": "[AÁÀÂÄaáàâä]", "E": "[EÉÈÊËeéèêë]", "I": "[IÍÌÎÏiíìîï]",
    "O": "[OÓÒÔÖoóòôö]", "U": "[UÚÙÛÜuúùûü]", "N": "[NÑnñ]", "C": "[CÇcç]",
}


def _accent_insensitive(token: str) -> str:
    """Match the token however it is accented: source documents spell the same surname both ways."""
    return "".join(_ACCENT_CLASS.get(ch, re.escape(ch)) for ch in token)


def private_dir() -> Path:
    d = dataset_dir_v3() / "_private"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_or_build_registry(sources_root: Path) -> ClientRegistry:
    """Build the registry once and persist the private map; reuse it on later runs so codes stay stable."""
    path = private_dir() / "client_files_map.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        registry = build_registry(sources_root, salt=data.get("salt"))
        if registry.codes == data.get("codes"):
            return registry
    registry = build_registry(sources_root)
    path.write_text(
        json.dumps({"salt": registry.salt, "codes": registry.codes}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n",
    )
    _write_audit_dictionary(registry)
    return registry


def _write_audit_dictionary(registry: ClientRegistry) -> None:
    """Put the PII audit's detection dictionary in the v3 private directory.

    ``audit_tree`` loads it from whichever dataset is ACTIVE, so once v3 is activated this file is the dictionary
    the whole audit runs on. It must therefore be the v2 one, not a new one built from these 301 folders: the v2
    dictionary covers all 467 known clients (a superset) and carries the ``reviewed_false_positives`` list -- the
    common Spanish words that collide with a surname, reviewed with the data owner. Regenerating it from the v3
    roster loses those three digests and changes the salt, which on activation turned the audit from 0 hits into
    1.160, nearly all of them ordinary vocabulary.

    A dictionary derived from the current sources is only a fallback, for a clean clone where v2 is not present.
    """
    target = private_dir() / "name_tokens_hashed.json"
    source = dataset_dir_v2() / "_private" / "name_tokens_hashed.json"
    if source.exists():
        shutil.copyfile(source, target)
        return
    hashed = {
        "_doc": "fallback dictionary built from the v3 sources: the v2 one, which is the reviewed superset, "
                "was not available",
        "salt": registry.salt,
        "name_tokens": sorted({hashlib.sha256((registry.salt + t).encode("utf-8")).hexdigest()
                               for t in registry._all_tokens}),
        "reviewed_false_positives": [],
    }
    target.write_text(json.dumps(hashed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def client_key(folder_name: str, registry: ClientRegistry) -> str | None:
    return registry.code_for(folder_name)
