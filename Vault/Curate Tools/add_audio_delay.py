import sys
import json
import subprocess
import os

try:
    import win32com.client  # Para .lnk
except ImportError:
    print("\033[31mERRO: Biblioteca 'pywin32' não encontrada.\033[0m")
    print("Instale com: \033[33mpip install pywin32\033[0m", file=sys.stderr)
    sys.exit(1)

# Força saída sem buffering
sys.stdout.reconfigure(line_buffering=True)

FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG  = r"C:\FFmpeg\bin\ffmpeg.exe"

# Cores ANSI
C = {
    "reset":  "\033[0m",
    "red":    "\033[31m",
    "green":  "\033[32m",
    "yellow": "\033[33m",
    "blue":   "\033[34m",
    "purple": "\033[35m",
    "cyan":   "\033[36m",
    "white":  "\033[97m",
    "bold":   "\033[1m",
}

def resolve_lnk(file_path):
    if not file_path.lower().endswith('.lnk'):
        return file_path
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(file_path)
        real_path = shortcut.TargetPath
        if not os.path.exists(real_path):
            print(f"{C['red']}O atalho aponta para um arquivo que não existe:{C['reset']}")
            print(f"  → {real_path}")
            sys.exit(1)
        return real_path
    except Exception as e:
        print(f"{C['red']}Erro ao ler atalho .lnk: {e}{C['reset']}", file=sys.stderr)
        sys.exit(1)

def get_ffprobe_json(path):
    try:
        cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(r.stdout)
    except Exception as e:
        print(f"{C['red']}Falha ao ler informações do arquivo com ffprobe:{C['reset']}")
        print(f"  → {e}")
        sys.exit(1)

def list_audio_tracks(data):
    tracks = []
    for s in data.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        tags = s.get("tags", {})
        tracks.append({
            "index": s["index"],
            "lang":  tags.get("language", "und"),
            "title": tags.get("title", "sem título"),
            "codec": s.get("codec_name", "—"),
            "ch":    s.get("channels", "?"),
        })
    return tracks

def get_bitrate(path, stream_idx):
    try:
        cmd = [
            FFPROBE, "-v", "quiet", "-select_streams", str(stream_idx),
            "-show_entries", "stream=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", path
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        br = r.stdout.strip()
        return br if br else "N/A"
    except:
        return "N/A"

def get_ext(codec):
    m = {
        'aac': 'aac', 'mp3': 'mp3', 'opus': 'opus', 'vorbis': 'ogg', 'flac': 'flac',
        'ac3': 'ac3', 'eac3': 'eac3', 'dts': 'dts', 'truehd': 'thd',
        'pcm_s16le': 'wav', 'pcm_s24le': 'wav',
    }
    return m.get(codec, 'mkv')

def delay_filter(delay_ms):
    if delay_ms == 0:
        return None
    if delay_ms > 0:
        return f"adelay={delay_ms}|{delay_ms}"
    else:
        cut = abs(delay_ms) / 1000.0
        return f"atrim=start={cut:.3f},asetpts=PTS-STARTPTS"

def main():
    if len(sys.argv) < 2:
        print(f"\n{C['yellow']}Uso:{C['reset']}")
        print(f"  Arraste um vídeo (ou atalho .lnk) neste .bat\n")
        input("Pressione ENTER para sair...")
        sys.exit(1)

    video = resolve_lnk(sys.argv[1])
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"\n{C['cyan']}{C['bold']}══════ Áudio Delay Tool ══════{C['reset']}")
    print(f"Arquivo: {C['white']}{os.path.basename(video)}{C['reset']}\n")

    data = get_ffprobe_json(video)
    tracks = list_audio_tracks(data)

    if not tracks:
        print(f"{C['red']}Nenhuma faixa de áudio encontrada.{C['reset']}")
        sys.exit(1)

    print(f"{C['yellow']}Faixas de áudio disponíveis:{C['reset']}\n")
    for i, t in enumerate(tracks, 1):
        print(f"  {C['green']}{i}{C['reset']}.  "
              f"{t['lang']:>3} | {t['title'][:38]:<38} | "
              f"{t['codec']:>6} | {t['ch']:>2}ch")

    print()
    while True:
        try:
            op = input(f"{C['cyan']}Digite o número da faixa → {C['reset']}")
            idx = int(op) - 1
            if 0 <= idx < len(tracks):
                selected = tracks[idx]
                break
            print(f"{C['yellow']}Escolha entre 1 e {len(tracks)}{C['reset']}")
        except:
            print(f"{C['yellow']}Digite apenas o número da faixa{C['reset']}")

    print(f"\n{C['purple']}Faixa selecionada → {selected['lang']} | {selected['title']}{C['reset']}\n")

    print(f"  {C['bold']}Insira o delay em MS:{C['reset']}")
    print(f"   {C['green']}+positivo{C['reset']}  → atrasa o áudio (adiciona silêncio no começo)")
    print(f"   {C['red']}-negativo{C['reset']}  → adianta o áudio (corta o início)")
    print(f"          {C['white']}0{C['reset']}  → sem alteração\n")

    while True:
        try:
            delay_txt = input(f"{C['cyan']}Delay em milissegundos (ex: 850, -1200, 0) → {C['reset']}")
            delay_ms = round(float(delay_txt))
            break
        except:
            print(f"{C['yellow']}Digite um número (pode ser negativo){C['reset']}")

    bitrate_raw = get_bitrate(video, selected['index'])
    bitrate_display = bitrate_raw if bitrate_raw != "N/A" else "N/A (HE-AAC variável)"

    print(f"\n{C['yellow']}Resumo da conversão:{C['reset']}")
    print(f"  • Faixa    : {selected['index']} ({selected['lang']})")
    print(f"  • Delay    : {C['bold']}{delay_ms:+} ms{C['reset']}")
    print(f"  • Codec    : {selected['codec']}")
    print(f"  • Bitrate  : {bitrate_display}")
    
    base = os.path.splitext(os.path.basename(video))[0]
    sign = "plus" if delay_ms >= 0 else "minus"
    val = abs(delay_ms)
    ext = get_ext(selected['codec'])
    out_name = f"{base}_track{selected['index']}_delay{sign}{val}ms.{ext}"
    output = os.path.join(script_dir, out_name)

    print(f"  • Arquivo  : {C['white']}{out_name}{C['reset']}\n")

    af_parts = []
    delay_af = delay_filter(delay_ms)
    if delay_af:
        af_parts.append(delay_af)
    # Sempre adiciona este filtro final para ajudar na compatibilidade futura com MP4
    af_parts.append("aresample=async=1:first_pts=0")
    af_string = ",".join(af_parts)

    cmd = [
        FFMPEG,
        "-i", video,
        "-map", f"0:{selected['index']}",
        "-c:a", selected['codec'],  # força reencode mantendo o codec original
    ]

    # Só adiciona bitrate se for um valor válido
    if bitrate_raw != "N/A" and bitrate_raw.isdigit():
        cmd.extend(["-b:a", bitrate_raw])
    else:
        # Valor seguro para HE-AAC estéreo (qualidade próxima à original)
        cmd.extend(["-b:a", "96k"])

    cmd.extend([
        "-af", af_string,
        "-metadata:s:a:0", f"language={selected['lang']}",
        "-metadata:s:a:0", f"title={selected['title']}",
        "-map_metadata", "-1",
        "-y",
        output
    ])

    print(f"{C['green']}Iniciando processamento...{C['reset']}\n")
    print(f"Comando ffmpeg sendo executado:\n  {' '.join(cmd)}\n")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            print(f"\n{C['green']}{C['bold']}CONCLUÍDO COM SUCESSO!{C['reset']}")
            print(f"Arquivo salvo em:\n  {C['white']}{output}{C['reset']}\n")
        else:
            print(f"{C['red']}ERRO durante a conversão:{C['reset']}")
            print(r.stderr.strip() or "Sem detalhes de erro (verifique o console)")
    except Exception as e:
        print(f"{C['red']}Falha ao executar ffmpeg:{C['reset']}")
        print(e)

    input(f"\n{C['cyan']}Pressione ENTER para fechar...{C['reset']}")

if __name__ == "__main__":
    main()