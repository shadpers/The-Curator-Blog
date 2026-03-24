import subprocess
import sys
import os
import json
import ctypes

# Habilita ANSI no terminal Windows
try:
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

FFMPEG_PATH  = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"

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
    """
    Usa valor absoluto para classificar — direção fica no sinal (+/-).
    Perfeito  : |diff| <= 50 ms   (tolerância de sync)
    Bom       : |diff| <= 1000 ms
    Ruim      : |diff| <= 2000 ms
    Horrível  : |diff|  > 2000 ms
    """
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

def get_streams(input_file):
    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        input_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return json.loads(result.stdout).get("streams", [])
    except Exception:
        return []

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
    diff_ms = (video_dur - max_audio_dur) * 1000
    Positivo → vídeo mais longo | Negativo → áudio mais longo
    Comparar contra o áudio MAIS LONGO evita falsos positivos de dubs curtos.
    """
    streams = get_streams(input_file)
    if not streams:
        return None

    video_dur  = None
    audio_durs = []

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

    if audio_durs:
        max_audio = max(audio_durs)
        diff_ms   = round((video_dur - max_audio) * 1000)
    else:
        diff_ms = 0

    return {
        "video_dur":  video_dur,
        "audio_durs": audio_durs,
        "diff_ms":    diff_ms,
    }

# ─────────────────────────────────────────────
# Processamento (corte)
# ─────────────────────────────────────────────

def process_file(input_file, info, index, total):
    print(f"\n{SEP}")
    print(f"{WHITE}  {bold('[' + str(index) + '/' + str(total) + ']')} {os.path.basename(input_file)}{RESET}")
    print(SEP)

    duration = str(info["video_dur"])
    base, ext = os.path.splitext(input_file)
    output_file = f"{base} (cuted){ext}"

    ffmpeg_cmd = [
        FFMPEG_PATH,
        "-y",
        "-v", "error",
        "-stats",
        "-i", input_file,
        "-map", "0",
        "-map_metadata", "0",
        "-map_chapters", "0",
        "-to", duration,
        "-c", "copy",
        output_file
    ]

    print(f"{WHITE}  {dim('Saída: ' + os.path.basename(output_file))}\n{RESET}")
    result = subprocess.run(ffmpeg_cmd)

    if result.returncode == 0:
        print(f"\n{WHITE}  {colored('✔ Concluído', GREEN)}{RESET}")
        return True
    else:
        print(f"\n{WHITE}  {colored('✘ Erro (código ' + str(result.returncode) + ')', RED)}{RESET}")
        return False

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
        audio_str    = (
            f"{n_audio} faixa(s) de áudio"
            if n_audio else colored("sem faixas de áudio", YELLOW)
        )

        if diff_ms > 0:
            diff_str = colored(f"+{diff_ms} ms", color)
            dir_str  = "vídeo mais longo"
        elif diff_ms < 0:
            diff_str = colored(f"{diff_ms} ms", color)
            dir_str  = "áudio mais longo"
        else:
            diff_str = colored("0 ms", color)
            dir_str  = "durações idênticas"

        print(f"{WHITE}  {dim('[' + str(i) + ']')} {bold(name)}")
        print(f"       {badge}  —  {diff_str}  {dim('(' + dir_str + ', ' + audio_str + ')')}{RESET}")

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

    valid   = [(f, info) for f, info in zip(files, analyses)
               if info is not None and f not in cloud_files]
    invalid = [f for f, info in zip(files, analyses) if info is None]

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

        avail = [g for g in GROUP_ORDER if g in groups]
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
    f_str = colored(f"{failed} erro(s)", RED) if failed else dim(f"0 erro(s)")
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
