import subprocess
import sys
import os
import re
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

# --- CONFIGURAÇÕES ---
FFMPEG  = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"
QUALITY = 2  # 1-31, menor = melhor

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

DURATION_OPTIONS = {
    "1": (30,  "30 segundos"),
    "2": (60,  "60 segundos"),
    "3": (180, "3 minutos"),
    "4": (300, "5 minutos"),
}

def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════╗
║      ANCHOR FRAME SYNC  —  v2.6.1        ║
║   Diferença de quadros em milissegundos  ║
║   (suporte a arquivos locais + URLs CDN) ║
╚══════════════════════════════════════════╝{RESET}
""")

def err(msg):
    print(f"{RED}[ERRO]{RESET} {msg}")
    sys.exit(1)

def info(msg):
    print(f"{CYAN}[INFO]{RESET} {msg}")

def ok(msg):
    print(f"{GREEN}[ OK ]{RESET} {msg}")

def clean_filename(name):
    """Remove caracteres especiais que podem bugar o ffmpeg (ex: colchetes, %)"""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:40].strip('_')

def is_url(path):
    """Detecta se o argumento é uma URL HTTP/HTTPS."""
    s = str(path).strip().lower()
    return s.startswith("http://") or s.startswith("https://")

def resolve_lnk(path):
    """Resolve atalhos .lnk do Windows para o caminho real do arquivo."""
    path = Path(path)
    if path.suffix.lower() != ".lnk":
        return path
    cmd = [
        "powershell", "-NoProfile", "-Command",
        f'(New-Object -COM WScript.Shell).CreateShortcut("{path}").TargetPath'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    target = result.stdout.strip()
    if not target:
        err(f"Não foi possível ler o atalho: {path}")
    target = Path(target)
    if not target.exists():
        err(f"Destino do atalho não encontrado: {target}")
    info(f"Atalho resolvido: {path.name}  →  {target.name}")
    return target

def resolve_input(arg):
    """Aceita caminho local (ou .lnk) ou URL de CDN."""
    arg = arg.strip().strip('"').strip("'")
    if is_url(arg):
        # Mostra só o começo da URL para não poluir o console
        display = arg if len(arg) <= 90 else arg[:87] + "..."
        info(f"URL detectada: {display}")
        return arg
    return resolve_lnk(arg)

def get_display_name(filepath):
    """Nome amigável para exibição e pastas de saída."""
    if is_url(filepath):
        path = urlparse(str(filepath)).path
        name = Path(path).stem or Path(path).name or "remote_video"
        # Remove extensões comuns se ainda restarem
        for ext in (".mp4", ".mkv", ".ts", ".m2ts", ".webm", ".mov"):
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
        return clean_filename(name) or "remote_video"
    return clean_filename(Path(filepath).stem)

def ask_duration():
    print(f"{BOLD}Duração da análise (quadros a extrair):{RESET}")
    for key, (secs, label) in DURATION_OPTIONS.items():
        fps_approx = 23.976
        frames_approx = int(secs * fps_approx)
        print(f"  {YELLOW}{key}{RESET}) {label:15s}  (~{frames_approx} quadros a 23.976 fps)")
    print()
    while True:
        raw = input(f"{YELLOW}Escolha [1-4]:{RESET} ").strip()
        if raw in DURATION_OPTIONS:
            secs, label = DURATION_OPTIONS[raw]
            print(f"  {GREEN}→ {label} selecionado.{RESET}\n")
            return secs
        print(f"  {RED}Digite 1, 2, 3 ou 4.{RESET}")

def check_deps():
    for tool in [FFMPEG, FFPROBE]:
        try:
            subprocess.run([tool, "-version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            err(f"'{tool}' não encontrado. Verifique o caminho no topo do script.")

def get_video_info(filepath):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",           # ajuda a pegar duration em alguns CDNs
        str(filepath)
    ]
    # Opções de reconexão para URLs
    if is_url(filepath):
        cmd = [
            FFPROBE, "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            str(filepath)
        ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err(f"Não foi possível ler: {filepath}\n{result.stderr.decode('utf-8', errors='ignore')[-400:] if result.stderr else ''}")
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            # Se duration não veio no stream, tenta no format
            if not s.get("duration") and data.get("format", {}).get("duration"):
                s["duration"] = data["format"]["duration"]
            return s
    err(f"Nenhuma stream de vídeo encontrada em: {filepath}")

def parse_framerate(rate_str):
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            return float(num) / float(den)
        return float(rate_str)
    except:
        return 0.0

def print_file_info(label, filepath, stream):
    codec  = stream.get("codec_name", "?").upper()
    width  = stream.get("width", "?")
    height = stream.get("height", "?")
    fps    = parse_framerate(stream.get("r_frame_rate", "0/1"))
    dur    = float(stream.get("duration", 0) or 0)
    h, rem = divmod(int(dur), 3600)
    m, s   = divmod(rem, 60)
    name   = get_display_name(filepath)
    if is_url(filepath):
        name = f"[URL] {name}"
    print(f"  {BOLD}{label}{RESET}: {name}")
    print(f"         {codec}  {width}x{height}  {fps:.3f} fps  "
          f"{h:02d}:{m:02d}:{s:02d} duração")

def timestamps_and_corrupt(stderr):
    """PTS por quadro de saída, e índices cujo decode falhou logo antes do showinfo."""
    timestamps = {}
    corrupt = set()
    frame_num = 1
    seen_ns = set()
    pending_error = False
    markers = (
        "error while decoding", "concealing", "could not find ref",
        "invalid data", "decode_slice_header", "error constructing",
        "corrupt decoded frame", "invalid nal", "pps id out of range",
        "cu_qp_delta", "missing reference", "conversion failed",
    )
    for line in (stderr or "").split("\n"):
        low = line.lower()
        if "showinfo" not in low and any(m in low for m in markers):
            if not re.fullmatch(r"[0-9a-fA-F]+", line.strip()):
                pending_error = True
            continue
        if "showinfo" not in low:
            continue
        m_n = re.search(r"\bn:\s*(\d+)\b", line)
        m_pts = re.search(r"pts_time:\s*([0-9.]+)", line)
        if not (m_n and m_pts):
            continue
        n = int(m_n.group(1))
        if n in seen_ns:
            continue
        seen_ns.add(n)
        timestamps[frame_num] = round(float(m_pts.group(1)) * 1000, 4)
        if pending_error:
            corrupt.add(frame_num)
            pending_error = False
        frame_num += 1
    return timestamps, corrupt


def relevant_ffmpeg_errors(stderr):
    """Filtra o stderr do ffmpeg: ignora dump hex de SEI/x265 e showinfo."""
    keys = ("error", "invalid", "failed", "corrupt", "concealing", "missing", "decode")
    lines = []
    for line in (stderr or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"[0-9a-fA-F]+", stripped):
            continue
        low = stripped.lower()
        if "showinfo" in low or "parsed_showinfo" in low:
            continue
        if any(k in low for k in keys):
            lines.append(stripped)
    return lines[-12:]


def write_red_frame(dest, width, height):
    """Quadro 100% vermelho. Slot existe, mas não serve de âncora."""
    dest = Path(dest)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=red:s={int(width)}x{int(height)}:r=1",
        "-frames:v", "1", "-q:v", "3", str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err(f"Não foi possível gerar o quadro vermelho: {result.stderr[-300:]}")


def build_extract_cmd(filepath, pattern, duration):
    # showinfo antes do setpts: o log guarda o PTS real.
    # setpts gera DTS crescente para o image2. Sem isso o muxer aborta em
    # "non monotonically increasing dts" (342 >= 342) e a retomada duplica quadro.
    # Sem -copyts e sem discardcorrupt.
    cmd = [
        FFMPEG, "-y", "-hide_banner",
        "-err_detect", "ignore_err",
        "-ec", "guess_mvs+deblock",
        "-fflags", "+genpts+igndts",
    ]
    if is_url(filepath):
        cmd += [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-timeout", "10000000",
        ]
    cmd += [
        "-i", str(filepath),
        "-t", f"{duration:.6f}",
        "-map", "0:v:0",
        "-map_metadata", "-1",
        "-vf", "format=yuv420p,showinfo,setpts=N/(FRAME_RATE*TB)",
        "-fps_mode", "passthrough",
        "-an", "-sn",
        "-q:v", str(QUALITY),
        pattern,
    ]
    return cmd


def extract_frames_with_timestamps(filepath, output_dir, label, duration):
    output_dir = Path(output_dir)
    ts_file = output_dir / "timestamps.json"
    bad_file = output_dir / "corrupt_frames.json"

    if ts_file.exists() and any(output_dir.glob("frame_*.jpg")):
        print(f"{YELLOW}[!] Pasta de {label} já contém arquivos.{RESET}")
        choice = input(f"    Deseja pular a extração e usar os quadros existentes? (S/n): ").strip().lower()
        if choice != "n":
            try:
                with open(ts_file, "r") as f:
                    timestamps = {int(k): v for k, v in json.load(f).items()}
                corrupt = set()
                if bad_file.exists():
                    with open(bad_file, "r") as f:
                        corrupt = set(json.load(f))
                ok(f"{label}: Usando cache ({len(timestamps)} quadros, {len(corrupt)} vermelhos).")
                return timestamps, corrupt
            except Exception:
                info("Falha ao ler cache, re-extraindo...")

    stream = get_video_info(filepath)
    width = int(stream.get("width") or 1440)
    height = int(stream.get("height") or 1080)
    fps = parse_framerate(stream.get("r_frame_rate", "24000/1001")) or 23.976
    frame_ms = 1000.0 / fps

    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame_*.jpg"):
        old.unlink()
    part_dir = output_dir / "_part"
    if part_dir.exists():
        shutil.rmtree(part_dir, ignore_errors=True)
    part_dir.mkdir()

    info(f"Extraindo quadros de {label} ({duration}s)...")
    if is_url(filepath):
        info("  (fonte remota — só os primeiros segundos pedidos serão decodificados)")
    info("  Vermelho só entra no lugar de um quadro que o decoder não entregou.")

    pattern = str(part_dir / "frame_%05d.jpg")
    result = subprocess.run(
        build_extract_cmd(filepath, pattern, duration),
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    parsed, decode_bad = timestamps_and_corrupt(result.stderr)
    files = sorted(part_dir.glob("frame_*.jpg"))
    if not parsed or not files:
        errors = relevant_ffmpeg_errors(result.stderr)
        detail = "\n".join(errors) if errors else (result.stderr or "")[-500:]
        err(f"ffmpeg falhou em {label}:\n{detail}")

    if result.returncode != 0:
        errors = relevant_ffmpeg_errors(result.stderr)
        print(f"{YELLOW}[!] ffmpeg avisou em {label}, mas os quadros gravados foram mantidos.{RESET}")
        for line in errors[:4]:
            print(f"    {line[:180]}")

    # parsed é 1..N na ordem de saída. n do showinfo só serve para achar buraco.
    # Um aviso de DTS (342 >= 342) não é índice de quadro e não pinta nada.
    show_ns = []
    seen = set()
    for line in (result.stderr or "").splitlines():
        if "showinfo" not in line.lower():
            continue
        m_n = re.search(r"\bn:\s*(\d+)\b", line)
        if not m_n:
            continue
        n = int(m_n.group(1))
        if n in seen:
            continue
        seen.add(n)
        show_ns.append(n)

    indexed = list(parsed.items())
    # showinfo às vezes loga um quadro a mais no fim e o image2 não grava o JPEG.
    # Isso não é quadro faltante: descartar, não inventar vermelho.
    if len(indexed) == len(files) + 1:
        indexed = indexed[:len(files)]
        show_ns = show_ns[:len(files)]
    entries = []
    for i, (idx, pts) in enumerate(indexed):
        if i > 0 and i < len(show_ns) and show_ns[i] > show_ns[i - 1] + 1:
            missing = show_ns[i] - show_ns[i - 1] - 1
            prev_pts = entries[-1][0]
            for k in range(missing):
                entries.append((round(prev_pts + frame_ms * (k + 1), 4), True, None))
        src = files[i] if i < len(files) else None
        missing_file = src is None or not Path(src).exists()
        entries.append((pts, missing_file, None if missing_file else src))

    if len(files) > len(indexed):
        info(f"{label}: {len(files) - len(indexed)} jpeg sem PTS ignorados (não entram na sequência).")

    red_template = output_dir / "_red.jpg"
    need_red = any(is_bad or src is None for _, is_bad, src in entries)
    if need_red:
        write_red_frame(red_template, width, height)

    timestamps = {}
    corrupt = set()
    for i, (pts, is_bad, src) in enumerate(entries, start=1):
        dest = output_dir / f"frame_{i:05d}.jpg"
        if is_bad or src is None:
            shutil.copyfile(red_template, dest)
            corrupt.add(i)
        else:
            shutil.move(str(src), dest)
        timestamps[i] = round(pts, 4)

    shutil.rmtree(part_dir, ignore_errors=True)
    if red_template.exists():
        red_template.unlink()

    with open(ts_file, "w") as f:
        json.dump(timestamps, f)
    with open(bad_file, "w") as f:
        json.dump(sorted(corrupt), f)

    expected = int(round(duration * fps))
    if abs(len(timestamps) - expected) > 3:
        print(f"{YELLOW}[!] {label}: {len(timestamps)} quadros, esperado ~{expected}.{RESET}")
    if corrupt:
        preview = ", ".join(str(n) for n in sorted(corrupt)[:12])
        suffix = "..." if len(corrupt) > 12 else ""
        print(f"{YELLOW}[!] {label}: {len(corrupt)} quadro(s) vermelho(s): {preview}{suffix}{RESET}")
        print(f"{YELLOW}    Só estes faltaram no decode. Nenhum quadro saudável foi trocado.{RESET}")
    else:
        ok(f"{label}: nenhum quadro faltante.")
    ok(f"{label}: {len(timestamps)} quadros extraídos.")
    return timestamps, corrupt


def open_folder(path):
    path = Path(path).resolve()
    if sys.platform == "win32": os.startfile(str(path))
    else: subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", str(path)])

def ask_frame(label, timestamps, corrupt=None):
    corrupt = corrupt or set()
    max_f = max(timestamps.keys()) if timestamps else 0
    while True:
        raw = input(f"\n{YELLOW}Qual quadro de {BOLD}{label}{RESET}{YELLOW} corresponde? [1 – {max_f}]:{RESET} ").strip()
        if raw.isdigit() and int(raw) in timestamps:
            n = int(raw)
            if n in corrupt:
                print(f"  {RED}Quadro {n} está vermelho (decode falhou). Escolha outro.{RESET}")
                continue
            return n, timestamps[n]
        print(f"  {RED}Quadro inválido.{RESET}")

def fmt_time(ms):
    total_s = ms / 1000
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:09.6f}"

def ask_input(label):
    """Pede interativamente um caminho local ou URL de CDN."""
    print(f"\n{BOLD}Fonte {label}:{RESET}")
    print(f"  Pode ser caminho de arquivo local ou link HTTP/HTTPS de CDN.")
    while True:
        raw = input(f"  {YELLOW}Digite ou cole e pressione ENTER:{RESET} ").strip().strip('"').strip("'")
        if not raw:
            print(f"  {RED}Valor vazio. Tente novamente.{RESET}")
            continue
        return resolve_input(raw)

def main():
    banner()

    # --- Entrada flexível ---
    # 0 args  → pede os dois interativamente
    # 1 arg   → usa como A e pede o B
    # 2 args  → usa os dois (arrastar no .bat ou linha de comando)
    args = sys.argv[1:]

    if len(args) == 0:
        print(f"{CYAN}Nenhum arquivo informado. Modo interativo.{RESET}")
        file_a = ask_input("A")
        file_b = ask_input("B")
    elif len(args) == 1:
        print(f"{CYAN}Apenas uma fonte informada. Usando como A e pedindo a B.{RESET}")
        file_a = resolve_input(args[0])
        file_b = ask_input("B")
    elif len(args) == 2:
        file_a = resolve_input(args[0])
        file_b = resolve_input(args[1])
    else:
        print(f"{RED}Muitos argumentos. Use no máximo dois (arquivo ou URL).{RESET}")
        print(f"""
{BOLD}Exemplos de uso:{RESET}
  • Arraste 1 ou 2 arquivos sobre o .bat
  • Clique duplo no .bat (pede os dois)
  • Linha de comando:
      python anchor_frame_sync.py "A.mkv" "https://cdn.../B.mp4"
      python anchor_frame_sync.py "https://cdn.../A.mp4"
""")
        sys.exit(1)

    check_deps()

    print(f"{BOLD}Arquivos / fontes:{RESET}")
    print_file_info("A", file_a, get_video_info(file_a))
    print_file_info("B", file_b, get_video_info(file_b))
    print()

    duration = ask_duration()

    base_dir = Path(sys.argv[0]).parent / "sync_output"
    dir_a = base_dir / f"A_{get_display_name(file_a)}"
    dir_b = base_dir / f"B_{get_display_name(file_b)}"

    ts_a, bad_a = extract_frames_with_timestamps(file_a, dir_a, "A", duration)
    ts_b, bad_b = extract_frames_with_timestamps(file_b, dir_b, "B", duration)

    print(f"\n{BOLD}Abrindo pastas com os quadros...{RESET}")
    open_folder(dir_a)
    open_folder(dir_b)

    print(f"""
{BOLD}── INSTRUÇÃO ──────────────────────────────────────────────────────{RESET}
  Navegue pelas pastas, encontre um quadro idêntico nos dois vídeos
  e anote o número (ex: frame_00123.jpg -> número 123).
  Quadro vermelho = decode falhou. Ele ocupa o índice, mas não serve de âncora.
{BOLD}───────────────────────────────────────────────────────────────────{RESET}""")

    frame_n_a, pts_a = ask_frame("A", ts_a, bad_a)
    frame_n_b, pts_b = ask_frame("B", ts_b, bad_b)

    diff_ms = pts_a - pts_b

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════╗
║               RESULTADO FINAL                ║
╚══════════════════════════════════════════════╝{RESET}

  Quadro A #{frame_n_a:>5}  →  {fmt_time(pts_a)}
  Quadro B #{frame_n_b:>5}  →  {fmt_time(pts_b)}

  {BOLD}Diferença:{RESET}  {YELLOW}{diff_ms:+.4f} ms{RESET}
             ({abs(diff_ms):.4f} ms  |  {abs(diff_ms)/1000:.6f} s)

  {CYAN}Interpretação:{RESET}""")

    if abs(diff_ms) < 0.1:
        print(f"  {GREEN}Os arquivos estão perfeitamente sincronizados.{RESET}")
    elif diff_ms > 0:
        print(f"  {YELLOW}B está {abs(diff_ms):.4f} ms ADIANTADO em relação a A.{RESET}")
        print(f"  → No MKVToolNix: aplique DELAY de {abs(diff_ms):.0f} ms em B.")
    else:
        print(f"  {YELLOW}A está {abs(diff_ms):.4f} ms ADIANTADO em relação a B.{RESET}")
        print(f"  → No MKVToolNix: aplique DELAY de {abs(diff_ms):.0f} ms em A.")

    print(f"\n  {BOLD}Para MKVToolNix:{RESET}  --sync 0:{diff_ms:.0f}")
    print(f"  {BOLD}Para ffmpeg:{RESET}      -itsoffset {diff_ms/1000:.6f}")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrompido.{RESET}")
    input("Pressione ENTER para fechar...")
