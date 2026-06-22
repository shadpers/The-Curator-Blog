import subprocess
import sys
import os
import re
import json
from pathlib import Path

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
║      ANCHOR FRAME SYNC  —  v2.2          ║
║   Diferença de quadros em milissegundos  ║
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
        str(filepath)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err(f"Não foi possível ler: {filepath}")
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
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
    print(f"  {BOLD}{label}{RESET}: {Path(filepath).name}")
    print(f"         {codec}  {width}x{height}  {fps:.3f} fps  "
          f"{h:02d}:{m:02d}:{s:02d} duração")

def extract_frames_with_timestamps(filepath, output_dir, label, duration):
    output_dir = Path(output_dir)
    ts_file = output_dir / "timestamps.json"

    # --- LÓGICA DE VERIFICAÇÃO DE CACHE ---
    if ts_file.exists() and any(output_dir.glob("frame_*.jpg")):
        print(f"{YELLOW}[!] Pasta de {label} já contém arquivos.{RESET}")
        choice = input(f"    Deseja pular a extração e usar os quadros existentes? (S/n): ").strip().lower()
        if choice != 'n':
            try:
                with open(ts_file, "r") as f:
                    data = json.load(f)
                    timestamps = {int(k): v for k, v in data.items()}
                ok(f"{label}: Usando cache ({len(timestamps)} quadros).")
                return timestamps
            except:
                info("Falha ao ler cache, re-extraindo...")

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "frame_%05d.jpg")
    info(f"Extraindo quadros de {label} ({duration}s)...")

    cmd = [
        FFMPEG, "-y",
        "-i", str(filepath),
        "-t", str(duration),
        "-map", "0:v:0",                   # [NOVO] Pega APENAS o vídeo principal (ignora capas/pôsteres)
        "-map_metadata", "-1",             # Remove metadados que bugam encoders de imagem
        "-vf", "format=yuv420p,showinfo",  # Força 8-bit antes do showinfo
        "-fps_mode", "passthrough",        # Modo moderno de vsync
        "-an", "-sn",                      # Ignora áudio e legendas (mais rápido)
        "-q:v", str(QUALITY),
        pattern
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    if result.returncode != 0:
        err(f"ffmpeg falhou em {label}:\n{result.stderr[-800:]}")

    timestamps = {}
    frame_num  = 1
    seen_ns    = set()

    for line in result.stderr.split("\n"):
        if "showinfo" not in line.lower(): continue
        m_n   = re.search(r"\bn:\s*(\d+)\b", line)
        m_pts = re.search(r"pts_time:\s*([0-9.]+)", line)
        if m_n and m_pts:
            n = int(m_n.group(1))
            if n in seen_ns: continue
            seen_ns.add(n)
            pts_ms = round(float(m_pts.group(1)) * 1000, 4)
            timestamps[frame_num] = pts_ms
            frame_num += 1

    with open(ts_file, "w") as f:
        json.dump(timestamps, f)

    ok(f"{label}: {len(timestamps)} quadros extraídos.")
    return timestamps

def open_folder(path):
    path = Path(path).resolve()
    if sys.platform == "win32": os.startfile(str(path))
    else: subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", str(path)])

def ask_frame(label, timestamps):
    max_f = max(timestamps.keys()) if timestamps else 0
    while True:
        raw = input(f"\n{YELLOW}Qual quadro de {BOLD}{label}{RESET}{YELLOW} corresponde? [1 – {max_f}]:{RESET} ").strip()
        if raw.isdigit() and int(raw) in timestamps:
            return int(raw), timestamps[int(raw)]
        print(f"  {RED}Quadro inválido.{RESET}")

def fmt_time(ms):
    total_s = ms / 1000
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:09.6f}"

def main():
    banner()

    if len(sys.argv) != 3:
        print(f"Uso: Arraste dois arquivos sobre o .bat")
        sys.exit(1)

    file_a = resolve_lnk(sys.argv[1])
    file_b = resolve_lnk(sys.argv[2])

    check_deps()

    print(f"{BOLD}Arquivos:{RESET}")
    print_file_info("A", file_a, get_video_info(file_a))
    print_file_info("B", file_b, get_video_info(file_b))
    print()

    duration = ask_duration()

    base_dir = Path(sys.argv[0]).parent / "sync_output"
    # [NOVO] Limpa caracteres especiais do nome para evitar falhas de gravação
    dir_a = base_dir / f"A_{clean_filename(file_a.stem)}"
    dir_b = base_dir / f"B_{clean_filename(file_b.stem)}"

    ts_a = extract_frames_with_timestamps(file_a, dir_a, "A", duration)
    ts_b = extract_frames_with_timestamps(file_b, dir_b, "B", duration)

    print(f"\n{BOLD}Abrindo pastas com os quadros...{RESET}")
    open_folder(dir_a)
    open_folder(dir_b)

    print(f"""
{BOLD}── INSTRUÇÃO ──────────────────────────────────────────────────────{RESET}
  Navegue pelas pastas, encontre um quadro idêntico nos dois vídeos
  e anote o número (ex: frame_00123.jpg -> número 123).
{BOLD}───────────────────────────────────────────────────────────────────{RESET}""")

    frame_n_a, pts_a = ask_frame("A", ts_a)
    frame_n_b, pts_b = ask_frame("B", ts_b)

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