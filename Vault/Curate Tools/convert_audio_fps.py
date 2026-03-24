import sys
import json
import subprocess
import os
from fractions import Fraction
try:
    import win32com.client  # Para resolver arquivos .lnk
except ImportError:
    print("Erro: A biblioteca 'pywin32' é necessária para suportar arquivos .lnk. Instale com 'pip install pywin32'.")
    print("Erro: A biblioteca 'pywin32' é necessária para suportar arquivos .lnk. Instale com 'pip install pywin32'.", file=sys.stderr)
    sys.exit(1)

# Força saída sem buffering
sys.stdout.reconfigure(line_buffering=True)

FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"

# FPS comuns em vídeos
COMMON_FPS = {
    "1": {"name": "23.976 (23.98) - Cinema/BluRay NTSC", "value": 24000/1001},
    "2": {"name": "24.000 - Cinema", "value": 24.0},
    "3": {"name": "25.000 - PAL (Europa)", "value": 25.0},
    "4": {"name": "29.970 (29.97) - TV NTSC", "value": 30000/1001},
    "5": {"name": "30.000 - Web/Streaming", "value": 30.0},
    "6": {"name": "50.000 - PAL alta taxa", "value": 50.0},
    "7": {"name": "59.940 (59.94) - TV NTSC alta taxa", "value": 60000/1001},
    "8": {"name": "60.000 - Gaming/Web", "value": 60.0},
}

def resolve_lnk_path(file_path):
    """Resolve o caminho real de um arquivo .lnk ou retorna o caminho original se não for um .lnk."""
    try:
        if file_path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            resolved_path = shortcut.TargetPath
            if not os.path.exists(resolved_path):
                error_msg = f"Erro: O arquivo referenciado pelo atalho {file_path} não existe: {resolved_path}"
                print(error_msg)
                print(error_msg, file=sys.stderr)
                sys.exit(1)
            return resolved_path
        return file_path
    except Exception as e:
        error_msg = f"Erro ao resolver o atalho {file_path}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def ffprobe_json(file_path):
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            error_msg = f"Erro ao executar ffprobe para {file_path}: {result.stderr}"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        return json.loads(result.stdout)
    except Exception as e:
        error_msg = f"Erro ao processar ffprobe para {file_path}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def get_video_fps(data):
    """Obtém o FPS do vídeo."""
    try:
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                fps_str = stream.get("r_frame_rate", "0/1")
                num, den = map(int, fps_str.split('/'))
                if den != 0:
                    return num / den
        return None
    except Exception as e:
        error_msg = f"Erro ao obter FPS do vídeo: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        return None

def get_audio_streams(data):
    try:
        audio_streams = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                lang = stream.get("tags", {}).get("language", "unknown")
                audio_streams.append({
                    "index": stream["index"],
                    "lang": lang,
                    "title": stream.get("tags", {}).get("title", "Sem título"),
                    "channels": stream.get("channels", "unknown"),
                    "codec": stream.get("codec_name", "unknown")
                })
        return audio_streams
    except Exception as e:
        error_msg = f"Erro ao processar streams de áudio: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def get_audio_info(file_path, stream_index):
    """Obtém informações detalhadas de uma faixa de áudio específica."""
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-select_streams", f"{stream_index}",
            "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate",
            "-of", "json",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            return {
                "codec": stream.get("codec_name", "aac"),
                "sample_rate": stream.get("sample_rate", "48000"),
                "channels": stream.get("channels", 2),
                "bit_rate": stream.get("bit_rate", None)
            }
        else:
            return {
                "codec": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": None
            }
    except:
        return {
            "codec": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "bit_rate": None
        }

def get_extension_for_codec(codec):
    """Retorna a extensão apropriada para o codec."""
    codec_map = {
        'aac': 'aac',
        'mp3': 'mp3',
        'opus': 'opus',
        'vorbis': 'ogg',
        'flac': 'flac',
        'ac3': 'ac3',
        'eac3': 'eac3',
        'dts': 'dts',
        'truehd': 'thd',
        'pcm_s16le': 'wav',
        'pcm_s24le': 'wav',
    }
    return codec_map.get(codec, 'mkv')

def build_atempo_filter(atempo):
    """
    Constrói filtro atempo. O ffmpeg limita atempo entre 0.5 e 2.0.
    Se o valor estiver fora desse range, encadeia múltiplos filtros.
    """
    filters = []
    
    while atempo < 0.5:
        filters.append("atempo=0.5")
        atempo /= 0.5
    
    while atempo > 2.0:
        filters.append("atempo=2.0")
        atempo /= 2.0
    
    filters.append(f"atempo={atempo:.10f}")
    
    return ",".join(filters)

def convert_audio(video_file, script_dir):
    try:
        # Resolve caminho de atalho .lnk
        video_file = resolve_lnk_path(video_file)
        
        # Obtém informações do arquivo
        data = ffprobe_json(video_file)
        audio_streams = get_audio_streams(data)
        current_fps = get_video_fps(data)
        
        if not audio_streams:
            error_msg = "Erro: Não encontrou faixas de áudio no arquivo."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        # Mostra FPS atual
        print("\n===== INFORMAÇÕES DO VÍDEO =====")
        if current_fps:
            print(f"FPS atual do vídeo: {current_fps:.3f}")
        else:
            print("FPS atual do vídeo: Não detectado")
        
        # Lista faixas disponíveis
        print("\n===== FAIXAS DE ÁUDIO DISPONÍVEIS =====")
        for i, audio in enumerate(audio_streams, 1):
            print(f"{i}. Lang={audio['lang']}, Title=\"{audio['title']}\", Codec={audio['codec']}, Canais={audio['channels']}")
        
        # Seleciona faixa
        while True:
            try:
                choice = input("\nDigite o número da faixa a converter: ")
                choice = int(choice)
                if 1 <= choice <= len(audio_streams):
                    selected_audio = audio_streams[choice - 1]
                    break
                else:
                    print(f"Por favor, escolha um número entre 1 e {len(audio_streams)}.")
            except ValueError:
                print("Entrada inválida. Digite um número.")
        
        # Mostra opções de FPS
        print("\n===== ESCOLHA O FPS DE DESTINO =====")
        for key in sorted(COMMON_FPS.keys(), key=int):
            print(f"{key}. {COMMON_FPS[key]['name']}")
        print("9. Digite manualmente o FPS de destino")
        
        # Seleciona FPS de destino
        target_fps = None
        while True:
            try:
                fps_choice = input("\nDigite o número da opção desejada: ")
                
                if fps_choice == "9":
                    fps_input = input("Digite o FPS de destino (ex: 23.976): ")
                    target_fps = float(fps_input)
                    if target_fps <= 0:
                        print("O FPS deve ser maior que zero.")
                        continue
                    break
                elif fps_choice in COMMON_FPS:
                    target_fps = COMMON_FPS[fps_choice]['value']
                    print(f"FPS selecionado: {target_fps:.6f}")
                    break
                else:
                    print(f"Por favor, escolha uma opção entre 1 e 9.")
            except ValueError:
                print("Entrada inválida. Digite um número.")
        
        # Calcula o fator de conversão
        if current_fps and current_fps > 0:
            factor = target_fps / current_fps
            print(f"\nFator calculado automaticamente: {factor:.10f}")
            print(f"(De {current_fps:.3f} fps para {target_fps:.3f} fps)")
        else:
            print(f"\nNão foi possível detectar o FPS atual. Calculando baseado no FPS de destino: {target_fps:.3f}")
            factor = 1.0
        
        # Preparar conversão
        stream_index = selected_audio['index']
        audio_info = get_audio_info(video_file, stream_index)
        codec = audio_info['codec']
        sample_rate = audio_info['sample_rate']
        lang = selected_audio['lang']
        title = selected_audio['title']
        
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        
        # Determina codec de saída ANTES de definir o nome do arquivo
        if codec in ['flac', 'pcm_s16le', 'pcm_s24le']:
            # Áudio já é lossless, mantém o codec
            codec_out = codec
            ext_out = get_extension_for_codec(codec)
            bitrate_args = []
        else:
            # Para codec lossy, usa FLAC para conversão sem perdas
            codec_out = 'flac'
            ext_out = 'flac'
            bitrate_args = ['-compression_level', '5']
        
        output_file = os.path.join(script_dir, f"{base_name}_track{stream_index}_{target_fps:.3f}fps.{ext_out}")
        
        atempo = 1.0 / factor
        atempo_filter = build_atempo_filter(atempo)
        
        print(f"\n===== CONVERTENDO (SEM PERDAS) =====")
        print(f"Faixa: {stream_index} ({lang}, {codec})")
        print(f"FPS origem: {current_fps:.3f}" if current_fps else "FPS origem: Não detectado")
        print(f"FPS destino: {target_fps:.3f}")
        print(f"Fator de conversão: {factor:.10f}")
        print(f"Fator de tempo (atempo): {atempo:.10f}")
        print(f"Codec de saída: {codec_out}")
        print(f"Arquivo de saída: {output_file}")
        print("Aguarde...\n")
        
        cmd = [
            FFMPEG_PATH,
            "-i", video_file,
            "-map", f"0:{stream_index}",
            "-af", f"{atempo_filter},aresample={sample_rate}",
            "-c:a", codec_out,
        ]
        
        cmd.extend(bitrate_args)
        
        cmd.extend([
            "-metadata:s:a:0", f"language={lang}",
            "-metadata:s:a:0", f"title={title}",
            output_file,
            "-y"
        ])
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        
        if result.returncode != 0:
            print(f"ERRO ao converter: {result.stderr}")
            sys.exit(1)
        else:
            print(f"✓ Conversão concluída com sucesso!")
            print(f"✓ Codec de saída: {codec_out} (sem perdas)")
            print(f"✓ Arquivo salvo em: {output_file}\n")
    
    except Exception as e:
        error_msg = f"Erro: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def main():
    try:
        if len(sys.argv) < 2:
            error_msg = "Uso: python convert_audio_fps.py <arquivo_video>"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        video_path = sys.argv[1]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"Arquivo de vídeo: {video_path}")
        
        convert_audio(video_path, script_dir)
    
    except Exception as e:
        error_msg = f"Erro no script: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()