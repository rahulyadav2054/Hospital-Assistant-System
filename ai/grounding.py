"""Grounding verifier - the hallucination safety net. Runs on every answer.

1. Split the draft into sentences.
2. Drop factual sentences without a valid [Sx] tag (greetings, transitions and questions are allowed).
3. For each tagged sentence, every number / date / time must appear in the cited source text.
4. If no factual sentence survives -> the standard not-found reply.
"""
import re

NOT_FOUND_MSG = ("I couldn't find this in the hospital's records or policies. Please contact the Patient Help Desk "
                 "(Block A, Ground Floor, extension 1100) for help.")

NUM = re.compile(r"\d+(?:[.:]\d+)?")
TAG = re.compile(r"\[S(\d+)\]")
LIST_MARK = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")
_LEADING_TAGS = re.compile(r"^((?:\[S\d+\]\s*)+)(.*)$", re.S)
ABBREV = {"dr", "mr", "mrs", "ms", "e.g", "i.e", "vs", "no", "st", "approx", "ext", "fig", "inc", "sr", "jr", "etc"}
_ALLOWED_UNTAGGED = re.compile(
    r"^(please (confirm|press|click|tap|use|review)\b|is there anything else|let me know|i hope this helps|"
    r"sure[.!]?$|here (is|are)\b|you can also ask\b|which (one|appointment)\b)", re.I)


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? followed by whitespace, except after abbreviations (Dr.) and list markers (1.)."""
    out, start = [], 0
    for m in re.finditer(r"[.!?](?=\s+)", text):
        chunk = text[start:m.end()]
        token = chunk.split()[-1] if chunk.split() else ""
        if token.lower().rstrip(".") in ABBREV:
            continue
        if re.fullmatch(r"\d+\.", token) and chunk.strip() == token:
            continue  # "1." at the start = list marker
        out.append(chunk.strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    # Tags written after the full stop ("... daily. [S1] Next") belong to the previous sentence.
    fixed: list[str] = []
    for s in out:
        m = _LEADING_TAGS.match(s)
        if m and fixed:
            fixed[-1] = f"{fixed[-1]} {m.group(1).strip()}"
            s = m.group(2).strip()
        if s:
            fixed.append(s)
    return fixed


def _norm_nums(t: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", t)


def is_non_factual(sentence: str) -> bool:
    plain = LIST_MARK.sub("", sentence).strip("*_ #").strip()
    if not plain:
        return True
    if NUM.search(plain):
        return False
    words = len(plain.split())
    if plain.endswith(":") and words <= 12:
        return True
    if plain.endswith("?") and words <= 15:
        return True
    return bool(_ALLOWED_UNTAGGED.match(plain)) and words <= 20


def _evidence(source: dict) -> str:
    parts = [source.get("text"), source.get("title"), source.get("section"), source.get("ref"), source.get("date")]
    return _norm_nums(" ".join(str(p) for p in parts if p))


def verify_grounding(draft: str, sources: list[dict]) -> tuple[str, str]:
    by_id = {s["id"]: s for s in sources}
    lines_out: list[str] = []
    grounded = 0
    for line in (draft or "").strip().splitlines():
        if not line.strip():
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            continue
        marker = LIST_MARK.match(line)
        prefix = marker.group(0) if marker else ""
        kept = []
        for s in split_sentences(line[len(prefix):]):
            tags = [f"S{t}" for t in TAG.findall(s)]
            if not tags:
                if is_non_factual(s):
                    kept.append(s)
                continue
            if any(t not in by_id for t in tags):
                continue
            evidence = " ".join(_evidence(by_id[t]) for t in tags)
            claim = _norm_nums(TAG.sub("", LIST_MARK.sub("", s)))
            if all(n in evidence for n in NUM.findall(claim)):
                kept.append(s)
                grounded += 1
        if kept:
            lines_out.append(prefix + " ".join(kept))
    answer = "\n".join(lines_out).strip()
    if grounded == 0:
        return NOT_FOUND_MSG, "not_found"
    return answer, "ok"
