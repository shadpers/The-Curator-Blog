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

FFMPEG_PATH     = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH    = r"C:\FFmpeg\bin\ffprobe.exe"
MKVEXTRACT_PATH = r"C:\Program Files\MKVToolNix\mkvextract.exe"
MKVMERGE_PATH   = r"C:\Program Files\MKVToolNix\mkvmerge.exe"

# Cores ANSI
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


def colored(text, color):
    return f"{color}{text}{RESET}{WHITE}"

def bold(text):
    return f"{BOLD}{WHITE}{text}{RESET}{WHITE}"

def dim(text):
    return f"{DIM}{text}{RESET}{WHITE}"


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
# MKVMerge: leitura de faixas
# ─────────────────────────────────────────────

def get_mkv_tracks(input_file):
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
# Conversores ASS
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

def shift_ass_timestamps(ass_path: str, trim_ms: int) -> int:
    """
    Subtrai trim_ms de todos os timestamps ASS.
      - Eventos cujo End fica <= 0 são descartados.
      - Eventos cujo Start fica negativo são zerados (0:00:00.00).
    Retorna quantidade de linhas modificadas/removidas.
    """
    trim_cs = round(trim_ms / 10)  # centésimos de segundo (arredondado, não truncado)

    try:
        with open(ass_path, "r", encoding="utf-8-sig", errors="ignore") as fh:
            raw = fh.read()
    except OSError:
        return 0

    linesep = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines()

    in_events     = False
    format_fields = []
    new_lines     = []
    modified      = 0

    for line in lines:
        stripped = line.strip()

        if re.match(r"^\[Events\]$", stripped, re.IGNORECASE):
            in_events = True
            new_lines.append(line)
            continue
        elif stripped.startswith("[") and stripped.endswith("]") and in_events:
            in_events = False

        if in_events:
            m = re.match(r"^Format\s*:", stripped, re.IGNORECASE)
            if m:
                format_fields = [f.strip().lower()
                                 for f in stripped[stripped.index(":") + 1:].split(",")]
                new_lines.append(line)
                continue

            m = re.match(r"^(Dialogue|Comment)\s*:", stripped, re.IGNORECASE)
            if m and format_fields:
                prefix_end = line.index(":") + 1
                prefix     = line[:prefix_end]
                rest       = line[prefix_end:]

                n     = len(format_fields)
                parts = rest.split(",", n - 1)

                if len(parts) == n:
                    try:
                        si = format_fields.index("start")
                        ei = format_fields.index("end")

                        start_cs = _ass_time_to_cs(parts[si])
                        end_cs   = _ass_time_to_cs(parts[ei])

                        new_start = start_cs - trim_cs
                        new_end   = end_cs   - trim_cs

                        # Evento termina antes do novo início → descarta
                        if new_end <= 0:
                            modified += 1
                            continue

                        # Ajusta start e end
                        parts[si] = _cs_to_ass_time(max(0, new_start))
                        parts[ei] = _cs_to_ass_time(max(0, new_end))
                        line = prefix + ",".join(parts)
                        modified += 1

                    except (ValueError, IndexError):
                        pass  # Linha malformada: passa intacta

        new_lines.append(line)

    out = linesep.join(new_lines) + linesep
    with open(ass_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    return modified


# ─────────────────────────────────────────────
# Conversores SRT
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

def shift_srt_timestamps(srt_path: str, trim_ms: int) -> int:
    """
    Subtrai trim_ms de todos os timestamps SRT.
      - Blocos cujo End fica <= 0 são descartados.
      - Start negativo é zerado (00:00:00,000).
    """
    try:
        with open(srt_path, "r", encoding="utf-8-sig", errors="ignore") as fh:
            raw = fh.read()
    except OSError:
        return 0

    linesep = "\r\n" if "\r\n" in raw else "\n"
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
    )

    blocks     = re.split(r"\n\s*\n", raw.strip())
    new_blocks = []
    modified   = 0

    for block in blocks:
        m = pattern.search(block)
        if not m:
            new_blocks.append(block)
            continue

        start_ms_val = _srt_time_to_ms(m.group(1))
        end_ms_val   = _srt_time_to_ms(m.group(2))

        new_start = start_ms_val - trim_ms
        new_end   = end_ms_val   - trim_ms

        if new_end <= 0:
            modified += 1
            continue  # descarta bloco

        new_start_str = _ms_to_srt_time(max(0, new_start))
        new_end_str   = _ms_to_srt_time(max(0, new_end))

        block = (block[:m.start(1)] + new_start_str +
                 block[m.end(1):m.start(2)] + new_end_str +
                 block[m.end(2):])
        modified += 1
        new_blocks.append(block)

    out = (linesep + linesep).join(new_blocks) + linesep
    with open(srt_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    return modified


# ─────────────────────────────────────────────
# Mapa de codecs de legenda
# ─────────────────────────────────────────────

_CODEC_ID_MAP = {
    "S_TEXT/ASS":   (".ass", True),
    "S_TEXT/SSA":   (".ass", True),
    "S_TEXT/UTF8":  (".srt", True),
    "S_TEXT/ASCII": (".srt", True),
    "S_HDMV/PGS":   (".sup", False),
    "S_DVBT":       (".sub", False),
    "S_VOBSUB":     (".sub", False),
}

_CODEC_NAME_MAP = [
    ("substation", ".ass", True),
    ("ass",        ".ass", True),
    ("ssa",        ".ass", True),
    ("subrip",     ".srt", True),
    ("srt",        ".srt", True),
    ("utf",        ".srt", True),
    ("pgs",        ".sup", False),
    ("hdmv",       ".sup", False),
    ("vobsub",     ".sub", False),
    ("dvd",        ".sub", False),
]

def _codec_ext_fixable(codec_id_internal: str, codec_name: str):
    result = _CODEC_ID_MAP.get(codec_id_internal.upper())
    if result:
        return result
    name_lower = codec_name.lower()
    for keyword, ext, fixable in _CODEC_NAME_MAP:
        if keyword in name_lower:
            return (ext, fixable)
    return None


# ─────────────────────────────────────────────
# Keyframe detector
# ─────────────────────────────────────────────

def find_keyframe_ms(input_file: str, trim_ms: int) -> int:
    """
    Usa ffprobe para listar keyframes do stream de vídeo nos primeiros
    (trim_ms/1000 + 30) segundos e retorna o timestamp em ms do primeiro
    keyframe >= trim_ms.
    Fallback: devolve trim_ms original se não encontrar nada.
    """
    search_window = trim_ms / 1000.0 + 30  # 30 s de margem é mais que suficiente
    cmd = [
        FFPROBE_PATH,
        "-select_streams", "v:0",
        "-skip_frame", "nokey",
        "-show_frames",
        "-show_entries", "frame=pts_time",
        "-read_intervals", f"%+{search_window:.3f}",
        "-of", "csv",
        "-v", "quiet",
        input_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="ignore")

    keyframes = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(",")
        try:
            keyframes.append(round(float(parts[-1]) * 1000))
        except (ValueError, IndexError):
            pass

    keyframes.sort()
    for kf in keyframes:
        if kf >= trim_ms:
            return kf

    return trim_ms  # fallback (nenhum keyframe encontrado à frente)


# ─────────────────────────────────────────────
# Processamento de um arquivo
# ─────────────────────────────────────────────

def process_file(input_file, trim_ms: int, index: int, total: int, sub_state: dict):
    print(f"\n{SEP}")
    print(f"{WHITE}  {bold('[' + str(index) + '/' + str(total) + ']')} {os.path.basename(input_file)}{RESET}")
    print(SEP)

    trim_s      = trim_ms / 1000.0
    base, ext   = os.path.splitext(input_file)
    output_file = f"{base} (trimmed){ext}"
    tmp_dir     = tempfile.mkdtemp(dir=os.path.dirname(input_file) or ".")

    try:
        # ── Etapa 1: Listar faixas de legenda ───────────────────────────
        mkv_tracks = get_mkv_tracks(input_file)
        sub_tracks = [t for t in mkv_tracks if t.get("type") == "subtitles"]
        has_subs   = bool(sub_tracks)

        # ── Etapa 1b: Encontrar keyframe real ───────────────────────────
        print(f"{WHITE}  {dim('Localizando keyframe mais próximo...')}{RESET}")
        actual_trim_ms = find_keyframe_ms(input_file, trim_ms)
        actual_trim_s  = actual_trim_ms / 1000.0

        if actual_trim_ms != trim_ms:
            diff = actual_trim_ms - trim_ms
            print(f"{WHITE}  {colored('⚙ Ajuste de keyframe:', CYAN)} "
                  f"{trim_ms} ms → {colored(str(actual_trim_ms) + ' ms', GREEN)} "
                  f"{dim('(+' + str(diff) + ' ms para alinhar ao keyframe)')}{RESET}")
        else:
            print(f"{WHITE}  {colored('✔ Keyframe exato em ' + str(actual_trim_ms) + ' ms', GREEN)}{RESET}")

        # ── Etapa 2: FFmpeg — corta início do vídeo + áudio ─────────────
        tmp_nosub = os.path.join(tmp_dir, "_nosub.mkv")
        map_args  = ["-map", "0:V", "-map", "0:a"] if has_subs else ["-map", "0"]

        sub_label = (f" {dim('(legendas serão deslocadas separadamente)')}"
                     if has_subs else "")
        print(f"{WHITE}  {dim('Cortando vídeo/áudio — ' + str(actual_trim_ms) + ' ms removidos')}{sub_label}\n{RESET}")

        ffmpeg_cmd = [
            FFMPEG_PATH, "-y", "-v", "error", "-stats",
            "-ss", str(actual_trim_s),   # antes do -i = fast seek direto ao keyframe
            "-i", input_file,
            *map_args,
            "-map_metadata", "0",
            "-map_chapters", "0",
            "-fflags", "+bitexact",
            "-c", "copy",
            tmp_nosub
        ]

        result = subprocess.run(ffmpeg_cmd)
        if result.returncode != 0:
            print(f"\n{WHITE}  {colored('✘ Erro no FFmpeg (corte A/V)', RED)}{RESET}")
            return False

        # ── Etapa 3: Extrair + deslocar legendas ────────────────────────
        mkvmerge_sub_args = []
        keep_original_subs = False  # True = muxar as legendas originais sem alterar

        if has_subs and not ask_subtitle_proceed(sub_state):
            keep_original_subs = True  # inclui no remux sem tocar nos timestamps
            print(f"{WHITE}  {dim('Legendas mantidas sem alteração.')}{RESET}")
            sub_tracks = []

        for track in sub_tracks:
            tid        = track["id"]
            props      = track.get("properties", {})
            codec_id   = props.get("codec_id", "")
            codec_name = track.get("codec", "")

            ext_info = _codec_ext_fixable(codec_id, codec_name)
            if ext_info is None:
                print(f"  {dim(f'  ⚠ Codec desconhecido ({codec_id or repr(codec_name)}) na faixa {tid} — ignorada.')}{RESET}")
                continue

            sub_ext, can_fix = ext_info
            tmp_sub = os.path.join(tmp_dir, f"sub_{tid}{sub_ext}")

            subprocess.run(
                [MKVEXTRACT_PATH, "tracks", input_file, f"{tid}:{tmp_sub}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="ignore"
            )

            if not os.path.exists(tmp_sub) or os.path.getsize(tmp_sub) == 0:
                print(f"  {dim(f'  ⚠ Falha ao extrair faixa {tid} — ignorada.')}{RESET}")
                continue

            # Desloca os timestamps subtraindo o corte REAL (não o pedido)
            if can_fix:
                if sub_ext == ".ass":
                    n = shift_ass_timestamps(tmp_sub, actual_trim_ms)
                elif sub_ext == ".srt":
                    n = shift_srt_timestamps(tmp_sub, actual_trim_ms)
                else:
                    n = 0

                fix_note = (f" {colored(f'({n} evento(s) ajustado(s)/removido(s))', GREEN)}"
                            if n > 0 else f" {dim('(sem eventos afetados)')}")
            else:
                # Legendas de imagem (PGS, VobSub) não podem ser deslocadas por texto
                fix_note = f" {colored('⚠ Legenda de imagem — timestamps NÃO deslocados', YELLOW)}"

            track_name  = props.get("track_name", "")
            lang        = props.get("language", "und")
            codec_label = codec_id if codec_id else codec_name
            print(f"  {dim(f'  Faixa {tid} [{codec_label}] {track_name}')}{fix_note}{RESET}")

            default_yn = "yes" if props.get("default_track", False) else "no"
            forced_yn  = "yes" if props.get("forced_track",  False) else "no"

            mkvmerge_sub_args += [
                "--language",      f"0:{lang}",
                "--track-name",    f"0:{track_name}",
                "--default-track", f"0:{default_yn}",
                "--forced-track",  f"0:{forced_yn}",
                tmp_sub,
            ]

        # ── Etapa 4: Remux final ─────────────────────────────────────────
        print(f"\n{WHITE}  {dim('Remuxando com mkvmerge...')}{RESET}")

        # Se o usuário optou por manter as legendas originais sem alterar,
        # removemos --no-subtitles para que o mkvmerge as copie do input original.
        source_exclude = ["--no-video", "--no-audio", "--no-chapters", "--no-global-tags"]
        if not keep_original_subs:
            source_exclude.append("--no-subtitles")

        mkvmerge_cmd = [
            MKVMERGE_PATH,
            "-o", output_file,
            tmp_nosub,
            *mkvmerge_sub_args,
            *source_exclude,
            input_file,
        ]

        merge_result = subprocess.run(
            mkvmerge_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="ignore"
        )

        if merge_result.returncode not in (0, 1):
            print(f"\n{WHITE}  {colored('✘ Erro no mkvmerge (código ' + str(merge_result.returncode) + ')', RED)}")
            if merge_result.stderr:
                print(f"  {dim(merge_result.stderr.strip())}{RESET}")
            return False

        print(f"{WHITE}  {colored('✔ Concluído → ' + os.path.basename(output_file), GREEN)}{RESET}")
        return True

    finally:
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

def ask_subtitle_proceed(sub_state: dict) -> bool:
    """
    Pergunta se deve aplicar o deslocamento nas legendas.
    sub_state = {"decision": None | "all_yes" | "all_no"}
    """
    if sub_state["decision"] == "all_yes":
        return True
    if sub_state["decision"] == "all_no":
        return False

    while True:
        resp = input(
            f"\n{WHITE}  {bold('Aplicar deslocamento nas legendas?')} "
            f"{colored('[S / N / ALL (sim p/ todos) / NALL (não p/ todos)]', CYAN)}{WHITE}: {RESET}"
        ).strip().upper()
        if resp == "S":
            return True
        if resp == "N":
            return False
        if resp == "ALL":
            sub_state["decision"] = "all_yes"
            return True
        if resp == "NALL":
            sub_state["decision"] = "all_no"
            return False
        print(f"{WHITE}  S = Sim  |  N = Não  |  ALL = Sim para todos  |  NALL = Não para todos{RESET}")

def ask_trim_ms() -> int:
    """Pergunta quantos MS cortar do início. Aceita apenas inteiro positivo."""
    while True:
        resp = input(
            f"\n{WHITE}  {bold('Quantos milissegundos cortar do INÍCIO de cada arquivo?')} "
            f"{colored('[ex: 500]', CYAN)}: {RESET}"
        ).strip()
        if resp.isdigit() and int(resp) > 0:
            return int(resp)
        print(f"{WHITE}  Digite um número inteiro positivo (ex: 500).{RESET}")


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
    print(f"{WHITE}  {bold(colored('CORTE DO INÍCIO — ' + str(total) + ' arquivo(s)', CYAN))}{RESET}")
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
        print(f"  {dim('Eles serão ignorados. Baixe-os primeiro para processá-los.')}{RESET}")

    valid_files = [f for f in files
                   if f not in cloud_files and os.path.exists(f) and f.lower().endswith(".mkv")]

    if not valid_files:
        print(f"\n{WHITE}  {colored('Nenhum arquivo MKV válido encontrado.', RED)}{RESET}\n")
        return

    # ── Pergunta quantos MS cortar ────────────
    trim_ms = ask_trim_ms()

    s   = trim_ms / 1000.0
    hms = f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f}"
    print(f"\n{WHITE}  Offset a remover: {colored(str(trim_ms) + ' ms', CYAN)} {dim('(' + hms + ')')}")
    print(f"  Arquivos a processar: {colored(str(len(valid_files)), CYAN)}{RESET}")

    if not ask_yn("Confirmar e iniciar o processamento?"):
        print(f"\n{WHITE}  {dim('Operação cancelada.')}{RESET}\n")
        return

    # ── Processamento ─────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('PROCESSANDO ' + str(len(valid_files)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)

    success = 0
    failed  = 0
    sub_state = {"decision": None}

    for i, f in enumerate(valid_files, 1):
        ok = process_file(f, trim_ms, i, len(valid_files), sub_state)
        if ok:
            success += 1
        else:
            failed += 1

    # ── Resumo ────────────────────────────────
    print(f"\n{SEP2}")
    s_str    = colored(f"{success} OK", GREEN)
    f_str    = colored(f"{failed} erro(s)", RED) if failed else dim("0 erro(s)")
    skipped  = len(files) - len(valid_files)
    if skipped:
        skip_str = colored(f"{skipped} ignorado(s)", YELLOW)
        print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {f_str}  |  {skip_str}{RESET}")
    else:
        print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {f_str}{RESET}")
    print(f"{SEP2}\n")


if __name__ == "__main__":
    main()
