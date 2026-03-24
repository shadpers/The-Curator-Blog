import sys
import subprocess
import os
import shutil
import re

def has_special_chars(path):
    # Caracteres problemáticos para .bat e FFmpeg no Windows
    return bool(re.search(r'[&^%$!]', path))

def get_safe_file_path(original_path):
    if has_special_chars(original_path):
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        temp_name = f"temp_{base_name}"
        temp_path = os.path.join(dir_name, temp_name)
        shutil.copy2(original_path, temp_path)
        print(f"Arquivo contém caracteres especiais. Criando cópia temporária: {temp_path}")
        return temp_path, True
    else:
        return original_path, False

def cleanup_temp_file(temp_path, was_temp):
    if was_temp:
        try:
            os.remove(temp_path)
            print(f"Arquivo temporário removido: {temp_path}")
        except Exception as e:
            print(f"Erro ao remover arquivo temporário: {e}")

def get_mkv_info(file_path):
    print(f"Analisando arquivo: {file_path}")
    ffmpeg_path = "C:\\FFmpeg\\bin\\ffmpeg.exe"
    if not os.path.exists(ffmpeg_path):
        print(f"Erro: FFmpeg não encontrado em {ffmpeg_path}. Instale o FFmpeg ou ajuste o caminho.")
        sys.exit(1)
    
    command = [
        ffmpeg_path,
        "-i", file_path,
        "-hide_banner",
        "-loglevel", "info",
        "-analyzeduration", "10000000",
        "-probesize", "10000000"
    ]
    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if process.stderr:
        print(f"Saída do FFmpeg: {process.stderr}")
    return process.stderr

def parse_mkv_info(ffmpeg_output):
    video_codec = None
    audio_tracks = []
    current_stream = None

    for line in ffmpeg_output.splitlines():
        line = line.strip()
        if 'Stream #0:' in line and 'Audio:' in line:
            try:
                stream_part, audio_part = line.split('Audio:')
                track_id = stream_part.split('#0:')[1].split('(')[0].strip()
                codec_part = audio_part.strip().split(' ')[0].replace(',', '')

                sample_rate = None
                if 'Hz' in audio_part:
                    sample_rate = audio_part.split('Hz')[0].strip().split(' ')[-1]

                channels = None
                if 'stereo' in audio_part:
                    channels = 'stereo'
                elif 'mono' in audio_part:
                    channels = 'mono'
                elif '5.1' in audio_part:
                    channels = '5.1'

                bitrate = None
                if 'kb/s' in audio_part:
                    bitrate = audio_part.split('kb/s')[0].strip().split(' ')[-1]

                current_stream = {
                    'id': track_id,
                    'codec': codec_part,
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'bitrate': bitrate
                }
                audio_tracks.append(current_stream)
            except Exception as e:
                print(f"Erro ao processar a linha de áudio: {line}\n{e}")
        elif 'Stream #0:0' in line and 'Video:' in line:
            parts = line.split('Video:')
            if len(parts) > 1:
                video_codec = parts[1].strip().split(' ')[0].replace(',', '')
        elif line.startswith('BPS'):
            if current_stream and not current_stream['bitrate']:
                try:
                    bitrate = line.split(':')[1].strip()
                    if bitrate.isdigit():
                        current_stream['bitrate'] = str(int(bitrate) // 1000)
                except:
                    pass

    return video_codec, audio_tracks

def main():
    if len(sys.argv) < 2:
        print("Uso: python process_mkv.py <caminho_do_arquivo_mkv>")
        sys.exit(1)

    mkv_file = sys.argv[1].strip('"')
    if not os.path.exists(mkv_file):
        print(f"Erro: Arquivo {mkv_file} não encontrado.")
        sys.exit(1)

    # Decide se precisa de cópia temporária
    safe_file, is_temp = get_safe_file_path(mkv_file)

    try:
        ffmpeg_output = get_mkv_info(safe_file)
        video_codec, audio_tracks = parse_mkv_info(ffmpeg_output)

        print(f"Codec de Vídeo: {video_codec}")
        if video_codec and video_codec.lower() != "h264":
            print("AVISO: O codec de vídeo não é H264!")

        print("Faixas de Áudio:")
        for i, track in enumerate(audio_tracks):
            print(f"  {i+1}. ID: {track['id']}, Codec: {track['codec']}, Sample Rate: {track['sample_rate']}, Canais: {track['channels']}, Bitrate: {track['bitrate']} kb/s")

        selected_audio_track_index = -1
        if len(audio_tracks) > 1:
            while True:
                try:
                    choice = input("Selecione a faixa de áudio para conversão (número): ")
                    selected_audio_track_index = int(choice) - 1
                    if 0 <= selected_audio_track_index < len(audio_tracks):
                        break
                    else:
                        print("Seleção inválida. Tente novamente.")
                except ValueError:
                    print("Entrada inválida. Por favor, digite um número.")
        elif len(audio_tracks) == 1:
            selected_audio_track_index = 0
            print(f"Faixa de áudio selecionada automaticamente: {audio_tracks[0]['id']}")
        else:
            print("Nenhuma faixa de áudio encontrada.")
            sys.exit(1)

        selected_track = audio_tracks[selected_audio_track_index]
        print(f"Faixa selecionada para conversão: ID {selected_track['id']}, Codec {selected_track['codec']}")

        base, _ = os.path.splitext(mkv_file)
        output_file = f"{base}_converted.mp4"

        ffmpeg_audio_params = []

        num_channels = 2
        if selected_track['channels']:
            if selected_track['channels'].lower() == 'stereo':
                num_channels = 2
            elif selected_track['channels'].lower() == 'mono':
                num_channels = 1
            elif '5.1' in selected_track['channels']:
                num_channels = 6

        if selected_track['codec'].lower() == "flac":
            ffmpeg_audio_params = [
                "-map", f"0:{selected_track['id']}",
                "-c:a", "alac"
            ]
            if selected_track['bitrate']:
                ffmpeg_audio_params.extend(["-b:a", f"{selected_track['bitrate']}k"])
            if selected_track['sample_rate']:
                ffmpeg_audio_params.extend(["-ar", selected_track['sample_rate']])
            ffmpeg_audio_params.extend(["-ac", str(num_channels)])
            print("Convertendo FLAC para ALAC...")
        elif selected_track['codec'].lower() != "aac":
            ffmpeg_audio_params = [
                "-map", f"0:{selected_track['id']}",
                "-c:a", "aac"
            ]
            if selected_track['bitrate']:
                ffmpeg_audio_params.extend(["-b:a", f"{selected_track['bitrate']}k"])
            if selected_track['sample_rate']:
                ffmpeg_audio_params.extend(["-ar", selected_track['sample_rate']])
            ffmpeg_audio_params.extend(["-ac", str(num_channels)])
            print("Convertendo não-AAC para AAC...")
        else:
            print("A faixa de áudio já está no formato AAC ou FLAC. Nenhuma conversão de áudio será feita.")
            ffmpeg_audio_params = [
                "-map", f"0:{selected_track['id']}",
                "-c:a", "copy"
            ]

        final_ffmpeg_command = [
            "C:\\FFmpeg\\bin\\ffmpeg.exe",
            "-i", safe_file,
            "-map", "0:v:0",
            *ffmpeg_audio_params,
            "-c:v", "copy",
            "-map_chapters", "-1",
            "-map_metadata", "-1",
            output_file
        ]

        print(f"Executando FFmpeg: {' '.join(final_ffmpeg_command)}")
        result = subprocess.run(final_ffmpeg_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.stderr:
            print(f"Erro do FFmpeg na conversão: {result.stderr}")
        print("Conversão concluída com sucesso!")

    finally:
        cleanup_temp_file(safe_file, is_temp)

if __name__ == "__main__":
    main()
