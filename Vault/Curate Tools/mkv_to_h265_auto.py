import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import re

FFMPEG = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"

# ------------------------------------------------------------

def die(msg):
    print(f"\nERRO: {msg}")
    input("Pressione ENTER para sair...")
    sys.exit(1)

if not os.path.isfile(FFMPEG):
    die(f"ffmpeg nao encontrado em {FFMPEG}")

if not os.path.isfile(FFPROBE):
    die(f"ffprobe nao encontrado em {FFPROBE}")

# ------------------------------------------------------------

def probe(cmd, file):
    p = subprocess.run(
        [FFPROBE] + cmd + [str(file)],
        capture_output=True,
        text=True
    )
    return p.stdout.strip()

# ------------------------------------------------------------

def get_duration(file):
    try:
        return float(probe(
            ['-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0'], file))
    except:
        return 0.0

# ------------------------------------------------------------

def get_resolution(file):
    """Detecta altura do vídeo (1080p, 720p, etc)"""
    try:
        return int(probe(
            ['-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=height',
             '-of', 'csv=p=0'], file))
    except:
        return 1080

# ------------------------------------------------------------

def get_video_size_bytes(file):
    try:
        out = probe(
            ['-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=index',
             '-of', 'csv=p=0'], file)

        cmd = [
            FFMPEG, '-i', str(file),
            '-map', '0:v:0',
            '-c', 'copy',
            '-f', 'null', '-'
        ]

        p = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)

        m = re.search(r'video:(\d+)kB', p.stderr)
        if m:
            return int(m.group(1)) * 1024
    except:
        pass

    # fallback: assume 85% video
    return int(file.stat().st_size * 0.85)

# ------------------------------------------------------------

def calc_video_bitrate_kbps(file, duration):
    size_bytes = get_video_size_bytes(file)
    if duration <= 0:
        return 0
    return int((size_bytes * 8) / duration / 1000)

# ------------------------------------------------------------

def decide_params(v_bitrate_kbps, src_size_gb, height):
    """
    Lógica otimizada para mínima perda de qualidade
    Considera: bitrate, tamanho E resolução
    """
    
    # Ajuste baseado em resolução
    res_adjust = 0
    if height >= 2160:  # 4K
        res_adjust = -2
        res_label = "4K"
    elif height >= 1440:  # 2K
        res_adjust = -1
        res_label = "2K"
    elif height >= 1070:  # 1080p (com margem para crops)
        res_label = "1080p"
    elif height >= 700:  # 720p
        res_adjust = 1
        res_label = "720p"
    else:
        res_adjust = 2
        res_label = f"{height}p"
    
    # Lógica principal baseada em bitrate (ARQUIVAL)
    if v_bitrate_kbps >= 18000:
        base_cq = 12
        level = "ARQUIVAL (transparente)"
    elif v_bitrate_kbps >= 14000:
        base_cq = 13
        level = "REFERENCIA (quase transparente)"
    elif v_bitrate_kbps >= 10000:
        base_cq = 14
        level = "PREMIUM (perda imperceptível)"
    elif v_bitrate_kbps >= 7000:
        base_cq = 15
        level = "ALTA (mínima perda)"
    else:
        base_cq = 16
        level = "MEDIA-ALTA (boa qualidade)"
    
    # Aplicar ajuste de resolução
    cq = base_cq + res_adjust
    
    # Garantir limites (permite CQ 12-20)
    cq = max(12, min(20, cq))
    
    print(f"Resolução: {res_label}")
    print(f"Complexidade: {level}")
    print(f"CQ base: {base_cq} | Ajuste resolução: {res_adjust:+d} | CQ final: {cq}")

    return [
        "-c:v", "hevc_nvenc",
        "-profile:v", "main10",
        "-tier", "high",  # Permite bitrates mais altos
        "-pix_fmt", "p010le",
        "-rc", "vbr_hq",
        "-cq", str(cq),
        "-preset", "p7",  # Máxima qualidade (mais lento que p6)
        "-rc-lookahead", "32",  # Melhora decisões de encoding
        "-b_ref_mode", "middle",  # B-frames mais eficientes
        "-bf", "4",  # 4 B-frames
        "-spatial_aq", "1",
        "-temporal_aq", "1",
        "-aq-strength", "8",
        "-nonref_p", "1",  # Permite P-frames não-referência
        "-strict_gop", "1"  # GOP consistente
    ]

# ------------------------------------------------------------

def run_ffmpeg(cmd, duration):
    cmd = cmd[:1] + ['-loglevel', 'error', '-stats'] + cmd[1:]
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    last = -1
    print("Progresso:")

    for line in p.stdout:
        if "time=" in line:
            m = re.search(r'time=(\d+:\d+:\d+\.\d+)', line)
            if m and duration > 0:
                t = parse_time(m.group(1))
                pct = min((t / duration) * 100, 100)
                if abs(pct - last) >= 0.5:
                    last = pct
                    bar = int(pct // 3) * "█"
                    bar = bar.ljust(30, "░")
                    print(f"\r[{bar}] {pct:5.1f}%", end="", flush=True)

    p.wait()
    print()
    return p.returncode == 0

# ------------------------------------------------------------

def parse_time(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

# ------------------------------------------------------------

def process(file):
    src = Path(file)
    if not src.exists():
        die("Arquivo nao encontrado")

    out = src.with_name(src.stem + "_H265.mkv")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as tmp:
        tmp_path = Path(tmp.name)

    shutil.copy2(src, tmp_path)

    try:
        duration = get_duration(tmp_path)
        if duration <= 0:
            duration = 1500

        height = get_resolution(tmp_path)
        src_size_gb = src.stat().st_size / (1024**3)
        v_bitrate = calc_video_bitrate_kbps(tmp_path, duration)

        print(f"Tamanho source: {src_size_gb:.2f} GB")
        print(f"Bitrate real do video: {v_bitrate} kbps")

        vopts = decide_params(v_bitrate, src_size_gb, height)

        cmd = [
            FFMPEG, "-y",
            "-i", str(tmp_path),
            "-map", "0:v:0"  # APENAS vídeo
        ] + vopts + [
            "-map_metadata", "-1",  # Remove metadata
            "-map_chapters", "-1",  # Remove chapters
            str(out)
        ]

        ok = run_ffmpeg(cmd, duration)
        if ok:
            out_size_gb = out.stat().st_size / (1024**3)
            reduction = ((src_size_gb - out_size_gb) / src_size_gb) * 100
            print(f"SUCESSO: {out.name}")
            print(f"Tamanho final: {out_size_gb:.2f} GB (redução de {reduction:.1f}%)")
        return ok

    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

# ------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    success = True
    for f in sys.argv[1:]:
        print("=" * 50)
        print(f"Processando: {Path(f).name}")
        print("=" * 50)
        if not process(f):
            success = False

    sys.exit(0 if success else 1)

# ------------------------------------------------------------

if __name__ == "__main__":
    main()