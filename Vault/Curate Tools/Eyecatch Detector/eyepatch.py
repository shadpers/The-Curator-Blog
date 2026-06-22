#!/usr/bin/env python3
"""
EYEPATCH — Eyecatch-Aware Patch & Correction Helper
Detecta o pulo de offset no eyecatch via comparacao de legendas
e aplica a correcao em todas as faixas de audio e legenda do MKV alvo.
"""

import sys
import subprocess
import os
import json
import re
import tempfile
import shutil
from difflib import SequenceMatcher

FFMPEG   = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE  = r"C:\FFmpeg\bin\ffprobe.exe"

# Tenta localizar mkvmerge em caminhos comuns
_MKVMERGE_CANDIDATES = [
    r"C:\MKVToolNix\mkvmerge.exe",
    r"C:\Program Files\MKVToolNix\mkvmerge.exe",
    r"C:\Program Files (x86)\MKVToolNix\mkvmerge.exe",
]
MKVMERGE = next((p for p in _MKVMERGE_CANDIDATES if os.path.exists(p)), "mkvmerge")

SEP  = "=" * 62
SEP2 = "-" * 62


# ─────────────────────────────────────────────────────────────────────────────
# Timestamp helpers
# ─────────────────────────────────────────────────────────────────────────────

def ass_ts_to_ms(ts):
    """'H:MM:SS.cc' -> ms"""
    h, m, rest = ts.split(":")
    s, cs = rest.split(".")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(cs) * 10

def ms_to_ass_ts(ms):
    ms = max(0, int(round(ms)))
    cs = (ms % 1000) // 10
    s  = (ms // 1000) % 60
    m  = (ms // 60000) % 60
    h  = ms // 3600000
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def srt_ts_to_ms(ts):
    """'HH:MM:SS,mmm' -> ms"""
    h, m, rest = ts.split(":")
    s, mil = rest.split(",")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(mil)

def ms_to_srt_ts(ms):
    ms = max(0, int(round(ms)))
    mil = ms % 1000
    s   = (ms // 1000) % 60
    m   = (ms // 60000) % 60
    h   = ms // 3600000
    return f"{h:02d}:{m:02d}:{s:02d},{mil:03d}"

def ms_to_human(ms):
    neg = ms < 0
    ms  = abs(int(ms))
    s   = (ms // 1000) % 60
    m   = ms // 60000
    return f"{'-' if neg else ''}{m}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# FFprobe helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ffprobe_json(args):
    """Run ffprobe and return parsed JSON, handling Windows encoding safely."""
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw = r.stdout.decode("utf-8", errors="replace")
    return json.loads(raw)

def get_chapters(mkv_path):
    return _ffprobe_json([FFPROBE, "-v", "quiet", "-print_format", "json",
                          "-show_chapters", mkv_path]).get("chapters", [])

def get_streams(mkv_path):
    return _ffprobe_json([FFPROBE, "-v", "quiet", "-print_format", "json",
                          "-show_streams", mkv_path]).get("streams", [])

# Aliases conhecidos para o capitulo "Part B" em releases de anime BD
_PART_B_ALIASES = [
    "part b", "part 2", "part two", "partb", "b part",
    "act b", "act 2", "act two",
    "segunda parte", "second part", "2nd part",
    "parte b", "parte 2",
    "2部分", "後半",            # japonês
    "teil b", "teil 2",        # alemão
    "partie b", "partie 2",    # francês
    "parte seconda",            # italiano
]

# Intervalo de tempo esperado para o inicio do Part B em um episodio de 24min
_PART_B_START_MIN_S =  480   # 8 min
_PART_B_START_MAX_S = 1000   # ~16.5 min


def _ch_start_ms(ch):
    return int(float(ch["start_time"]) * 1000)


def locate_part_b(chapters):
    """
    Localiza o capitulo "Part B" usando tres estrategias em cascata:

    1. Correspondencia por nome: qualquer alias em _PART_B_ALIASES.
    2. Heuristica temporal: capitulo cujo inicio cai em [8min, 16.5min]
       E que nao seja o primeiro capitulo nessa faixa (Part A pode comecar
       antes dos 8min mas nunca depois — Part B e o segundo nessa janela).
    3. Heuristica posicional: em estruturas de 5 ou 6 capitulos (padrao BD
       de anime: Intro/OP → OP → Part A → Part B → ED → Preview), o Part B
       e sempre o capitulo de indice 3.

    Retorna (ms, titulo_original, metodo_str) ou (None, None, motivo_str).
    """
    if not chapters:
        return None, None, "nenhum capitulo encontrado"

    # ── Estrategia 1: por nome ────────────────────────────────────────────
    for ch in chapters:
        title = ch.get("tags", {}).get("title", "").strip()
        if any(alias in title.lower() for alias in _PART_B_ALIASES):
            return _ch_start_ms(ch), title, "nome"

    # ── Estrategia 2: heuristica temporal ────────────────────────────────
    # Pega todos os capitulos cujo inicio cai na janela esperada
    in_window = [
        ch for ch in chapters
        if _PART_B_START_MIN_S <= float(ch["start_time"]) <= _PART_B_START_MAX_S
    ]
    if len(in_window) == 1:
        ch = in_window[0]
        title = ch.get("tags", {}).get("title", "").strip() or f"(indice {chapters.index(ch)})"
        return _ch_start_ms(ch), title, "heuristica temporal"
    if len(in_window) >= 2:
        # Dois ou mais capitulos na janela: pega o de indice mais alto
        # (Part A começa antes, Part B começa depois)
        ch = in_window[-1]
        title = ch.get("tags", {}).get("title", "").strip() or f"(indice {chapters.index(ch)})"
        return _ch_start_ms(ch), title, "heuristica temporal (ultimo na janela)"

    # ── Estrategia 3: posicional ──────────────────────────────────────────
    if len(chapters) >= 5:
        ch = chapters[3]
        title = ch.get("tags", {}).get("title", "").strip() or "(sem titulo)"
        return _ch_start_ms(ch), title, f"posicional (indice 3 de {len(chapters)})"

    return None, None, f"nao foi possivel identificar Part B ({len(chapters)} capitulos)"


def chapter_jump_estimate(ref_chapters, tgt_chapters):
    """
    Estima o pulo usando diferenca de timestamps de capitulos.

    Compara o inicio do Part B e o inicio do capitulo seguinte em ambos
    os arquivos. A diferenca entre os dois deltas e o pulo do eyecatch.

    Retorna (jump_ms, detalhes_dict) ou (None, motivo_str).
    detalhes_dict tem chaves: ref_pb_ms, tgt_pb_ms, ref_aft_ms, tgt_aft_ms,
                               ref_pb_title, tgt_pb_title, method_ref, method_tgt
    """
    ref_pb_ms, ref_pb_title, ref_method = locate_part_b(ref_chapters)
    tgt_pb_ms, tgt_pb_title, tgt_method = locate_part_b(tgt_chapters)

    if ref_pb_ms is None:
        return None, f"REF: {ref_method}"
    if tgt_pb_ms is None:
        return None, f"ALVO: {tgt_method}"

    # Capitulo imediatamente apos o Part B em cada arquivo
    def _next_chapter_ms(chapters, part_b_ms):
        for i, ch in enumerate(chapters):
            if abs(_ch_start_ms(ch) - part_b_ms) < 500 and i + 1 < len(chapters):
                return _ch_start_ms(chapters[i + 1])
        return None

    ref_aft_ms = _next_chapter_ms(ref_chapters, ref_pb_ms)
    tgt_aft_ms = _next_chapter_ms(tgt_chapters, tgt_pb_ms)

    if ref_aft_ms is None or tgt_aft_ms is None:
        return None, "capitulo seguinte ao Part B nao encontrado"

    cut_delta = tgt_pb_ms - ref_pb_ms
    aft_delta = tgt_aft_ms - ref_aft_ms
    jump      = aft_delta - cut_delta

    return jump, {
        "ref_pb_ms":    ref_pb_ms,
        "tgt_pb_ms":    tgt_pb_ms,
        "ref_aft_ms":   ref_aft_ms,
        "tgt_aft_ms":   tgt_aft_ms,
        "ref_pb_title": ref_pb_title,
        "tgt_pb_title": tgt_pb_title,
        "method_ref":   ref_method,
        "method_tgt":   tgt_method,
        "cut_delta":    cut_delta,
        "aft_delta":    aft_delta,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Subtitle: format detection, extract, parse, write
# ─────────────────────────────────────────────────────────────────────────────

def detect_fmt(codec_name):
    c = codec_name.lower()
    if "ass" in c or "ssa" in c:
        return "ass"
    if "subrip" in c or "srt" in c:
        return "srt"
    return "unknown"

def extract_subtitle(mkv_path, abs_idx, out_path):
    cmd = [FFMPEG, "-y", "-i", mkv_path,
           "-map", f"0:{abs_idx}", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"Falha ao extrair legenda {abs_idx}:\n{r.stderr[-600:]}")

# ── ASS ──────────────────────────────────────────────────────────────────────

_ASS_RE = re.compile(
    r"^(Dialogue:\s*\d+,)"
    r"(\d:\d{2}:\d{2}\.\d{2}),"
    r"(\d:\d{2}:\d{2}\.\d{2}),"
    r"(.*)$",
    re.DOTALL,
)

def parse_ass(path):
    """Returns (header_lines, events_list)."""
    header, events, in_events = [], [], False
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.strip().lower() == "[events]":
                in_events = True
                header.append(line)
                continue
            if in_events and line.startswith("Dialogue:"):
                m = _ASS_RE.match(line)
                if m:
                    events.append({
                        "prefix":   m.group(1),
                        "start_ms": ass_ts_to_ms(m.group(2)),
                        "end_ms":   ass_ts_to_ms(m.group(3)),
                        "rest":     m.group(4),
                    })
                    continue
            header.append(line)
    return header, events

def write_ass(header, events, path):
    with open(path, "w", encoding="utf-8") as f:
        for line in header:
            f.write(line + "\n")
        for ev in events:
            f.write(
                f"{ev['prefix']}"
                f"{ms_to_ass_ts(ev['start_ms'])},"
                f"{ms_to_ass_ts(ev['end_ms'])},"
                f"{ev['rest']}\n"
            )

def ass_plain_text(ev):
    rest = ev["rest"].split(",", 8)[-1] if "," in ev["rest"] else ev["rest"]
    t = re.sub(r"\{[^}]*\}", "", rest)
    t = re.sub(r"\\[Nn]", " ", t)
    return " ".join(t.split()).lower()

# ── SRT ──────────────────────────────────────────────────────────────────────

_SRT_TIMING = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"
)

def parse_srt(path):
    events = []
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        content = f.read()
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            m = _SRT_TIMING.match(line.strip())
            if m:
                text = " ".join(lines[i + 1:]).strip()
                events.append({
                    "start_ms": srt_ts_to_ms(m.group(1)),
                    "end_ms":   srt_ts_to_ms(m.group(2)),
                    "text":     text,
                })
                break
    return events

def write_srt(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, ev in enumerate(events, 1):
            f.write(f"{i}\n")
            f.write(f"{ms_to_srt_ts(ev['start_ms'])} --> {ms_to_srt_ts(ev['end_ms'])}\n")
            f.write(ev["text"] + "\n\n")

def srt_plain_text(ev):
    t = re.sub(r"<[^>]+>", "", ev["text"])
    return " ".join(t.split()).lower()

# ── Generic getters ───────────────────────────────────────────────────────────

def ev_start(ev):
    return ev["start_ms"]

def ev_text(ev, fmt):
    return ass_plain_text(ev) if fmt == "ass" else srt_plain_text(ev)


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue matching  —  IMPROVED
# ─────────────────────────────────────────────────────────────────────────────

_STOP = frozenset({
    "a", "an", "the", "i", "is", "it", "to", "of", "and", "in", "you",
    "he", "she", "we", "they", "this", "that", "for", "be", "are", "was",
    "do", "not", "have", "has", "will", "can", "but", "with", "at", "by",
    "me", "my", "our", "your", "his", "her", "its", "on", "as", "up",
    "no", "so", "if", "or", "all", "just", "now", "get", "go", "got",
})

def word_overlap(a, b):
    """Jaccard similarity on word sets (including stop words)."""
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

def text_similarity(a, b):
    """
    Combined similarity: max of —
      - Jaccard on content words only (strips stop words and short tokens)
      - SequenceMatcher character ratio * 0.8 (tolerates paraphrasing)
    This handles cases where two valid translations of the same line
    share few words but similar character patterns, or share key nouns
    even when verbs/structure differ.
    """
    if not a or not b:
        return 0.0

    # Content-word Jaccard (strips stop words, keeps words >= 3 chars)
    wa = {w for w in a.split() if len(w) >= 3 and w not in _STOP}
    wb = {w for w in b.split() if len(w) >= 3 and w not in _STOP}
    if wa and wb:
        content_sc = len(wa & wb) / len(wa | wb)
    elif not wa and not wb:
        content_sc = word_overlap(a, b)   # all stop words — use plain Jaccard
    else:
        content_sc = 0.0

    # Character-level sequence ratio (capped at 0.8 weight)
    seq_sc = SequenceMatcher(None, a, b).ratio() * 0.8

    return max(content_sc, seq_sc)

def events_in_window(events, center_ms, window_ms):
    lo, hi = center_ms - window_ms, center_ms + window_ms
    return [e for e in events if lo <= e["start_ms"] <= hi]


def match_pairs_windowed(ref_evs, tgt_evs, ref_fmt, tgt_fmt,
                          expected_offset_ms=0,
                          time_tolerance_ms=4000,
                          min_score=0.30):
    """
    Bipartite matching: each REF event is paired with the best TGT event,
    subject to BOTH text similarity AND a timing window constraint.

    expected_offset_ms : expected tgt_start ≈ ref_start + expected_offset_ms
    time_tolerance_ms  : how far (±) from that expectation we search

    Matching is exclusive: each TGT event can only be assigned once
    (greedily, highest score first), preventing the same TGT line from
    absorbing multiple REF events and corrupting the delta statistics.
    """
    candidates = []
    for r in ref_evs:
        rt = ev_text(r, ref_fmt)
        if len(rt.split()) < 2:
            continue
        expected_tgt = r["start_ms"] + expected_offset_ms
        lo = expected_tgt - time_tolerance_ms
        hi = expected_tgt + time_tolerance_ms
        for t in tgt_evs:
            if lo <= t["start_ms"] <= hi:
                sc = text_similarity(rt, ev_text(t, tgt_fmt))
                if sc >= min_score:
                    candidates.append((sc, id(r), id(t), r, t, rt))

    # Greedy assignment: best score first, each node used at most once
    candidates.sort(key=lambda x: -x[0])
    used_ref, used_tgt = set(), set()
    pairs = []
    for sc, rid, tid, r, t, rt in candidates:
        if rid in used_ref or tid in used_tgt:
            continue
        used_ref.add(rid)
        used_tgt.add(tid)
        pairs.append((r["start_ms"], t["start_ms"], rt[:48]))

    pairs.sort(key=lambda x: x[0])
    return pairs


def robust_avg(deltas):
    """
    IQR-filtered mean: removes outliers beyond 1.5×IQR before averaging.
    Falls back to plain mean if too few points to compute IQR reliably.
    """
    if not deltas:
        return 0.0
    if len(deltas) < 4:
        return sum(deltas) / len(deltas)
    s = sorted(deltas)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    if iqr == 0:
        return sum(deltas) / len(deltas)
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    clean = [d for d in s if lo <= d <= hi]
    if not clean:
        clean = deltas
    return sum(clean) / len(clean)


def estimate_jump(ref_evs, tgt_evs, ref_fmt, tgt_fmt, cut_ref_ms,
                  chapter_jump_ms=None):
    """
    Dois estagio de matching com ancora nos capitulos.

    Estagio 1 — ANTES: janela apertada (video identico → delta esperado ~0),
                 deriva avg_before robusto.

    Estagio 2 — DEPOIS: janela centrada em avg_before + chapter_jump_ms
                 (ou avg_before se chapter_jump_ms nao disponivel).
                 Threshold mais baixo pois traducoes diferentes tem menos overlap.

    chapter_jump_ms: estimativa direta pelos capitulos — quando disponivel,
                     centra a janela de busca exatamente no lugar certo e
                     permite tolerancia MUITO menor → muito menos falsos positivos.
    """
    MARGIN_MS    = 60_000   # contexto em cada lado do corte
    BEFORE_TOL   = 2_000    # apertado: video identico antes do eyecatch
    AFTER_TOL    =   800    # muito apertado com ancora de capitulo (evita mis-matches)
    AFTER_TOL_FB = 4_000    # largo como fallback sem ancora

    before_ref_evs = [e for e in ref_evs
                      if cut_ref_ms - MARGIN_MS <= e["start_ms"] < cut_ref_ms]
    after_ref_evs  = [e for e in ref_evs
                      if cut_ref_ms <= e["start_ms"] <= cut_ref_ms + MARGIN_MS]

    tgt_pool = [e for e in tgt_evs
                if cut_ref_ms - MARGIN_MS * 2 <= e["start_ms"]
                             <= cut_ref_ms + MARGIN_MS * 2]

    # ── Estagio 1: antes ──────────────────────────────────────────────────
    before_pairs = match_pairs_windowed(
        before_ref_evs, tgt_pool, ref_fmt, tgt_fmt,
        expected_offset_ms=0,
        time_tolerance_ms=BEFORE_TOL,
        min_score=0.28,
    )
    before_deltas = [t - r for r, t, _ in before_pairs]
    avg_before    = robust_avg(before_deltas)

    # ── Estagio 2: depois — centrado na ancora de capitulos ───────────────
    if chapter_jump_ms is not None:
        expected_after = int(avg_before) + int(chapter_jump_ms)
        after_tol      = AFTER_TOL
        min_sc_after   = 0.25   # traducoes diferentes: threshold mais permissivo
    else:
        expected_after = int(avg_before)
        after_tol      = AFTER_TOL_FB
        min_sc_after   = 0.28

    after_pairs = match_pairs_windowed(
        after_ref_evs, tgt_pool, ref_fmt, tgt_fmt,
        expected_offset_ms=expected_after,
        time_tolerance_ms=after_tol,
        min_score=min_sc_after,
    )
    after_deltas = [t - r for r, t, _ in after_pairs]
    avg_after    = robust_avg(after_deltas)

    jump_ms = avg_after - avg_before
    return before_pairs, after_pairs, avg_before, avg_after, jump_ms


# ─────────────────────────────────────────────────────────────────────────────
# Audio fix
# ─────────────────────────────────────────────────────────────────────────────

def fix_audio_stream(mkv_path, abs_idx, cut_s, jump_s, out_flac):
    """
    Divide o audio em cut_s e remove/insere jump_s segundos no inicio do seg2.
    jump_s > 0 -> target atrasado -> tira jump_s do inicio do seg2
    jump_s < 0 -> target adiantado -> insere silencio no inicio do seg2
    """
    if abs(jump_s) < 0.005:
        cmd = [FFMPEG, "-y", "-i", mkv_path,
               "-map", f"0:{abs_idx}", "-c:a", "flac", out_flac]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-600:])
        return

    if jump_s > 0:
        f2 = f"atrim=start={cut_s + jump_s:.4f},asetpts=PTS-STARTPTS"
    else:
        sil_ms = int(abs(jump_s) * 1000)
        f2 = f"atrim=start={cut_s:.4f},asetpts=PTS-STARTPTS,adelay={sil_ms}:all=1"

    fc = (
        f"[0:{abs_idx}]asplit=2[_s1][_s2];"
        f"[_s1]atrim=0:{cut_s:.4f},asetpts=PTS-STARTPTS[a1];"
        f"[_s2]{f2}[a2];"
        f"[a1][a2]concat=n=2:v=0:a=1[out]"
    )
    cmd = [FFMPEG, "-y", "-i", mkv_path,
           "-filter_complex", fc,
           "-map", "[out]", "-c:a", "flac", out_flac]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou no audio {abs_idx}:\n{r.stderr[-600:]}")


# ─────────────────────────────────────────────────────────────────────────────
# Subtitle fix
# ─────────────────────────────────────────────────────────────────────────────

def remove_eyecatch_duplicates(events, cut_ms, fmt):
    """
    Procura por dialogos duplicados na regiao do eyecatch (janela de ± 45s).
    Se encontrar falas identicas (texto plain), remove a PRIMEIRA ocorrencia
    (pre-corte) e mantem a SEGUNDA (pos-corte), avisando no console.
    Util quando o arquivo alvo repete o ultimo dialogo antes do eyecatch
    logo apos a emenda.
    """
    window   = 45_000   # raio de busca em torno do ponto de corte (ms)
    to_remove = set()

    for i in range(len(events)):
        if i in to_remove:
            continue
        ev1 = events[i]
        if not (cut_ms - window <= ev1["start_ms"] <= cut_ms + window):
            continue
        text1 = ev_text(ev1, fmt).strip()
        if len(text1) < 10:          # ignora respostas muito curtas ("sim.", "ah!")
            continue
        for j in range(i + 1, min(i + 11, len(events))):
            if j in to_remove:
                continue
            if ev_text(events[j], fmt).strip() == text1:
                to_remove.add(i)
                raw = ev1.get("rest", ev1.get("text", ""))
                raw = raw.replace(r"\N", " ").replace("\n", " ")
                if len(raw) > 55:
                    raw = raw[:52] + "..."
                print(f"\n      [!] Repeticao de Eyecatch resolvida:")
                print(f"          - Removido: [{ms_to_human(ev1['start_ms'])}] {raw}")
                print(f"          - Mantido : [{ms_to_human(events[j]['start_ms'])}]")
                break

    for idx in sorted(to_remove, reverse=True):
        events.pop(idx)
    return events


def fix_subtitle_stream(mkv_path, abs_idx, codec, cut_ms, jump_ms, out_path, tmp_dir):
    fmt = detect_fmt(codec)
    ext = "ass" if fmt == "ass" else "srt"
    raw = os.path.join(tmp_dir, f"raw_{abs_idx}.{ext}")
    extract_subtitle(mkv_path, abs_idx, raw)

    if fmt == "ass":
        header, events = parse_ass(raw)
        events = remove_eyecatch_duplicates(events, cut_ms, fmt)
        for ev in events:
            if ev["start_ms"] >= cut_ms:
                ev["start_ms"] -= jump_ms
                ev["end_ms"]   -= jump_ms
        write_ass(header, events, out_path)
    elif fmt == "srt":
        events = parse_srt(raw)
        events = remove_eyecatch_duplicates(events, cut_ms, fmt)
        for ev in events:
            if ev["start_ms"] >= cut_ms:
                ev["start_ms"] -= jump_ms
                ev["end_ms"]   -= jump_ms
        write_srt(events, out_path)
    else:
        # Formato desconhecido: copia sem alterar
        shutil.copy(raw, out_path)


# ─────────────────────────────────────────────────────────────────────────────
# Mux
# ─────────────────────────────────────────────────────────────────────────────

def mux_output(tgt_path, audio_files, audio_meta, sub_files, sub_meta, output_path):
    cmd = [MKVMERGE, "-o", output_path]

    for af, m in zip(audio_files, audio_meta):
        if m.get("language"):
            cmd += ["--language", f"0:{m['language']}"]
        if m.get("title"):
            cmd += ["--track-name", f"0:{m['title']}"]
        cmd.append(af)

    for sf, m in zip(sub_files, sub_meta):
        if m.get("language"):
            cmd += ["--language", f"0:{m['language']}"]
        if m.get("title"):
            cmd += ["--track-name", f"0:{m['title']}"]
        cmd.append(sf)

    # Attachments do alvo (sem video/audio/subs/chapters)
    cmd += ["--no-video", "--no-audio", "--no-subtitles", "--no-chapters", tgt_path]

    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode > 1:
        raise RuntimeError(f"mkvmerge falhou:\n{r.stdout}\n{r.stderr}")


# ─────────────────────────────────────────────────────────────────────────────
# Stream listing / selection
# ─────────────────────────────────────────────────────────────────────────────

def print_av_streams(streams):
    """Print audio+subtitle streams with both local (#N) and absolute index."""
    audio_n, sub_n = 0, 0
    filtered = []
    print(f"\n  {'#':>3}  {'Idx':>4}  {'Tipo':>5}  {'Codec':>10}  {'Lang':>5}  Titulo")
    print(f"  {'-'*60}")
    for s in streams:
        ct = s.get("codec_type")
        if ct == "audio":
            audio_n += 1
            local = f"A{audio_n}"
            filtered.append((local, s))
        elif ct == "subtitle":
            sub_n += 1
            local = f"S{sub_n}"
            filtered.append((local, s))
        else:
            continue
        print(
            f"  {local:>3}  "
            f"{s['index']:>4}  "
            f"{ct[:5]:>5}  "
            f"{s.get('codec_name','?')[:10]:>10}  "
            f"{s.get('tags',{}).get('language','?')[:5]:>5}  "
            f"{s.get('tags',{}).get('title','')[:35]}"
        )
    return filtered  # list of (local_label, stream_dict)

def pick_stream(streams, codec_type, label):
    """
    Accept:
      - absolute stream index (e.g. 12)
      - local label (e.g. S3 or s3)
      - local number within type (e.g. 3 → 3rd subtitle)
    """
    valid_pairs = [(loc, s) for loc, s in streams if s.get("codec_type") == codec_type]
    if not valid_pairs:
        return None
    prefix = "A" if codec_type == "audio" else "S"

    while True:
        raw = input(f"\n  Selecione {label} (# ou indice absoluto): ").strip()
        # Try absolute index
        try:
            idx = int(raw)
            # Could be absolute OR local number
            # First try absolute
            match = next((s for _, s in valid_pairs if s["index"] == idx), None)
            if match:
                return match
            # Then try as 1-based local number
            if 1 <= idx <= len(valid_pairs):
                return valid_pairs[idx - 1][1]
        except ValueError:
            pass
        # Try label like S3 or A2
        label_up = raw.upper()
        match = next((s for loc, s in valid_pairs if loc == label_up), None)
        if match:
            return match

        options = [f"{loc}(idx={s['index']})" for loc, s in valid_pairs]
        print(f"  Invalido. Opcoes: {options}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(ref_path, tgt_path):
    print(f"\n{SEP}")
    print("  EYEPATCH  |  Eyecatch-Aware Patch & Correction Helper")
    print(SEP)

    print(f"\n  REF : {os.path.basename(ref_path)}")
    print(f"  ALVO: {os.path.basename(tgt_path)}")

    # ── Part B boundary & chapter-based jump estimate ────────────────────
    print(f"\n{SEP2}")
    print("  Lendo capitulos...")
    ref_chapters = get_chapters(ref_path)
    tgt_chapters = get_chapters(tgt_path)

    ref_pb_ms, ref_pb_title, ref_pb_method = locate_part_b(ref_chapters)

    if ref_pb_ms is None:
        print(f"  AVISO: Part B nao localizado na REF ({ref_pb_method}).")
        raw = input("  Informe o tempo de inicio do Part B em segundos: ").strip()
        cut_ref_ms = int(float(raw) * 1000)
    else:
        cut_ref_ms = ref_pb_ms
        print(f"  Part B REF : {ms_to_human(cut_ref_ms)} — \"{ref_pb_title}\" [{ref_pb_method}]")

    # Estimativa primaria pelo diff de capitulos
    ch_jump_ms, ch_detail = chapter_jump_estimate(ref_chapters, tgt_chapters)
    if ch_jump_ms is not None:
        d = ch_detail
        print(f"\n{SEP2}")
        print("  Estimativa por capitulos (metodo primario):")
        print(f"  Part B   REF={ms_to_human(d['ref_pb_ms'])} \"{d['ref_pb_title']}\" [{d['method_ref']}]")
        print(f"           ALVO={ms_to_human(d['tgt_pb_ms'])} \"{d['tgt_pb_title']}\" [{d['method_tgt']}]"
              f"  delta={d['cut_delta']:+d}ms")
        print(f"  Prox.cap REF={ms_to_human(d['ref_aft_ms'])}  ALVO={ms_to_human(d['tgt_aft_ms'])}"
              f"  delta={d['aft_delta']:+d}ms")
        print(f"  => PULO ESTIMADO: {ch_jump_ms:+d} ms")
    else:
        print(f"  Aviso capitulos: {ch_detail}")

    # ── Stream listing ────────────────────────────────────────────────────
    ref_streams = get_streams(ref_path)
    tgt_streams = get_streams(tgt_path)

    print(f"\n{SEP2}")
    print(f"  Streams  REF: {os.path.basename(ref_path)}")
    ref_pairs = print_av_streams(ref_streams)

    print(f"\n{SEP2}")
    print(f"  Streams  ALVO: {os.path.basename(tgt_path)}")
    tgt_pairs = print_av_streams(tgt_streams)

    # ── Subtitle selection for analysis ──────────────────────────────────
    print(f"\n{SEP2}")
    print("  Selecione as legendas para analise do pulo:")
    ref_sub = pick_stream(ref_pairs, "subtitle", "legenda da REFERENCIA")
    tgt_sub = pick_stream(tgt_pairs, "subtitle", "legenda do ALVO")

    if not ref_sub or not tgt_sub:
        print("  Legenda nao encontrada. Abortando.")
        return

    ref_fmt = detect_fmt(ref_sub.get("codec_name", ""))
    tgt_fmt = detect_fmt(tgt_sub.get("codec_name", ""))

    def stream_info(s, fmt):
        lang  = s.get("tags", {}).get("language", "?")
        title = s.get("tags", {}).get("title", "") or "(sem titulo)"
        return f"idx={s['index']} | {fmt.upper()} | {lang} | {title}"

    print(f"\n  REF selecionada : {stream_info(ref_sub, ref_fmt)}")
    print(f"  ALVO selecionada: {stream_info(tgt_sub, tgt_fmt)}")

    confirm = input("\n  Confirmar selecao? [S/N]: ").strip().upper()
    if confirm != "S":
        ref_sub = pick_stream(ref_pairs, "subtitle", "legenda da REFERENCIA")
        tgt_sub = pick_stream(tgt_pairs, "subtitle", "legenda do ALVO")
        ref_fmt = detect_fmt(ref_sub.get("codec_name", ""))
        tgt_fmt = detect_fmt(tgt_sub.get("codec_name", ""))
        print(f"\n  REF selecionada : {stream_info(ref_sub, ref_fmt)}")
        print(f"  ALVO selecionada: {stream_info(tgt_sub, tgt_fmt)}")

    # ── Work in temp dir ──────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:

        print(f"\n{SEP2}")
        print("  Extraindo legendas para analise...")
        ref_sub_raw = os.path.join(tmp, f"ref_ana.{ref_fmt}")
        tgt_sub_raw = os.path.join(tmp, f"tgt_ana.{tgt_fmt}")
        extract_subtitle(ref_path, ref_sub["index"], ref_sub_raw)
        extract_subtitle(tgt_path, tgt_sub["index"], tgt_sub_raw)
        print("  OK")

        if ref_fmt == "ass":
            _, ref_events = parse_ass(ref_sub_raw)
        else:
            ref_events = parse_srt(ref_sub_raw)

        if tgt_fmt == "ass":
            _, tgt_events = parse_ass(tgt_sub_raw)
        else:
            tgt_events = parse_srt(tgt_sub_raw)

        # ── Two-phase jump estimation ─────────────────────────────────────
        before_pairs, after_pairs, avg_before, avg_after, jump_ms = estimate_jump(
            ref_events, tgt_events, ref_fmt, tgt_fmt, cut_ref_ms,
            chapter_jump_ms=ch_jump_ms,
        )

        print(f"  Pares ANTES  encontrados: {len(before_pairs)}")
        print(f"  Pares DEPOIS encontrados: {len(after_pairs)}")

        # ── Comparison table ──────────────────────────────────────────────
        print(f"\n{SEP2}")
        print("  Dialogo ao redor do eyecatch (5 antes / 5 depois)\n")
        print(f"  {'REF':>7}  {'ALVO':>7}  {'delta':>8}  Texto")
        print(f"  {'-'*58}")

        all_pairs = [(r, t, tx, False) for r, t, tx in before_pairs] + \
                    [(r, t, tx, True)  for r, t, tx in after_pairs]
        show = before_pairs[-5:] + after_pairs[:5]

        if not show:
            print("  (nenhum par — verifique se os idiomas das legendas batem)")
        else:
            sep_printed = False
            for r, t, tx in show:
                if not sep_printed and r >= cut_ref_ms:
                    print(f"  {'.'*56}  <- Part B")
                    sep_printed = True
                diff = t - r
                print(f"  {ms_to_human(r):>7}  {ms_to_human(t):>7}  {diff:>+8.0f}ms  {tx[:36]}")

        # ── Jump report ───────────────────────────────────────────────────
        print(f"\n{SEP}")
        if not before_pairs and not after_pairs:
            print("  AVISO: sem pares para calcular pela legenda.")
        print(f"  [Legendas] Offset ANTES  eyecatch : {avg_before:>+8.1f} ms")
        print(f"  [Legendas] Offset DEPOIS eyecatch : {avg_after:>+8.1f} ms")
        print(f"  [Legendas] PULO DETECTADO         : {jump_ms:>+8.1f} ms  ({len(before_pairs)}+{len(after_pairs)} pares)")
        if ch_jump_ms is not None:
            print(f"  [Capitulos] PULO ESTIMADO         : {ch_jump_ms:>+8.1f} ms  <- PRIMARIO")
        print(SEP)

        # ── Confirm ───────────────────────────────────────────────────────
        # Escolhe o valor padrao: capitulos tem prioridade sobre legendas
        default_jump = ch_jump_ms if ch_jump_ms is not None else jump_ms
        default_src  = "capitulos" if ch_jump_ms is not None else "legendas"

        print(f"\n  Ajuste sugerido: {default_jump:+.0f} ms  [{default_src}]"
              f"  a partir de {ms_to_human(cut_ref_ms)}")
        if ch_jump_ms is not None and abs(jump_ms - ch_jump_ms) > 200:
            print(f"  (Legenda sugere {jump_ms:+.0f} ms — divergencia de "
                  f"{abs(jump_ms - ch_jump_ms):.0f} ms, preferindo capitulos)")
        print("  [S] Aplicar sugerido   [L] Usar valor das legendas"
              "   [N] Digitar manualmente   [C] Cancelar")
        resp = input("  > ").strip().upper()

        if resp == "C":
            print("  Cancelado.")
            return

        if resp == "L":
            apply_jump = jump_ms
        elif resp == "N":
            raw = input(
                "  Ajuste manual em ms\n"
                "  (+ = alvo atrasado, corta do inicio do seg2)\n"
                "  (- = alvo adiantado, insere silencio no inicio do seg2)\n"
                "  > "
            ).strip()
            try:
                apply_jump = float(raw)
            except ValueError:
                print("  Valor invalido. Abortando.")
                return
        else:   # S ou qualquer outra tecla
            apply_jump = default_jump

        jump_ms = apply_jump

        # cut point in TARGET timeline = ref boundary + constant offset before
        cut_tgt_ms = int(cut_ref_ms + avg_before)
        cut_tgt_s  = cut_tgt_ms / 1000.0
        jump_s     = jump_ms / 1000.0

        print(f"\n  Ajuste : {jump_ms:+.0f} ms")
        print(f"  Corte  : {ms_to_human(cut_tgt_ms)} no ALVO ({cut_tgt_ms} ms)")

        # ── Process audio streams ─────────────────────────────────────────
        tgt_audio = [s for _, s in tgt_pairs if s.get("codec_type") == "audio"]
        tgt_subs  = [s for _, s in tgt_pairs if s.get("codec_type") == "subtitle"]

        print(f"\n{SEP2}")
        print(f"  Processando {len(tgt_audio)} faixa(s) de audio...")
        audio_files, audio_meta = [], []
        for s in tgt_audio:
            idx   = s["index"]
            lang  = s.get("tags", {}).get("language", "")
            title = s.get("tags", {}).get("title", "")
            out   = os.path.join(tmp, f"audio_{idx}.flac")
            print(f"  [{idx}] {title or lang} ...", end=" ", flush=True)
            fix_audio_stream(tgt_path, idx, cut_tgt_s, jump_s, out)
            audio_files.append(out)
            audio_meta.append({"language": lang, "title": title})
            print("OK")

        # ── Process subtitle streams ──────────────────────────────────────
        print(f"\n{SEP2}")
        print(f"  Processando {len(tgt_subs)} faixa(s) de legenda...")
        sub_files, sub_meta = [], []
        for s in tgt_subs:
            idx    = s["index"]
            lang   = s.get("tags", {}).get("language", "")
            title  = s.get("tags", {}).get("title", "")
            codec  = s.get("codec_name", "")
            fmt    = detect_fmt(codec)
            ext    = "ass" if fmt == "ass" else "srt"
            out    = os.path.join(tmp, f"sub_{idx}_fixed.{ext}")
            print(f"  [{idx}] {title or lang} ({fmt.upper()}) ...", end=" ", flush=True)
            fix_subtitle_stream(tgt_path, idx, codec, cut_tgt_ms, int(jump_ms), out, tmp)
            sub_files.append(out)
            sub_meta.append({"language": lang, "title": title})
            print("OK")

        # ── Mux ──────────────────────────────────────────────────────────
        tgt_base  = os.path.splitext(os.path.basename(tgt_path))[0]
        tgt_dir   = os.path.dirname(tgt_path)
        sign      = "+" if jump_ms >= 0 else ""
        out_name  = f"{tgt_base}_eyepatch ({sign}{jump_ms:.0f}ms).mkv"
        out_path  = os.path.join(tgt_dir, out_name)

        print(f"\n{SEP2}")
        print(f"  Muxando...")
        print(f"  {out_name}")
        mux_output(tgt_path, audio_files, audio_meta, sub_files, sub_meta, out_path)

    print(f"\n{SEP}")
    print("  EYEPATCH concluido com sucesso.")
    print(SEP + "\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python eyepatch.py REF.mkv ALVO.mkv")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
