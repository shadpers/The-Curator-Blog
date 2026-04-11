import subprocess
import sys
import os
import json
import ctypes
import tempfile
import shutil
import re

# Habilita ANSI no terminal Windows
try:
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

FFMPEG_PATH      = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH     = r"C:\FFmpeg\bin\ffprobe.exe"
MKVEXTRACT_PATH  = r"C:\Program Files\MKVToolNix\mkvextract.exe"
MKVMERGE_PATH    = r"C:\Program Files\MKVToolNix\mkvmerge.exe"

# Cores ANSI — branco explícito para texto comum
WHITE  = "\033[97m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SEP  = f"{DIM}{'─' * 60}{RESET}"
SEP2 = f"{DIM}{'═' * 60}{RESET}"

# ─────────────────────────────────────────────
# Google Drive: verifica se arquivo está local
# ─────────────────────────────────────────────

def is_offline_available(path):
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:
            return False
        return not (attrs & 0x400000) and not (attrs & 0x40000)
    except Exception:
        return True

# ─────────────────────────────────────────────
# Classificação
# ─────────────────────────────────────────────

def classify(diff_ms):
    abs_diff = abs(diff_ms)
    if abs_diff <= 50:
        return "Perfeito", BLUE
    elif abs_diff <= 1000:
        return "Bom",      GREEN
    elif abs_diff <= 2000:
        return "Ruim",     YELLOW
    else:
        return "Horrível", RED

def colored(text, color):
    return f"{color}{text}{RESET}{WHITE}"

def bold(text):
    return f"{BOLD}{WHITE}{text}{RESET}{WHITE}"

def dim(text):
    return f"{DIM}{text}{RESET}{WHITE}"

# ─────────────────────────────────────────────
# FFprobe helpers
# ─────────────────────────────────────────────

def get_metadata(input_file):
    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='ignore')
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}

def parse_duration(stream):
    raw = stream.get("duration")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    raw = stream.get("tags", {}).get("DURATION") or stream.get("tags", {}).get("duration")
    if raw and ":" in raw:
        try:
            parts = raw.split(":")
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except Exception:
            pass
    return None

def analyze_file(input_file):
    """
    Compara a duração do vídeo contra o tempo do container ou a faixa de áudio mais longa.
    Também rastreia QUAIS faixas de legenda estão ultrapassando o vídeo (Fantasmas).
    """
    metadata = get_metadata(input_file)
    if not metadata:
        return None

    streams    = metadata.get("streams", [])
    format_info = metadata.get("format", {})

    video_dur    = None
    audio_durs   = []
    phantom_subs = []

    for s in streams:
        ct = s.get("codec_type")
        d  = parse_duration(s)
        if d is None:
            continue
        if ct == "video" and video_dur is None:
            video_dur = d
        elif ct == "audio":
            audio_durs.append(d)

    if video_dur is None:
        return None

    for s in streams:
        if s.get("codec_type") == "subtitle":
            d = parse_duration(s)
            if d is not None and (d - video_dur) > 0.05:
                idx   = s.get("index")
                tags  = s.get("tags", {})
                title = tags.get("title") or tags.get("TITLE")
                lang  = tags.get("language") or tags.get("LANGUAGE") or "Desconhecido"
                name  = title if title else f"Idioma: {lang.upper()}"
                phantom_subs.append(f"Faixa {idx} [{name}]")

    try:
        format_dur = float(format_info.get("duration", 0))
    except ValueError:
        format_dur = 0

    max_dur = format_dur
    if audio_durs:
        max_audio = max(audio_durs)
        if max_audio > max_dur:
            max_dur = max_audio

    if max_dur > 0:
        diff_ms = round((video_dur - max_dur) * 1000)
    else:
        diff_ms = round((video_dur - max(audio_durs)) * 1000) if audio_durs else 0

    return {
        "video_dur":    video_dur,
        "audio_durs":   audio_durs,
        "diff_ms":      diff_ms,
        "phantom_subs": phantom_subs,
    }

# ─────────────────────────────────────────────
# MKVMerge: leitura de faixas (JSON)
# ─────────────────────────────────────────────

def get_mkv_tracks(input_file):
    """Retorna a lista de faixas do mkvmerge -J, ou [] em caso de erro."""
    result = subprocess.run(
        [MKVMERGE_PATH, "-J", input_file],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="ignore"
    )
    try:
        data = json.loads(result.stdout)
        return data.get("tracks", [])
    except Exception:
        return []

# ─────────────────────────────────────────────
# Correção de timestamps .ASS — O "Ghost Killer"
# ─────────────────────────────────────────────

def _ass_time_to_cs(t: str) -> int:
    """'H:MM:SS.cc' → centésimos de segundo."""
    h, m, rest = t.strip().split(":")
    s, cs = rest.split(".")
    return int(h) * 360000 + int(m) * 6000 + int(s) * 100 + int(cs)

def _cs_to_ass_time(cs: int) -> str:
    """centésimos de segundo → 'H:MM:SS.cc'."""
    h = cs // 360000; cs %= 360000
    m = cs // 6000;   cs %= 6000
    s = cs // 100;    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def fix_ass_timestamps(ass_path: str, max_seconds: float) -> int:
    """
    Lê o arquivo .ass e:
      - Corta o End de todo evento que ultrapasse max_seconds.
      - Remove eventos cujo Start já ultrapassou max_seconds.
    Retorna a quantidade de linhas modificadas/removidas.
    """
    max_cs = int(max_seconds * 100)

    try:
        with open(ass_path, "r", encoding="utf-8-sig", errors="ignore") as fh:
            raw = fh.read()
    except OSError:
        return 0

    # Detecta terminador de linha do arquivo original
    linesep = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines()

    in_events     = False
    format_fields = []
    new_lines     = []
    modified      = 0

    for line in lines:
        stripped = line.strip()

        # Seção [Events]
        if re.match(r"^\[Events\]$", stripped, re.IGNORECASE):
            in_events = True
            new_lines.append(line)
            continue
        elif stripped.startswith("[") and stripped.endswith("]") and in_events:
            in_events = False

        if in_events:
            # Linha Format: descobre a posição dos campos Start e End
            m = re.match(r"^Format\s*:", stripped, re.IGNORECASE)
            if m:
                format_fields = [f.strip().lower()
                                 for f in stripped[stripped.index(":") + 1:].split(",")]
                new_lines.append(line)
                continue

            # Linha Dialogue: ou Comment:
            m = re.match(r"^(Dialogue|Comment)\s*:", stripped, re.IGNORECASE)
            if m and format_fields:
                prefix_end = line.index(":") + 1
                prefix     = line[:prefix_end]          # "Dialogue:" (mantém espaços originais)
                rest       = line[prefix_end:]           # tudo após ':'

                # Divide em exatamente N campos (o último = texto, pode ter vírgulas)
                n = len(format_fields)
                parts = rest.split(",", n - 1)

                if len(parts) == n:
                    try:
                        si = format_fields.index("start")
                        ei = format_fields.index("end")

                        start_cs = _ass_time_to_cs(parts[si])
                        end_cs   = _ass_time_to_cs(parts[ei])

                        if start_cs >= max_cs:
                            # Evento inteiramente após o corte → descarta
                            modified += 1
                            continue

                        if end_cs > max_cs:
                            # Evento atravessa o corte → clipa o End
                            parts[ei] = _cs_to_ass_time(max_cs)
                            line = prefix + ",".join(parts)
                            modified += 1

                    except (ValueError, IndexError):
                        pass  # Linha malformada: passa intacta

        new_lines.append(line)

    if modified > 0:
        out = linesep.join(new_lines) + linesep
        with open(ass_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)

    return modified

# ─────────────────────────────────────────────
# Fixador SRT (bônus, para arquivos mistos)
# ─────────────────────────────────────────────

def _srt_time_to_ms(t: str) -> int:
    h, m, rest = t.strip().split(":")
    s, ms = rest.replace(",", ".").split(".")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

def _ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000; ms %= 3600000
    m = ms // 60000;   ms %= 60000
    s = ms // 1000;    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def fix_srt_timestamps(srt_path: str, max_seconds: float) -> int:
    max_ms = int(max_seconds * 1000)

    try:
        with open(srt_path, "r", encoding="utf-8-sig", errors="ignore") as fh:
            raw = fh.read()
    except OSError:
        return 0

    linesep  = "\r\n" if "\r\n" in raw else "\n"
    pattern  = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
    )

    # Divide o SRT em blocos por linha em branco dupla
    blocks   = re.split(r"\n\s*\n", raw.strip())
    new_blocks = []
    modified   = 0

    for block in blocks:
        m = pattern.search(block)
        if not m:
            new_blocks.append(block)
            continue

        start_ms = _srt_time_to_ms(m.group(1))
        end_ms   = _srt_time_to_ms(m.group(2))

        if start_ms >= max_ms:
            modified += 1
            continue  # descarta bloco inteiramente

        if end_ms > max_ms:
            new_end  = _ms_to_srt_time(max_ms)
            block    = block[:m.start(2)] + new_end + block[m.end(2):]
            modified += 1

        new_blocks.append(block)

    if modified > 0:
        out = (linesep + linesep).join(new_blocks) + linesep
        with open(srt_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)

    return modified

# ─────────────────────────────────────────────
# Pipeline de extensões por codec_id
# ─────────────────────────────────────────────

# Mapa principal: codec_id interno do Matroska (campo em properties)
# → (extensão de extração, pode_corrigir_timestamps)
_CODEC_ID_MAP = {
    "S_TEXT/ASS":   (".ass", True),
    "S_TEXT/SSA":   (".ass", True),
    "S_TEXT/UTF8":  (".srt", True),
    "S_TEXT/ASCII": (".srt", True),
    "S_HDMV/PGS":   (".sup", False),
    "S_DVBT":       (".sub", False),
    "S_VOBSUB":     (".sub", False),
}

# Fallback: nome legível que o mkvmerge -J coloca no campo "codec" (topo da faixa)
# Usa correspondência por substring para ser tolerante a variações de capitalização
_CODEC_NAME_MAP = [
    ("substation",  ".ass", True),   # "SubStationAlpha", "SSA"
    ("ass",         ".ass", True),
    ("ssa",         ".ass", True),
    ("subrip",      ".srt", True),   # "SubRip/SRT"
    ("srt",         ".srt", True),
    ("utf",         ".srt", True),   # "UTF-8 Plain Text"
    ("pgs",         ".sup", False),  # "HDMV PGS"
    ("hdmv",        ".sup", False),
    ("vobsub",      ".sub", False),
    ("dvd",         ".sub", False),
]

def _codec_ext_fixable(codec_id_internal: str, codec_name: str):
    """
    Tenta resolver a extensão e se o codec é fixável.
    Prioridade: codec_id interno (de properties) > nome legível (campo 'codec').
    Retorna (ext, fixável) ou None se desconhecido.
    """
    # 1ª tentativa: codec_id interno exato (ex: "S_TEXT/ASS")
    result = _CODEC_ID_MAP.get(codec_id_internal.upper())
    if result:
        return result

    # 2ª tentativa: nome legível por substring (ex: "SubStationAlpha")
    name_lower = codec_name.lower()
    for keyword, ext, fixable in _CODEC_NAME_MAP:
        if keyword in name_lower:
            return (ext, fixable)

    return None

# ─────────────────────────────────────────────
# Processamento principal — Pipeline 4 etapas
# ─────────────────────────────────────────────

def process_file(input_file, info, index, total):
    print(f"\n{SEP}")
    print(f"{WHITE}  {bold('[' + str(index) + '/' + str(total) + ']')} {os.path.basename(input_file)}{RESET}")
    print(SEP)

    video_dur   = info["video_dur"]
    base, ext   = os.path.splitext(input_file)
    output_file = f"{base} (cuted){ext}"

    # Diretório temporário ao lado do arquivo de entrada
    tmp_dir = tempfile.mkdtemp(dir=os.path.dirname(input_file) or ".")

    try:
        # ── Etapa 1: Descobrir as faixas de legenda ──────────────────────
        mkv_tracks = get_mkv_tracks(input_file)
        sub_tracks = [t for t in mkv_tracks if t.get("type") == "subtitles"]
        has_subs   = bool(sub_tracks)

        # ── Etapa 2: FFmpeg — corta vídeo + áudio, sem legendas ──────────
        tmp_nosub = os.path.join(tmp_dir, "_nosub.mkv")

        # Usa "0:V" (maiúsculo) para excluir streams de imagem estática (cover art,
        # MPNG, etc.) que o FFmpeg classifica como vídeo mas não possuem framerate real.
        # "-map 0:v" (minúsculo) os incluía, gerando a faixa fantasma no MKV final.
        map_args = ["-map", "0:V", "-map", "0:a"] if has_subs else ["-map", "0"]
        ffmpeg_cmd = [
            FFMPEG_PATH, "-y", "-v", "error", "-stats",
            "-i", input_file,
            *map_args,
            "-map_metadata", "0",
            "-map_chapters", "0",
            "-fflags", "+bitexact",   # suprime tag "encoder" que o FFmpeg insere automaticamente
            "-to", str(video_dur),
            "-c", "copy",
            tmp_nosub
        ]

        sub_label = (f" {dim('(legendas serão corrigidas separadamente)')}"
                     if has_subs else "")
        print(f"{WHITE}  {dim('Saída: ' + os.path.basename(output_file))}{sub_label}\n{RESET}")

        result = subprocess.run(ffmpeg_cmd)
        if result.returncode != 0:
            print(f"\n{WHITE}  {colored('✘ Erro no FFmpeg (etapa de corte A/V)', RED)}{RESET}")
            return False

        # ── Etapa 3: Extrair + Corrigir legendas ─────────────────────────
        mkvmerge_sub_args = []   # argumentos extras para o mkvmerge final

        for track in sub_tracks:
            tid         = track["id"]
            props       = track.get("properties", {})
            # codec_id interno fica em properties; "codec" no topo é o nome legível
            codec_id    = props.get("codec_id", "")          # ex: "S_TEXT/ASS"
            codec_name  = track.get("codec", "")             # ex: "SubStationAlpha"

            ext_info = _codec_ext_fixable(codec_id, codec_name)
            if ext_info is None:
                print(f"  {dim(f'  ⚠ Codec desconhecido ({codec_id or codec_name!r}) na faixa {tid} — ignorada.')}{RESET}")
                continue

            sub_ext, can_fix = ext_info
            tmp_sub = os.path.join(tmp_dir, f"sub_{tid}{sub_ext}")

            # Extrai a faixa original (sem corte)
            extract_result = subprocess.run(
                [MKVEXTRACT_PATH, "tracks", input_file, f"{tid}:{tmp_sub}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="ignore"
            )

            if not os.path.exists(tmp_sub) or os.path.getsize(tmp_sub) == 0:
                print(f"  {dim(f'  ⚠ Falha ao extrair faixa {tid} ({codec_id}) — ignorada.')}{RESET}")
                continue

            # Corrige timestamps se for um formato de texto suportado
            if can_fix:
                if sub_ext == ".ass":
                    n = fix_ass_timestamps(tmp_sub, video_dur)
                elif sub_ext == ".srt":
                    n = fix_srt_timestamps(tmp_sub, video_dur)
                else:
                    n = 0

                fix_note = (f" {colored(f'({n} evento(s) corrigido(s))', GREEN)}"
                            if n > 0 else f" {dim('(sem eventos fantasma)')}")
            else:
                fix_note = f" {dim('(imagem, não modificada)')}"

            track_name = props.get("track_name", "")
            lang       = props.get("language", "und")
            codec_label = codec_id if codec_id else codec_name
            print(f"  {dim(f'  Faixa {tid} [{codec_label}] {track_name}')}{fix_note}{RESET}")

            # Monta os argumentos de metadados para o mkvmerge
            default_yn = "yes" if props.get("default_track", False) else "no"
            forced_yn  = "yes" if props.get("forced_track", False)  else "no"

            mkvmerge_sub_args += [
                "--language",     f"0:{lang}",
                "--track-name",   f"0:{track_name}",
                "--default-track", f"0:{default_yn}",
                "--forced-track", f"0:{forced_yn}",
                tmp_sub,
            ]

            # VobSub também extrai um .idx: precisa passar o .idx ao mkvmerge
            if sub_ext == ".sub":
                idx_path = tmp_sub.replace(".sub", ".idx")
                if os.path.exists(idx_path):
                    # mkvmerge lê .sub + .idx em conjunto pelo caminho .sub; ok.
                    pass

        # ── Etapa 4: Remux final com mkvmerge ────────────────────────────
        print(f"\n{WHITE}  {dim('Remuxando com mkvmerge...')}{RESET}")

        # Inclui o arquivo original apenas como fonte de attachments (fontes TTF/OTF
        # usadas pelas legendas ASS, imagens de capa, etc.). As flags --no-* evitam
        # duplicar vídeo, áudio, legendas e capítulos que já vêm de tmp_nosub.
        mkvmerge_cmd = [
            MKVMERGE_PATH,
            "-o", output_file,
            tmp_nosub,
            *mkvmerge_sub_args,
            "--no-video", "--no-audio", "--no-subtitles", "--no-chapters", "--no-global-tags",
            input_file,
        ]

        merge_result = subprocess.run(
            mkvmerge_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="ignore"
        )

        if merge_result.returncode not in (0, 1):  # 1 = warnings, ainda ok
            print(f"\n{WHITE}  {colored('✘ Erro no mkvmerge (código ' + str(merge_result.returncode) + ')', RED)}")
            if merge_result.stderr:
                print(f"  {dim(merge_result.stderr.strip())}{RESET}")
            return False

        # ── Etapa 5: Validação ────────────────────────────────────────────
        print(f"\n{WHITE}  {dim('Inspecionando o corte final...')}{RESET}")
        check_info = analyze_file(output_file)

        if check_info:
            new_diff    = check_info["diff_ms"]
            phantoms    = check_info.get("phantom_subs", [])

            if abs(new_diff) <= 50 and not phantoms:
                print(f"{WHITE}  {colored('✔ Concluído e Validado', GREEN)}{RESET}")
                return True
            else:
                print(f"{WHITE}  {colored('⚠ Arquivo falhou na validação!', YELLOW)}")
                if phantoms:
                    print(f"  {colored('Motivo: Fantasma(s) sobrevivente(s): ' + ', '.join(phantoms), YELLOW)}{RESET}")
                else:
                    print(f"  {colored(f'Motivo: Diferença residual = {new_diff}ms.', YELLOW)}{RESET}")
                return False
        else:
            print(f"{WHITE}  {colored('✔ Concluído (validação indisponível)', GREEN)}{RESET}")
            return True

    finally:
        # Sempre limpa os temporários
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ─────────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────────

def ask_yn(prompt):
    while True:
        resp = input(f"\n{WHITE}  {bold(prompt)} {colored('[S/N]', CYAN)}: {RESET}").strip().upper()
        if resp in ("S", "N"):
            return resp == "S"
        print(f"{WHITE}  Digite S ou N.{RESET}")

def ask_choice(prompt, options):
    for i, opt in enumerate(options, 1):
        print(f"{WHITE}    [{i}] {opt}{RESET}")
    while True:
        resp = input(f"\n{WHITE}  {bold(prompt)}: {RESET}").strip()
        if resp.isdigit() and 1 <= int(resp) <= len(options):
            return int(resp) - 1
        print(f"{WHITE}  Digite um número entre 1 e {len(options)}.{RESET}")

def ask_multi(prompt, options):
    for i, opt in enumerate(options, 1):
        print(f"{WHITE}    [{i}] {opt}{RESET}")
    while True:
        resp = input(f"\n{WHITE}  {bold(prompt)}: {RESET}").strip()
        parts = [p.strip() for p in resp.replace(" ", ",").split(",") if p.strip()]
        try:
            indices = [int(p) - 1 for p in parts]
            if all(0 <= idx < len(options) for idx in indices) and indices:
                return indices
        except ValueError:
            pass
        print(f"{WHITE}  Digite números separados por vírgula (ex: 1,3,4).{RESET}")

# ─────────────────────────────────────────────
# Exibição da análise
# ─────────────────────────────────────────────

def print_analysis(files, analyses, cloud_files):
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('ANÁLISE PRÉ-CORTE', CYAN))}{RESET}")
    print(SEP2)

    for i, (f, info) in enumerate(zip(files, analyses), 1):
        name = os.path.basename(f)

        if f in cloud_files:
            print(f"{WHITE}  {dim('[' + str(i) + ']')} {name}")
            print(f"       {colored('☁ Somente online — pulado (não baixado)', YELLOW)}{RESET}")
            continue

        if info is None:
            print(f"{WHITE}  {dim('[' + str(i) + ']')} {name}")
            print(f"       {colored('✘ Falha na leitura', RED)}{RESET}")
            continue

        diff_ms      = info["diff_ms"]
        label, color = classify(diff_ms)
        badge        = colored(f"● {label}", color)
        n_audio      = len(info["audio_durs"])
        audio_str    = (f"{n_audio} faixa(s) de áudio"
                        if n_audio else colored("sem faixas de áudio", YELLOW))

        if diff_ms > 0:
            diff_str = colored(f"+{diff_ms} ms", color)
            dir_str  = "vídeo mais longo"
        elif diff_ms < 0:
            diff_str = colored(f"{diff_ms} ms", color)
            dir_str  = "container/áudio mais longo"
        else:
            diff_str = colored("0 ms", color)
            dir_str  = "durações idênticas"

        phantom_subs    = info.get("phantom_subs", [])
        phantom_warning = ""
        if phantom_subs and diff_ms < -50:
            subs_str = ", ".join(phantom_subs)
            phantom_warning = colored(f"\n       👻 Legenda(s) Suspeita(s): {subs_str}", YELLOW)

        print(f"{WHITE}  {dim('[' + str(i) + ']')} {bold(name)}")
        print(f"       {badge}  —  {diff_str}  {dim('(' + dir_str + ', ' + audio_str + ')')}{phantom_warning}{RESET}")

    print(f"\n{SEP2}\n")

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(f"{WHITE}Arraste um ou mais arquivos MKV para o .bat.{RESET}")
        return

    files = sys.argv[1:]
    total = len(files)

    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('FILA: ' + str(total) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)
    for i, f in enumerate(files, 1):
        print(f"{WHITE}  {dim('[' + str(i) + ']')} {os.path.basename(f)}{RESET}")

    # ── Verificação de arquivos na nuvem ──────
    cloud_files = set()
    for f in files:
        if os.path.exists(f) and not is_offline_available(f):
            cloud_files.add(f)

    if cloud_files:
        print(f"\n{WHITE}  {colored('⚠ Atenção:', YELLOW)} {len(cloud_files)} arquivo(s) estão somente online no Google Drive.")
        print(f"  {dim('Esses arquivos seriam baixados completamente para análise/corte.')}")
        print(f"  {dim('Eles serão ignorados. Baixe-os primeiro para processá-los.')}{RESET}")

    # ── Análise ───────────────────────────────
    print(f"\n{WHITE}  Analisando faixas...{RESET}")
    analyses = []
    for f in files:
        if f in cloud_files or not os.path.exists(f):
            analyses.append(None)
        else:
            analyses.append(analyze_file(f))

    print_analysis(files, analyses, cloud_files)

    # ── Cortar? ───────────────────────────────
    if not ask_yn("Cortar faixas?"):
        print(f"\n{WHITE}  {dim('Nenhum arquivo processado.')}{RESET}\n")
        return

    valid = [(f, info) for f, info in zip(files, analyses)
             if info is not None and f not in cloud_files]

    if not valid:
        print(f"\n{WHITE}  {colored('Nenhum arquivo válido para corte.', RED)}{RESET}\n")
        return

    # ── Por grupo ou individual ───────────────
    to_cut = []
    GROUP_COLORS = {"Perfeito": BLUE, "Bom": GREEN, "Ruim": YELLOW, "Horrível": RED}
    GROUP_ORDER  = ["Perfeito", "Bom", "Ruim", "Horrível"]

    if ask_yn("Cortar por grupo?"):
        groups = {}
        for f, info in valid:
            label, _ = classify(info["diff_ms"])
            groups.setdefault(label, []).append((f, info))

        avail   = [g for g in GROUP_ORDER if g in groups]
        print()
        options = [
            colored(g, GROUP_COLORS[g]) + f"  {dim('(' + str(len(groups[g])) + ' arquivo(s))')}"
            for g in avail
        ]
        idx          = ask_choice("Escolha o grupo", options)
        chosen_label = avail[idx]
        to_cut       = groups[chosen_label]

        print(f"\n{WHITE}  {len(to_cut)} arquivo(s) no grupo "
              f"{colored(chosen_label, GROUP_COLORS[chosen_label])} selecionado(s).{RESET}")

    else:
        if ask_yn("Selecionar individualmente?"):
            print()
            names = []
            for f, info in valid:
                label, color = classify(info["diff_ms"])
                diff_ms = info["diff_ms"]
                sign = "+" if diff_ms > 0 else ""
                tag = colored(f"[{label} / {sign}{diff_ms}ms]", color)
                names.append(f"{os.path.basename(f)}  {tag}")
            indices = ask_multi("Digite os números dos arquivos (ex: 1,3)", names)
            to_cut  = [valid[i] for i in indices]
        else:
            print(f"\n{WHITE}  {dim('Nenhum arquivo selecionado.')}{RESET}\n")
            return

    if not to_cut:
        print(f"\n{WHITE}  {dim('Nenhum arquivo selecionado.')}{RESET}\n")
        return

    # ── Processamento ─────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('PROCESSANDO ' + str(len(to_cut)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)

    success = 0
    failed  = 0
    for i, (f, info) in enumerate(to_cut, 1):
        ok = process_file(f, info, i, len(to_cut))
        if ok:
            success += 1
        else:
            failed += 1

    # ── Resumo ────────────────────────────────
    print(f"\n{SEP2}")
    s_str = colored(f"{success} OK", GREEN)
    f_str = colored(f"{failed} erro(s)", RED) if failed else dim("0 erro(s)")
    skipped = len(cloud_files) + len([f for f, info in zip(files, analyses)
                                      if info is None and f not in cloud_files])
    if skipped:
        skip_str = colored(f"{skipped} ignorado(s)", YELLOW)
        print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {f_str}  |  {skip_str}{RESET}")
    else:
        print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {f_str}{RESET}")
    print(f"{SEP2}\n")

if __name__ == "__main__":
    main()
