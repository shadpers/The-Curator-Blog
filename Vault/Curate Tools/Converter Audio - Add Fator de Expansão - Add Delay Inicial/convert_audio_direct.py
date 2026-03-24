import sys
import json
import subprocess
import os

sys.stdout.reconfigure(line_buffering=True)

FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"

def get_audio_info(file_path, stream_index):
    """Obtém todas as informações da faixa de áudio."""
    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-select_streams", f"{stream_index}",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"Erro ao obter informações do áudio: {result.stderr}")
        sys.exit(1)
    
    data = json.loads(result.stdout)
    return data["streams"][0] if data.get("streams") else None

def build_atempo_filter(stretch_factor):
    """Constrói filtro atempo. O ffmpeg limita atempo entre 0.5 e 2.0."""
    atempo = 1.0 / stretch_factor
    filters = []
    
    while atempo < 0.5:
        filters.append("atempo=0.5")
        atempo /= 0.5
    
    while atempo > 2.0:
        filters.append("atempo=2.0")
        atempo /= 2.0
    
    filters.append(f"atempo={atempo:.6f}")
    return ",".join(filters)

def convert_audio(video_file):
    if not os.path.exists(video_file):
        print(f"Erro: Arquivo não encontrado: {video_file}")
        sys.exit(1)
    
    # Obtém informações das faixas de áudio
    cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json", "-show_streams", video_file]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    data = json.loads(result.stdout)
    
    audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    
    if not audio_streams:
        print("Erro: Nenhuma faixa de áudio encontrada.")
        sys.exit(1)
    
    # Lista faixas
    print("\n===== FAIXAS DE ÁUDIO =====")
    for i, s in enumerate(audio_streams, 1):
        lang = s.get("tags", {}).get("language", "unknown")
        title = s.get("tags", {}).get("title", "Sem título")
        codec = s.get("codec_name", "unknown")
        print(f"{i}. Lang={lang}, Title=\"{title}\", Codec={codec}")
    
    # Seleciona faixa
    while True:
        try:
            choice = int(input("\nNúmero da faixa: "))
            if 1 <= choice <= len(audio_streams):
                selected = audio_streams[choice - 1]
                break
            print(f"Escolha entre 1 e {len(audio_streams)}.")
        except ValueError:
            print("Digite um número válido.")
    
    # Escolhe método de entrada
    print("\n===== MÉTODO DE ENTRADA =====")
    print("1. Fator de Stretch (ex: 1.001102)")
    print("2. Fator FFmpeg atempo (ex: 0.95878663)")
    
    while True:
        try:
            method = int(input("\nEscolha o método (1 ou 2): "))
            if method in [1, 2]:
                break
            print("Escolha 1 ou 2.")
        except ValueError:
            print("Digite um número válido.")
    
    # Solicita fator baseado no método escolhido
    if method == 1:
        while True:
            try:
                stretch = float(input("\nFator de stretch (ex: 1.001102): "))
                if stretch > 0:
                    atempo_value = 1.0 / stretch
                    print(f"→ Fator FFmpeg equivalente: atempo={atempo_value:.8f}")
                    break
                print("O fator deve ser maior que zero.")
            except ValueError:
                print("Digite um número válido.")
    else:
        while True:
            try:
                atempo_value = float(input("\nFator FFmpeg atempo (ex: 0.95878663): "))
                if atempo_value > 0:
                    stretch = 1.0 / atempo_value
                    print(f"→ Fator de Stretch equivalente: {stretch:.8f}")
                    break
                print("O fator deve ser maior que zero.")
            except ValueError:
                print("Digite um número válido.")
    
    # Solicita delay
    while True:
        try:
            delay_ms = float(input("Delay no início em ms (ex: 100): "))
            if delay_ms >= 0:
                break
            print("O delay deve ser maior ou igual a zero.")
        except ValueError:
            print("Digite um número válido.")
    
    # Prepara conversão
    stream_index = selected['index']
    audio_info = get_audio_info(video_file, stream_index)
    
    # Obtém parâmetros originais
    codec = audio_info.get("codec_name")
    bitrate = audio_info.get("bit_rate", "192000")
    sample_rate = audio_info.get("sample_rate", "48000")
    channels = audio_info.get("channels", 2)
    lang = audio_info.get("tags", {}).get("language", "unknown")
    title = audio_info.get("tags", {}).get("title", "")
    
    # Nome do arquivo de saída
    base_name = os.path.splitext(os.path.basename(video_file))[0]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Extensão baseada no codec
    ext_map = {'aac': 'aac', 'mp3': 'mp3', 'opus': 'opus', 'ac3': 'ac3', 'flac': 'flac'}
    ext = ext_map.get(codec, 'mka')
    
    output_file = os.path.join(script_dir, f"{base_name}_stretch{stretch:.6f}_delay{delay_ms:.0f}ms.{ext}")
    
    # Constrói filtro de áudio
    atempo_filter = build_atempo_filter(stretch)
    
    if delay_ms > 0:
        delay_sec = delay_ms / 1000.0
        audio_filter = f"adelay={delay_ms}|{delay_ms},{atempo_filter}"
    else:
        audio_filter = atempo_filter
    
    print(f"\n===== CONVERTENDO =====")
    print(f"Faixa: {stream_index}")
    print(f"Codec: {codec}")
    print(f"Bitrate: {bitrate}")
    print(f"Sample rate: {sample_rate}")
    print(f"Fator de Stretch: {stretch:.8f}")
    print(f"Fator FFmpeg atempo: {atempo_value:.8f}")
    print(f"Delay: {delay_ms:.0f}ms")
    print(f"Saída: {output_file}\n")
    
    # Comando ffmpeg
    cmd = [
        FFMPEG_PATH,
        "-i", video_file,
        "-map", f"0:{stream_index}",
        "-af", audio_filter,
        "-c:a", codec,
        "-b:a", bitrate,
        "-ar", sample_rate,
        "-ac", str(channels),
        "-metadata:s:a:0", f"language={lang}",
    ]
    
    if title:
        cmd.extend(["-metadata:s:a:0", f"title={title}"])
    
    cmd.extend([output_file, "-y"])
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    
    if result.returncode != 0:
        print(f"ERRO: {result.stderr}")
        sys.exit(1)
    else:
        print(f"✓ Conversão concluída!")
        print(f"✓ Arquivo: {output_file}\n")

def main():
    if len(sys.argv) < 2:
        print("Arraste o arquivo de vídeo sobre o .bat")
        sys.exit(1)
    
    video_path = sys.argv[1].strip('"')
    print(f"Arquivo: {video_path}")
    convert_audio(video_path)

if __name__ == "__main__":
    main()