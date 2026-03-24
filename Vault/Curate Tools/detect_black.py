import subprocess
import re
import sys
import os
from colorama import init, Fore, Style

# Inicializa o Colorama para funcionar no Windows
init()

def analisar_video(video_path, segundos_iniciais=6, threshold_ms=10, pix_threshold=0.10,
                    silence_threshold=-40, silence_duration=0.1):
    ffmpeg_path = os.getenv('FFMPEG', 'ffmpeg')

    cmd = [
        ffmpeg_path, '-t', str(segundos_iniciais), '-i', video_path,
        '-analyzeduration', '100M', '-probesize', '100M',
        '-vf', f'blackdetect=d={threshold_ms/1000}:pix_th={pix_threshold}',
        '-af', f'silencedetect=noise={silence_threshold}dB:d={silence_duration}',
        '-f', 'null', '-'
    ]

    try:
        resultado = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        output = resultado.stderr

        video_name = os.path.basename(video_path)
        print(f"{Fore.GREEN}Vídeo: {video_name}{Style.RESET_ALL}")

        duration_match = re.search(r'Duration: (\d{2}:\d{2}:\d{2}\.\d{2})', output)
        duration_str = duration_match.group(1) if duration_match else "Desconhecida"
        print(f"{Fore.GREEN}Duração total: {duration_str}{Style.RESET_ALL}")

        primeiro_black = True
        primeiro_silence = True
        primeiro_black_val = None
        primeiro_silence_val = None

        for line in output.splitlines():
            # Blackdetect
            if 'blackdetect' in line and primeiro_black:
                match = re.search(r'black_start:([\d\.]+)\s*black_end:([\d\.]+)\s*black_duration:([\d\.]+)', line)
                if match:
                    start, end, dur = match.groups()
                    print(f"{Fore.CYAN}[blackdetect] black_start:{start} black_end:{end} {Fore.RED}black_duration:{dur}{Style.RESET_ALL}")
                    primeiro_black_val = dur
                    primeiro_black = False

            # Silencedetect
            elif 'silence_' in line and primeiro_silence:
                match_start = re.search(r'silence_start:\s*([\d\.]+)', line)
                if match_start:
                    print(f"{Fore.CYAN}[silencedetect] silence_start: {match_start.group(1)}{Style.RESET_ALL}")
                match_end = re.search(r'silence_end:\s*([\d\.]+)\s*\|\s*silence_duration:\s*([\d\.]+)', line)
                if match_end:
                    end, dur = match_end.groups()
                    print(f"{Fore.CYAN}[silencedetect] silence_end: {end} | {Fore.RED}silence_duration: {dur}{Style.RESET_ALL}")
                    primeiro_silence_val = dur
                    primeiro_silence = False  # ignora próximos blocos

        # Resumo final sempre mostrando valores numéricos
        print(f"\n{Fore.YELLOW}Resumo do primeiro bloco detectado:{Style.RESET_ALL}")
        print(f"{Fore.RED}Black duration: {primeiro_black_val if primeiro_black_val else '0'} ms | "
              f"Silence duration: {primeiro_silence_val if primeiro_silence_val else '0'} ms{Style.RESET_ALL}")

        return output

    except subprocess.CalledProcessError as e:
        print(f"{Fore.RED}Erro ao executar FFmpeg: {e}{Style.RESET_ALL}")
        print(f"{Fore.RED}Saída de erro: {e.stderr}{Style.RESET_ALL}")
        return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"{Fore.RED}Uso: python detect_black.py seu_video.mkv{Style.RESET_ALL}")
    else:
        analisar_video(sys.argv[1])
