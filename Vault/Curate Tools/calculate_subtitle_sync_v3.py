# calculate_subtitle_sync_v3.py
# Sincroniza tempos de todas as faixas de legenda do Alvo com base na Referência.
import sys
import json
import subprocess
import os
import re
import difflib
import bisect

try:
    import win32com.client
except ImportError:
    print("Erro: pywin32 necessário. Instale com: pip install pywin32")
    sys.exit(1)
try:
    import pysrt
except ImportError:
    print("Erro: pysrt necessário. Instale com: pip install pysrt")
    sys.exit(1)

sys.stdout.reconfigure(line_buffering=True)

FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH  = r"C:\FFmpeg\bin\ffmpeg.exe"

LANGUAGE_PRIORITY = {
    'en': ['en', 'eng', 'english'],
    'es': ['es', 'spa', 'spanish'],
    'pt': ['pt', 'por', 'portuguese'],
    'fr': ['fr', 'fre', 'french'],
    'de': ['de', 'ger', 'german'],
    'it': ['it', 'ita', 'italian'],
    'ja': ['ja', 'jpn', 'japanese'],
    'ar': ['ar', 'ara', 'arabic'],
    'ru': ['ru', 'rus', 'russian'],
    'th': ['th', 'tha', 'thai'],
    'vi': ['vi', 'vie', 'vietnamese'],
    'ms': ['ms', 'may', 'malay'],
    'id': ['id', 'ind', 'indonesian'],
}

# ═══════════════════════════════════════════════════════════════════════════════
# Utilitários gerais
# ═══════════════════════════════════════════════════════════════════════════════

def die(msg):
    print(msg)
    print(msg, file=sys.stderr)
    sys.exit(1)

def resolve_lnk_path(file_path):
    try:
        if file_path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            resolved = shortcut.TargetPath
            if not os.path.exists(resolved):
                die(f"Erro: atalho aponta para arquivo inexistente: {resolved}")
            return resolved
        return file_path
    except Exception as e:
        die(f"Erro ao resolver atalho {file_path}: {e}")

def ffprobe_json(file_path):
    try:
        cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json", "-show_streams", file_path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            die(f"Erro ffprobe em {file_path}: {r.stderr}")
        return json.loads(r.stdout)
    except Exception as e:
        die(f"Erro ao processar ffprobe: {e}")

def get_subtitle_streams(data):
    subs = []
    for s in data.get("streams", []):
        if s.get("codec_type") == "subtitle":
            lang = s.get("tags", {}).get("language", "unknown").lower()
            dur_str = s.get("tags", {}).get("DURATION")
            if dur_str:
                h, m, sec = dur_str.split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(sec)
            else:
                duration = float(s.get("duration", 0))
            subs.append({
                "index":    s["index"],
                "lang":     lang,
                "duration": duration,
                "title":    s.get("tags", {}).get("title", "Sem título"),
                "codec":    s.get("codec_name", "unknown"),
            })
    return subs

def get_subtitle_stream_indices(data):
    return [s["index"] for s in data.get("streams", []) if s.get("codec_type") == "subtitle"]

# ═══════════════════════════════════════════════════════════════════════════════
# Extração de faixas
# ═══════════════════════════════════════════════════════════════════════════════

def _relative_index(data, subtitle_index):
    indices = get_subtitle_stream_indices(data)
    if subtitle_index not in indices:
        die(f"Índice {subtitle_index} não encontrado.")
    return indices.index(subtitle_index)

def extract_as_srt(file_path, subtitle_index, output_srt):
    """Extrai a faixa como .srt para comparação textual."""
    data = ffprobe_json(file_path)
    rel  = _relative_index(data, subtitle_index)
    stream = next(s for s in data["streams"] if s["index"] == subtitle_index)
    codec  = stream.get("codec_name", "unknown")
    if codec not in ["srt", "subrip", "ass", "ssa"]:
        die(f"Codec '{codec}' não suportado para extração.")
    cmd = [FFMPEG_PATH, "-y", "-i", file_path,
           "-map", f"0:s:{rel}", "-c:s", "srt", output_srt]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        die(f"Erro ao extrair legenda: {r.stderr}")
    if not os.path.exists(output_srt) or os.path.getsize(output_srt) == 0:
        die(f"Arquivo .srt não criado ou vazio: {output_srt}")
    return output_srt

def extract_native(file_path, subtitle_index, output_dir, name_hint):
    """Extrai a faixa no formato nativo (.ass ou .srt)."""
    data   = ffprobe_json(file_path)
    rel    = _relative_index(data, subtitle_index)
    stream = next(s for s in data["streams"] if s["index"] == subtitle_index)
    codec  = stream.get("codec_name", "unknown")
    if codec in ["ass", "ssa"]:
        ext        = ".ass"
        codec_flag = "ass"
    else:
        ext        = ".srt"
        codec_flag = "srt"
    out_path = os.path.join(output_dir, f"{name_hint}{ext}")
    cmd = [FFMPEG_PATH, "-y", "-i", file_path,
           "-map", f"0:s:{rel}", "-c:s", codec_flag, out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        die(f"Erro ao extrair faixa nativa {subtitle_index}: {r.stderr}")
    return out_path, ext

# ═══════════════════════════════════════════════════════════════════════════════
# Seleção de legendas
# ═══════════════════════════════════════════════════════════════════════════════

def is_signs_songs(sub):
    kws = ['sign', 'song', 'full subtitle', 'full sub']
    return any(k in sub['title'].lower() for k in kws)

def list_subtitles(subs, label):
    print(f"\nLegendas disponíveis no {label}:")
    for i, s in enumerate(subs, 1):
        print(f"  {i}. Lang={s['lang']}, Title=\"{s['title']}\", "
              f"Duração={s['duration']:.3f}s, Codec={s['codec']}")
    return subs

def select_subtitle(subs, label):
    while True:
        try:
            c = int(input(f"\nDigite o número da legenda para {label}: "))
            if 1 <= c <= len(subs):
                return subs[c - 1]
            print(f"Escolha entre 1 e {len(subs)}.")
        except ValueError:
            print("Número inválido.")

def auto_select_subtitle(subs, label):
    print(f"\nDepuração: Idiomas disponíveis em {label}: {[s['lang'] for s in subs]}")
    for lang_key, lang_codes in LANGUAGE_PRIORITY.items():
        matching = [s for s in subs if s['lang'] in lang_codes]
        if not matching:
            continue
        clean = [s for s in matching if not is_signs_songs(s)]
        if len(clean) == 1:
            print(f"Legenda selecionada automaticamente para {label}: "
                  f"Lang={clean[0]['lang']}, Title=\"{clean[0]['title']}\"")
            return clean[0]
        elif len(clean) > 1:
            print(f"\nMúltiplas faixas de diálogo para '{lang_key}' em {label}. Seleção manual:")
            list_subtitles(clean, f"{label} (idioma {lang_key})")
            return select_subtitle(clean, f"{label} (idioma {lang_key})")
        else:
            print(f"\nAVISO: A única faixa '{lang_key}' em {label} parece ser Signs & Songs ou similar.")
            print("Exibindo todas as faixas disponíveis:")
            list_subtitles(subs, label)
            return select_subtitle(subs, label)
    print(f"\nNenhum idioma prioritário encontrado em {label}. Seleção manual:")
    list_subtitles(subs, label)
    return select_subtitle(subs, label)

# ═══════════════════════════════════════════════════════════════════════════════
# Leitura de diálogos (via SRT) e matching
# ═══════════════════════════════════════════════════════════════════════════════

def clean_text(text):
    text = re.sub(r'\{[^}]*}', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    return ' '.join(text.split()).strip()

def read_srt_dialogues(srt_file, max_time=99999):
    encodings = ['utf-8', 'latin-1', 'cp1252']
    subs = None
    for enc in encodings:
        try:
            subs = pysrt.open(srt_file, encoding=enc)
            break
        except Exception:
            continue
    if not subs:
        die(f"Não foi possível ler {srt_file}")
    dialogues = []
    seen = set()
    for sub in subs:
        cleaned = clean_text(sub.text.replace('\n', ' '))
        if len(cleaned) > 10 and len(cleaned.split()) > 1:
            st = (sub.start.hours * 3600 + sub.start.minutes * 60
                  + sub.start.seconds + sub.start.milliseconds / 1000)
            et = (sub.end.hours * 3600 + sub.end.minutes * 60
                  + sub.end.seconds + sub.end.milliseconds / 1000)
            if st > max_time:
                continue
            key = (cleaned, round(st, 2), round(et, 2))
            if key not in seen:
                seen.add(key)
                dialogues.append({
                    "index":      sub.index,
                    "text":       cleaned,
                    "start_time": st,
                    "end_time":   et,
                })
    if not dialogues:
        die(f"Nenhum diálogo válido em {srt_file}")
    return dialogues

def find_best_matches(ref_all, tgt_all, threshold=0.6):
    """
    Para cada diálogo da Referência, encontra o melhor par no Alvo por similaridade.
    Sem reutilização. Retorna pares ordenados cronologicamente pela Referência.
    """
    used = set()
    pairs = []
    for ref_d in ref_all:
        best_tgt   = None
        best_ratio = 0
        for i, tgt_d in enumerate(tgt_all):
            if i in used:
                continue
            ratio = difflib.SequenceMatcher(None, ref_d['text'], tgt_d['text']).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_tgt   = (i, tgt_d)
        if best_tgt is not None:
            used.add(best_tgt[0])
            pairs.append((ref_d, best_tgt[1], best_ratio))
    return pairs

# ═══════════════════════════════════════════════════════════════════════════════
# Mapeamento de tempo
# ═══════════════════════════════════════════════════════════════════════════════

def build_time_map(matched_pairs):
    """
    Constrói uma função de interpolação linear:  tempo_alvo_original → tempo_referência.
    Âncoras: cada par matched fornece (tgt_start, ref_start).
    Extrapolação linear nas extremidades.
    """
    anchors    = sorted((tgt['start_time'], ref['start_time']) for ref, tgt, _ in matched_pairs)
    tgt_times  = [a[0] for a in anchors]
    ref_times  = [a[1] for a in anchors]

    def slope(i):
        dt = tgt_times[i + 1] - tgt_times[i]
        return (ref_times[i + 1] - ref_times[i]) / dt if dt != 0 else 1.0

    def interpolate(t):
        if not anchors:
            return t
        if len(anchors) == 1:
            return ref_times[0] + (t - tgt_times[0])
        if t <= tgt_times[0]:
            return ref_times[0] + slope(0) * (t - tgt_times[0])
        if t >= tgt_times[-1]:
            return ref_times[-1] + slope(-2) * (t - tgt_times[-1])
        idx = bisect.bisect_right(tgt_times, t) - 1
        t0, t1 = tgt_times[idx], tgt_times[idx + 1]
        r0, r1 = ref_times[idx], ref_times[idx + 1]
        frac   = (t - t0) / (t1 - t0) if (t1 - t0) != 0 else 0
        return r0 + frac * (r1 - r0)

    return interpolate

# ═══════════════════════════════════════════════════════════════════════════════
# Parser / Writer de ASS
# ═══════════════════════════════════════════════════════════════════════════════

def ass_time_to_sec(t):
    """H:MM:SS.cc → segundos"""
    h, m, rest = t.split(':')
    s, cs = rest.split('.')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100

def sec_to_ass_time(sec):
    """segundos → H:MM:SS.cc"""
    sec = max(0.0, sec)
    h   = int(sec // 3600);  sec -= h * 3600
    m   = int(sec // 60);    sec -= m * 60
    s   = int(sec)
    cs  = min(99, round((sec - s) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def parse_ass(path):
    """
    Lê um arquivo .ass.
    Retorna (header_lines, events) onde events é lista de dicts com campos parseados.
    Eventos do tipo 'dialogue' e 'comment' têm start_sec/end_sec modificáveis.
    """
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        lines = f.readlines()

    header         = []
    events         = []
    in_events      = False
    events_format  = []

    for line in lines:
        stripped = line.rstrip('\r\n')
        low      = stripped.strip().lower()

        if low == '[events]':
            in_events = True
            header.append(line)
            continue

        if not in_events:
            header.append(line)
            continue

        # Dentro da seção [Events]
        if low.startswith('format:'):
            header.append(line)
            events_format = [f.strip() for f in stripped[7:].split(',')]
            continue

        is_dialogue = low.startswith('dialogue:')
        is_comment  = low.startswith('comment:')

        if is_dialogue or is_comment:
            keyword    = 'Dialogue' if is_dialogue else 'Comment'
            prefix_len = 9 if is_dialogue else 8  # "Dialogue:" / "Comment:"
            n_fields   = len(events_format) if events_format else 10

            try:
                content = stripped[prefix_len:].lstrip(' ')
                parts   = content.split(',', n_fields - 1)

                if events_format:
                    si = events_format.index('Start')
                    ei = events_format.index('End')
                else:
                    si, ei = 1, 2

                start_sec = ass_time_to_sec(parts[si].strip())
                end_sec   = ass_time_to_sec(parts[ei].strip())

                events.append({
                    'type':          'dialogue' if is_dialogue else 'comment',
                    'keyword':       keyword,
                    'start_sec':     start_sec,
                    'end_sec':       end_sec,
                    'parts':         parts,
                    'start_idx':     si,
                    'end_idx':       ei,
                    'original_line': line,
                })
            except Exception:
                # Linha mal formada → preserva no cabeçalho
                header.append(line)
            continue

        # Outras linhas dentro de [Events] (linhas em branco, etc.)
        header.append(line)

    return header, events

def write_ass(header, events, out_path):
    """Escreve um .ass com os eventos modificados."""
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        for line in header:
            f.write(line if line.endswith('\n') else line + '\n')
        for e in events:
            parts = list(e['parts'])
            parts[e['start_idx']] = sec_to_ass_time(e['start_sec'])
            parts[e['end_idx']]   = sec_to_ass_time(e['end_sec'])
            f.write(f"{e['keyword']}: {','.join(parts)}\n")

# ═══════════════════════════════════════════════════════════════════════════════
# Parser / Writer de SRT
# ═══════════════════════════════════════════════════════════════════════════════

def parse_srt(path):
    encodings = ['utf-8', 'latin-1', 'cp1252']
    subs = None
    for enc in encodings:
        try:
            subs = pysrt.open(path, encoding=enc)
            break
        except Exception:
            continue
    if not subs:
        die(f"Não foi possível ler {path}")
    entries = []
    for s in subs:
        st = s.start.hours*3600 + s.start.minutes*60 + s.start.seconds + s.start.milliseconds/1000
        et = s.end.hours*3600   + s.end.minutes*60   + s.end.seconds   + s.end.milliseconds/1000
        entries.append({
            'type':      'dialogue',
            'start_sec': st,
            'end_sec':   et,
            'text':      s.text,
            'index':     s.index,
        })
    return entries

def write_srt(entries, out_path):
    def fmt(sec):
        sec = max(0.0, sec)
        h = int(sec // 3600);  sec -= h * 3600
        m = int(sec // 60);    sec -= m * 60
        s = int(sec)
        ms = min(999, round((sec - s) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\n{fmt(e['start_sec'])} --> {fmt(e['end_sec'])}\n{e['text']}\n\n")

# ═══════════════════════════════════════════════════════════════════════════════
# Aplicação do mapeamento a uma faixa
# ═══════════════════════════════════════════════════════════════════════════════

def apply_transform(entries, time_map_fn, removed_start_times, tolerance=0.15):
    """
    Aplica a função de tempo a todos os eventos.
    Remove eventos cujo start_sec esteja dentro da tolerância de qualquer
    tempo marcado para remoção.
    Retorna (kept, removed).
    """
    removed = []
    kept    = []
    for e in entries:
        if e.get('type') == 'dialogue':
            t = e['start_sec']
            if any(abs(t - rt) <= tolerance for rt in removed_start_times):
                removed.append(e)
                continue
        new_e = dict(e)
        if 'parts' in e:
            new_e['parts'] = list(e['parts'])
        new_e['start_sec'] = time_map_fn(e['start_sec'])
        new_e['end_sec']   = time_map_fn(e['end_sec'])
        kept.append(new_e)
    return kept, removed

# ═══════════════════════════════════════════════════════════════════════════════
# Fluxo principal
# ═══════════════════════════════════════════════════════════════════════════════

def sync_subtitles(ref_path, tgt_path):
    ref_path = resolve_lnk_path(ref_path)
    tgt_path = resolve_lnk_path(tgt_path)

    ref_data = ffprobe_json(ref_path)
    tgt_data = ffprobe_json(tgt_path)

    ref_subs = get_subtitle_streams(ref_data)
    tgt_subs = get_subtitle_streams(tgt_data)

    if not ref_subs:
        die("Erro: Nenhuma legenda encontrada na Referência.")
    if not tgt_subs:
        die("Erro: Nenhuma legenda encontrada no Alvo.")

    list_subtitles(ref_subs, "Referência")
    list_subtitles(tgt_subs, "Alvo")

    ref_sel = auto_select_subtitle(ref_subs, "Referência")
    tgt_sel = auto_select_subtitle(tgt_subs, "Alvo")

    max_time = ref_sel["duration"] * 0.95

    # ── Extrai faixas de comparação como SRT ──────────────────────────────────
    ref_srt_tmp = "temp_ref_cmp.srt"
    tgt_srt_tmp = "temp_tgt_cmp.srt"
    extract_as_srt(ref_path, ref_sel["index"], ref_srt_tmp)
    extract_as_srt(tgt_path, tgt_sel["index"], tgt_srt_tmp)

    ref_all = read_srt_dialogues(ref_srt_tmp, max_time)
    tgt_all = read_srt_dialogues(tgt_srt_tmp, max_time)

    # ── Match de diálogos ─────────────────────────────────────────────────────
    print("\nBuscando correspondências entre diálogos...")
    all_pairs = find_best_matches(ref_all, tgt_all, threshold=0.6)

    if len(all_pairs) < 6:
        print(f"\nAVISO: Apenas {len(all_pairs)} pares encontrados. "
              "Pode ser insuficiente para sincronização precisa.")

    # ── Exibe 3 primeiros e 3 últimos pares ──────────────────────────────────
    def fmt_pair(label, pairs):
        print(f"\n=== {label} ===")
        for i, (ref_d, tgt_d, ratio) in enumerate(pairs, 1):
            diff_ms = int((ref_d['start_time'] - tgt_d['start_time']) * 1000)
            sim_str = f", sim={ratio:.2f}" if ratio < 1.0 else ""
            print(f"  [{i}] (Δ {diff_ms:+d}ms{sim_str})")
            print(f"    REF: {ref_d['start_time']:.3f}s → {ref_d['text']}")
            print(f"    ALV: {tgt_d['start_time']:.3f}s → {tgt_d['text']}")

    fmt_pair("3 Primeiros Pares Correspondentes", all_pairs[:3])
    fmt_pair("3 Últimos Pares Correspondentes",   all_pairs[-3:])

    # ── Contagem entre âncoras ────────────────────────────────────────────────
    if len(all_pairs) >= 6:
        anchor_ref_start = all_pairs[2][0]['start_time']
        anchor_ref_end   = all_pairs[-3][0]['start_time']
        anchor_tgt_start = all_pairs[2][1]['start_time']
        anchor_tgt_end   = all_pairs[-3][1]['start_time']

        ref_between = sum(1 for d in ref_all
                          if anchor_ref_start <= d['start_time'] <= anchor_ref_end)
        tgt_between = sum(1 for d in tgt_all
                          if anchor_tgt_start <= d['start_time'] <= anchor_tgt_end)

        print(f"\n=== Diálogos entre âncoras (3º primeiro → 1º último par) ===")
        print(f"  Referência: {ref_between} diálogos  "
              f"({anchor_ref_start:.1f}s → {anchor_ref_end:.1f}s)")
        print(f"  Alvo:       {tgt_between} diálogos  "
              f"({anchor_tgt_start:.1f}s → {anchor_tgt_end:.1f}s)")

        if ref_between != tgt_between:
            diff = tgt_between - ref_between
            sinal = "a mais" if diff > 0 else "a menos"
            print(f"\n  AVISO: O Alvo tem {abs(diff)} diálogo(s) {sinal} que a Referência nesta região.")
            print("  Isso pode indicar cortes diferentes entre os releases.")
            resp = input("\nDeseja continuar mesmo assim? (s/n): ").strip().lower()
            if resp != 's':
                print("Operação cancelada pelo usuário.")
                try:
                    os.remove(ref_srt_tmp)
                    os.remove(tgt_srt_tmp)
                except Exception:
                    pass
                sys.exit(0)
        else:
            print("  OK: Contagem de diálogos igual nas duas legendas nessa região.")

    # ── Identifica diálogos sem correspondência ───────────────────────────────
    matched_tgt_times  = {round(tgt['start_time'], 3) for _, tgt, _ in all_pairs}
    removed_dialogues  = [d for d in tgt_all
                          if round(d['start_time'], 3) not in matched_tgt_times]
    removed_start_times = {d['start_time'] for d in removed_dialogues}

    print(f"\n=== Sumário ===")
    print(f"  Pares encontrados:                      {len(all_pairs)}")
    print(f"  Diálogos Alvo sem correspondência:      {len(removed_dialogues)}  (serão removidos)")

    # ── Constrói mapa de tempo ────────────────────────────────────────────────
    time_map_fn = build_time_map(all_pairs)

    # ── Verifica consistência estrutural entre faixas do Alvo ─────────────────
    tgt_compare_count = len(tgt_all)
    print(f"\n=== Verificando estrutura das faixas do Alvo ===")

    # ── Processa e exporta todas as faixas do Alvo ────────────────────────────
    output_dir  = os.path.dirname(os.path.abspath(sys.argv[0]))
    tgt_base    = os.path.splitext(os.path.basename(tgt_path))[0]
    tmp_dir     = output_dir

    print(f"\n=== Processando e exportando faixas do Alvo ===")

    all_removed_entries = {}  # idx → lista de entries removidos

    for sub_info in tgt_subs:
        idx   = sub_info['index']
        lang  = sub_info['lang']
        title = sub_info['title']
        codec = sub_info['codec']

        print(f"\n  Faixa [{idx}] Lang={lang}, Title=\"{title}\", Codec={codec}")

        # Extrai no formato nativo
        tmp_name = f"temp_tgt_native_{idx}"
        try:
            native_path, native_ext = extract_native(tgt_path, idx, tmp_dir, tmp_name)
        except SystemExit:
            print(f"    AVISO: Falha ao extrair faixa {idx}. Pulando.")
            continue

        # Faz parse
        if native_ext == ".ass":
            header, entries = parse_ass(native_path)
        else:
            entries = parse_srt(native_path)
            header  = None

        # Verifica estrutura vs faixa de comparação
        dialogue_count = sum(1 for e in entries if e.get('type') == 'dialogue')
        if idx != tgt_sel['index'] and dialogue_count != tgt_compare_count:
            print(f"    AVISO: Esta faixa tem {dialogue_count} diálogos; "
                  f"a faixa de comparação tem {tgt_compare_count}. "
                  "Remoções por proximidade temporal (tolerância 150ms).")

        # Aplica transformação
        kept, removed = apply_transform(entries, time_map_fn, removed_start_times)
        all_removed_entries[idx] = {'info': sub_info, 'removed': removed}

        # Nome do arquivo de saída
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        out_name   = f"{tgt_base}_sync_{lang}_{safe_title}{native_ext}"
        out_path   = os.path.join(output_dir, out_name)

        if native_ext == ".ass":
            write_ass(header, kept, out_path)
        else:
            write_srt(kept, out_path)

        print(f"    Exportado: {out_name}")
        print(f"    Entradas mantidas: {len(kept)}   |   Removidas: {len(removed)}")

        # Remove temporário
        try:
            os.remove(native_path)
        except Exception:
            pass

    # ── Limpa SRTs temporários ────────────────────────────────────────────────
    for f in [ref_srt_tmp, tgt_srt_tmp]:
        try:
            os.remove(f)
        except Exception:
            pass

    # ── Exibe todos os diálogos removidos ────────────────────────────────────
    print("\n" + "═" * 60)
    print("DIÁLOGOS REMOVIDOS DO ALVO")
    print("═" * 60)
    print(f"(Baseado na faixa de comparação: "
          f"Lang={tgt_sel['lang']}, Title=\"{tgt_sel['title']}\")\n")

    if not removed_dialogues:
        print("  Nenhum diálogo removido.")
    else:
        for i, d in enumerate(removed_dialogues, 1):
            print(f"  [{i:3d}] {d['start_time']:.3f}s – {d['end_time']:.3f}s")
            print(f"         \"{d['text']}\"")

    print("\n" + "═" * 60)
    print("EXPORTAÇÃO CONCLUÍDA")
    print(f"Arquivos salvos em: {output_dir}")
    print("═" * 60 + "\n")


def main():
    if len(sys.argv) < 3:
        die("Uso: python calculate_subtitle_sync_v3.py <arquivo_REFERENCIA> <arquivo_ALVO>")

    ref_path = sys.argv[1]
    tgt_path = sys.argv[2]

    # Remove aspas extras que o Windows pode adicionar
    ref_path = ref_path.strip('"')
    tgt_path = tgt_path.strip('"')

    print(f"Referência: {ref_path}")
    print(f"Alvo:       {tgt_path}")

    sync_subtitles(ref_path, tgt_path)


if __name__ == "__main__":
    main()
