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

def find_part_b_ms(chapters):
    """Retorna o inicio do Part B em ms, ou None se nao encontrado."""
    for ch in chapters:
        title = ch.get("tags", {}).get("title", "").lower()
        if "part b" in title:
            return int(float(ch["start_time"]) * 1000)
    return None

def find_chapter_after_part_b(chapters):
    """Retorna o inicio (ms) do capitulo imediatamente apos o Part B."""
    found = False
    for ch in chapters:
        title = ch.get("tags", {}).get("title", "").lower()
        if found:
            return int(float(ch["start_time"]) * 1000)
        if "part b" in title:
            found = True
    return None

def chapter_jump_estimate(ref_chapters, tgt_chapters):
    """
    Estima o pulo usando diferenca de timestamps de capitulos.

    Se ambos tem Part B no mesmo instante mas o capitulo seguinte comeca
    em instantes diferentes, essa diferenca e o pulo total do eyecatch.

    Retorna (jump_ms, detalhes_str) ou (None, motivo_str).
    """
    ref_pb  = find_part_b_ms(ref_chapters)
    tgt_pb  = find_part_b_ms(tgt_chapters)
    ref_aft = find_chapter_after_part_b(ref_chapters)
    tgt_aft = find_chapter_after_part_b(tgt_chapters)

    if None in (ref_pb, tgt_pb, ref_aft, tgt_aft):
        return None, "capitulos insuficientes em um dos arquivos"

    cut_delta = tgt_pb - ref_pb      # delta no ponto de corte (~0ms)
    aft_delta = tgt_aft - ref_aft    # delta no capitulo seguinte
    jump      = aft_delta - cut_delta

    detail = (
        f"  Part B  REF={ms_to_human(ref_pb)}  ALVO={ms_to_human(tgt_pb)}"
        f"  (delta={cut_delta:+d}ms)\n"
        f"  Prox.cap REF={ms_to_human(ref_aft)}  ALVO={ms_to_human(tgt_aft)}"
        f"  (delta={aft_delta:+d}ms)"
    )
    return jump, detail


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
    r = subprocess.run(cmd, capture_output=True, text=True)
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
    AFTER_TOL    = 2_500    # apertado quando temos ancora por capitulo
    AFTER_TOL_FB = 6_000    # largo como fallback sem ancora

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

def fix_audio_stream(mkv_path, stream_info, cut_s, jump_s, out_audio, tmp_dir):
    """
    Divide o audio em cut_s e remove/insere jump_s segundos no inicio do seg2,
    preservando codec, bitrate, sample rate e canais originais.
    """
    abs_idx = stream_info["index"]
    codec_name = stream_info.get("codec_name", "aac")
    sample_rate = stream_info.get("sample_rate")
    channels = stream_info.get("channels")
    bit_rate = stream_info.get("bit_rate")
    
    # Mapeamentos de codec internos do ffmpeg (ex: pcm para mkv geralmente é pcm_s16le ou s24le)
    if "pcm" in codec_name:
        # Se for PCM, mantemos como s16le por padrão de segurança
        encoder = "pcm_s16le"
    elif codec_name == "dts":
         # FFmpeg dts encoder é experimental e muitas vezes problemático, dca é o decoder, ac3 é a melhor conversão nesses casos se dts estrito não for necessário
         # MAS para tentar manter igual, usamos dca
         encoder = "dca"
    elif codec_name == "aac":
        encoder = "aac"
    elif codec_name == "ac3":
         encoder = "ac3"
    elif codec_name == "eac3":
         encoder = "eac3"
    elif codec_name == "opus":
         encoder = "libopus"
    elif codec_name == "vorbis":
         encoder = "libvorbis"
    else:
        # Tenta usar o mesmo nome para o encoder
        encoder = codec_name

    cmd = [FFMPEG, "-y", "-i", mkv_path]
    
    # Monta as opções de codificação originais
    encode_opts = ["-c:a", encoder]
    if sample_rate:
        encode_opts.extend(["-ar", str(sample_rate)])
    if channels:
        encode_opts.extend(["-ac", str(channels)])
    if bit_rate:
         encode_opts.extend(["-b:a", str(bit_rate)])
    elif encoder == "aac":
         # Bitrate padrão de segurança se não informado e for aac
         encode_opts.extend(["-b:a", "192k"])

    if abs(jump_s) < 0.005:
        # Pequeno ajuste na chamada se não precisar de pulo
        cmd.extend(["-map", f"0:{abs_idx}"])
        cmd.extend(encode_opts)
        cmd.append(out_audio)
        
        r = subprocess.run(cmd, capture_output=True, text=True)
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
    
    cmd.extend(["-filter_complex", fc, "-map", "[out]"])
    cmd.extend(encode_opts)
    cmd.append(out_audio)
    
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou no audio {abs_idx}:\n{r.stderr[-600:]}")

def remove_eyecatch_duplicates(events, cut_ms, fmt):
    """
    Procura por diálogos duplicados na região do eyecatch (janela de ± 45s).
    Se encontrar falas idênticas, remove a PRIMEIRA e mantém a SEGUNDA,
    avisando o usuário no console.
    """
    window = 45000  # Procura num raio de 45 segundos ao redor do corte
    to_remove = set()
    
    for i in range(len(events)):
        if i in to_remove:
            continue
        ev1 = events[i]
        
        # Verifica se a linha está próxima do ponto de corte do eyecatch
        if not (cut_ms - window <= ev1["start_ms"] <= cut_ms + window):
            continue
            
        text1 = ev_text(ev1, fmt).strip()
        
        # Ignora falas muito curtas (evita apagar respostas genéricas como "sim.", "ah!", etc.)
        if len(text1) < 10:
            continue
            
        # Olha os próximos 10 eventos para frente
        for j in range(i + 1, min(i + 11, len(events))):
            if j in to_remove:
                continue
            ev2 = events[j]
            text2 = ev_text(ev2, fmt).strip()
            
            # Se o texto plain (sem tags, minúsculo) for idêntico, é a repetição
            if text1 == text2:
                to_remove.add(i) # Marca o PRIMEIRO evento para remoção
                
                # Prepara o log amigável para o console
                raw_text = ev1.get("rest", ev1.get("text", ""))
                raw_text = raw_text.replace(r"\N", " ").replace("\n", " ")
                if len(raw_text) > 55: 
                    raw_text = raw_text[:52] + "..."
                
                print(f"\n      [!] Repetição de Eyecatch resolvida:")
                print(f"          - Removido: [{ms_to_human(ev1['start_ms'])}] {raw_text}")
                print(f"          - Mantido : [{ms_to_human(ev2['start_ms'])}]")
                break
                
    # Remove os itens marcados, de trás pra frente (para manter os índices da lista intactos)
    for idx in sorted(list(to_remove), reverse=True):
        events.pop(idx)
        
    return events

# ─────────────────────────────────────────────────────────────────────────────
# Subtitle fix
# ─────────────────────────────────────────────────────────────────────────────

def fix_subtitle_stream(mkv_path, abs_idx, codec, cut_ms, jump_ms, out_path, tmp_dir):
    fmt = detect_fmt(codec)
    ext = "ass" if fmt == "ass" else "srt"
    raw = os.path.join(tmp_dir, f"raw_{abs_idx}.{ext}")
    extract_subtitle(mkv_path, abs_idx, raw)

    if fmt == "ass":
        header, events = parse_ass(raw)
        events = remove_eyecatch_duplicates(events, cut_ms, fmt) # <--- CHAMA A FUNÇÃO AQUI
        for ev in events:
            if ev["start_ms"] >= cut_ms:
                ev["start_ms"] -= jump_ms
                ev["end_ms"]   -= jump_ms
        write_ass(header, events, out_path)
    elif fmt == "srt":
        events = parse_srt(raw)
        events = remove_eyecatch_duplicates(events, cut_ms, fmt) # <--- CHAMA A FUNÇÃO AQUI
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

    r = subprocess.run(cmd, capture_output=True, text=True)
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
    cut_ref_ms   = find_part_b_ms(ref_chapters)

    if cut_ref_ms is None:
        print("  Capitulo 'Part B' nao encontrado na REF.")
        raw = input("  Informe o tempo de inicio do Part B em segundos: ").strip()
        cut_ref_ms = int(float(raw) * 1000)
    else:
        print(f"  Part B REF: {ms_to_human(cut_ref_ms)} ({cut_ref_ms} ms)")

    # Estimativa primaria pelo diff de capitulos
    ch_jump_ms, ch_detail = chapter_jump_estimate(ref_chapters, tgt_chapters)
    if ch_jump_ms is not None:
        print(f"\n{SEP2}")
        print("  Estimativa por capitulos (metodo primario):")
        print(ch_detail)
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
            
            # Pega o codec pra tentar usar a extensão certa (pra não dar pau no mkvmerge)
            codec_name = s.get("codec_name", "aac")
            if codec_name == "libopus" or codec_name == "opus": ext = "opus"
            elif codec_name == "vorbis": ext = "ogg"
            elif codec_name == "ac3" or codec_name == "eac3": ext = "ac3"
            elif codec_name == "dts" or codec_name == "dca": ext = "dts"
            elif "pcm" in codec_name: ext = "wav"
            else: ext = codec_name # fallback, ex: m4a/aac
            if ext == "aac": ext = "m4a"

            out = os.path.join(tmp, f"audio_{idx}.{ext}")
            
            print(f"  [{idx}] {title or lang} ({codec_name}) ...", end=" ", flush=True)
            fix_audio_stream(tgt_path, s, cut_tgt_s, jump_s, out, tmp)
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
