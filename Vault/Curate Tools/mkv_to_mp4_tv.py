import sys
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import re

FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"

def run_ffprobe(args, input_file):
    """Run ffprobe and return stdout as string."""
    full_args = [FFPROBE_PATH] + args + [str(input_file)]
    try:
        result = subprocess.run(full_args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"ERRO no ffprobe: {e}")
        print(f"Args: {' '.join(full_args)}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERRO: ffprobe nao encontrado em {FFPROBE_PATH}. Verifique o caminho.")
        sys.exit(1)

def get_duration(tmp_file):
    """Get duration in seconds from video."""
    duration_str = run_ffprobe(['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0'], tmp_file)
    try:
        return float(duration_str)
    except ValueError:
        return 0.0

def parse_time_to_seconds(time_str):
    """Parse HH:MM:SS.ss to seconds."""
    if not time_str:
        return 0.0
    m = re.match(r'(\d+):(\d+):(\d+(?:\.\d+)?)', time_str)
    if m:
        h, m_val, s = map(float, m.groups())
        return h * 3600 + m_val * 60 + s
    return 0.0

def run_ffmpeg_with_progress(cmd, duration):
    """Run ffmpeg with clean single-line progress bar."""
    try:
        # Suppress ffmpeg output except errors
        cmd = cmd[:1] + ['-loglevel', 'error', '-stats'] + cmd[1:]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                   text=True, bufsize=1, universal_newlines=True)
        
        print("Progresso: ", end='', flush=True)
        last_progress = -1
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output and 'time=' in output:
                time_match = re.search(r'time=(\d+:\d+:\d+(?:\.\d+)?)', output)
                if time_match:
                    current_time = parse_time_to_seconds(time_match.group(1))
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        # Only update if progress changed by at least 0.5%
                        if abs(progress - last_progress) >= 0.5 or progress >= 99.9:
                            last_progress = progress
                            bar_length = 30
                            filled = int(bar_length * progress / 100)
                            bar = '█' * filled + '░' * (bar_length - filled)
                            
                            time_str = f"{int(current_time//3600):02d}:{int((current_time%3600)//60):02d}:{int(current_time%60):02d}"
                            dur_str = f"{int(duration//3600):02d}:{int((duration%3600)//60):02d}:{int(duration%60):02d}"
                            
                            # Clear line and rewrite
                            print(f'\r[{bar}] {progress:.1f}% - {time_str}/{dur_str}', end='', flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            # Final completion message
            bar = '█' * 30
            dur_str = f"{int(duration//3600):02d}:{int((duration%3600)//60):02d}:{int(duration%60):02d}"
            print(f'\r[{bar}] 100.0% - {dur_str}/{dur_str} - Concluido!     ')
            return True
        else:
            print(f"\n\nERRO no FFmpeg (return code {process.returncode}).")
            return False
            
    except FileNotFoundError:
        print(f"\nERRO: ffmpeg nao encontrado em {FFMPEG_PATH}. Verifique o caminho.")
        return False
    except KeyboardInterrupt:
        print("\n\nProcessamento interrompido pelo usuario.")
        process.terminate()
        return False

def get_video_info(tmp_file):
    """Get video codec and pix_fmt."""
    codec = run_ffprobe(['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'default=nokey=1:noprint_wrappers=1'], tmp_file)
    pix_fmt = run_ffprobe(['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=pix_fmt', '-of', 'default=nokey=1:noprint_wrappers=1'], tmp_file)
    print(f"Video: {codec} / {pix_fmt}")
    return codec.lower(), pix_fmt.lower()

def get_audio_streams(tmp_file):
    """Get audio streams with language tags. Returns list of (global_idx, lang, local_audio_idx)."""
    output = run_ffprobe(['-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index:stream_tags=language', '-of', 'csv=p=0'], tmp_file)
    streams = []
    local_idx = 0
    for line in output.splitlines():
        if line.strip():
            parts = line.split(',', 1)
            if len(parts) == 2:
                global_idx = int(parts[0])
                lang = parts[1].strip().lower()
                if lang in ['por', 'pt', 'pt-br', 'pt_br']:
                    streams.append((global_idx, lang, local_idx))
                local_idx += 1
    return streams

def get_audio_info(tmp_file, local_a_idx):
    """Get audio codec, channels, bit_rate. Uses local audio index."""
    codec = run_ffprobe(['-v', 'error', '-select_streams', f'a:{local_a_idx}', '-show_entries', 'stream=codec_name', '-of', 'default=nokey=1:noprint_wrappers=1'], tmp_file)
    channels = run_ffprobe(['-v', 'error', '-select_streams', f'a:{local_a_idx}', '-show_entries', 'stream=channels', '-of', 'default=nokey=1:noprint_wrappers=1'], tmp_file)
    bit_rate = run_ffprobe(['-v', 'error', '-select_streams', f'a:{local_a_idx}', '-show_entries', 'stream=bit_rate', '-of', 'default=nokey=1:noprint_wrappers=1'], tmp_file)
    print(f"Audio: {codec} / {channels}ch / {bit_rate}bps")
    return codec.lower(), int(channels) if channels.isdigit() else 2, bit_rate if bit_rate.isdigit() else None

def build_ffmpeg_cmd(tmp_file, out_file, vopts, local_a_idx, acodec, a_channels, a_bitrate):
    """Build FFmpeg command."""
    cmd = [
        FFMPEG_PATH, '-y', '-i', str(tmp_file),
        '-map', '0:v:0'
    ]
    cmd += vopts.split()
    cmd += [
        '-map', f'0:a:{local_a_idx}'
    ]
    if acodec == 'aac':
        cmd += ['-c:a', 'copy']
    else:
        if a_bitrate:
            cmd += ['-c:a', 'aac', '-b:a', str(a_bitrate), '-ac', str(a_channels)]
        else:
            cmd += ['-c:a', 'aac', '-q:a', '2', '-ac', str(a_channels)]
    cmd += [
        '-map_metadata', '-1', '-map_chapters', '-1',
        '-movflags', '+faststart', str(out_file)
    ]
    return cmd

def process_file(src):
    """Process a single file."""
    src = Path(src)
    if not src.exists():
        print(f"ERRO: Arquivo nao existe: {src}")
        return False
    
    out_dir = src.parent
    name = src.stem
    out = out_dir / f"{name}_TV.mp4"
    
    print(f"Processando: {src.name}")
    print(f"Destino: {out.name}")
    
    # Copy to temp
    with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        print("Copiando para TEMP...", end='', flush=True)
        shutil.copy2(src, tmp_path)
        print(" OK")
    except Exception as e:
        print(f"\nERRO na copia: {e}")
        return False
    
    try:
        # Video info
        v_codec, v_pix = get_video_info(tmp_path)
        
        if v_codec == 'h264' and v_pix == 'yuv420p':
            print("Video compativel -> COPY")
            vopts = '-c:v copy'
        else:
            print("Video incompativel -> NVENC (re-encode)")
            vopts = '-c:v h264_nvenc -pix_fmt yuv420p -profile:v high -level 4.1 -rc vbr -cq 23 -preset p5'
        
        # Get duration for progress
        duration = get_duration(tmp_path)
        if duration == 0:
            print("AVISO: Duracao desconhecida, usando estimativa.")
            duration = 2580  # Fallback: 43min
        
        # Audio streams
        audio_streams = get_audio_streams(tmp_path)
        if not audio_streams:
            print("ERRO: Nenhum audio PT-BR encontrado!")
            return False
        
        if len(audio_streams) == 1:
            _, _, local_a_idx = audio_streams[0]
            print(f"Audio PT-BR: stream {local_a_idx}")
        else:
            print(f"\n{len(audio_streams)} audios PT-BR encontrados:")
            for i, (global_idx, lang, local_idx) in enumerate(audio_streams, 1):
                print(f"  {i}. Stream {local_idx} (global {global_idx}, lang: {lang})")
            choice = input("Escolha (1-{}): ".format(len(audio_streams))).strip()
            try:
                choice = int(choice) - 1
                if 0 <= choice < len(audio_streams):
                    _, _, local_a_idx = audio_streams[choice]
                else:
                    print("Opcao invalida, usando o primeiro.")
                    _, _, local_a_idx = audio_streams[0]
            except ValueError:
                print("Entrada invalida, usando o primeiro.")
                _, _, local_a_idx = audio_streams[0]
            print(f"Selecionado: stream {local_a_idx}")
        
        # Audio info
        acodec, achannels, abr = get_audio_info(tmp_path, local_a_idx)
        
        # Build and run FFmpeg
        print()
        cmd = build_ffmpeg_cmd(tmp_path, out, vopts, local_a_idx, acodec, achannels, abr)
        
        success = run_ffmpeg_with_progress(cmd, duration)
        
        if success:
            print(f"\nSUCESSO: {out.name}")
            return True
        else:
            print(f"\nFALHA no processamento.")
            return False
    
    finally:
        # Cleanup
        try:
            os.unlink(tmp_path)
        except:
            pass

def main():
    files = sys.argv[1:]
    if not files:
        print("Uso: python mkv_to_mp4_tv.py <arquivo.mkv> [...]")
        sys.exit(1)
    
    successes = 0
    for i, file_path in enumerate(files, 1):
        if len(files) > 1:
            print(f"\n{'='*50}")
            print(f"Arquivo {i}/{len(files)}")
            print('='*50)
        
        if process_file(file_path):
            successes += 1
        
        if len(files) > 1 and i < len(files):
            print()  # Space between files
    
    if len(files) > 1:
        print(f"\n{'='*50}")
        print(f"RESUMO: {successes}/{len(files)} processados com sucesso")
        print('='*50)
    
    sys.exit(0 if successes == len(files) else 1)

if __name__ == "__main__":
    main()