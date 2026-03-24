import sys
import json
import subprocess
import os
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

def get_audio_streams(data):
    try:
        audio_streams = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                lang = stream.get("tags", {}).get("language", "unknown")
                duration = stream.get("duration", None)
                if duration is None:
                    duration = data.get("format", {}).get("duration", "unknown")
                
                audio_streams.append({
                    "index": stream["index"],
                    "lang": lang,
                    "title": stream.get("tags", {}).get("title", "Sem título"),
                    "channels": stream.get("channels", "unknown"),
                    "codec": stream.get("codec_name", "unknown"),
                    "duration": duration
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
            "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate,channel_layout",
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
                "bit_rate": stream.get("bit_rate", None),
                "channel_layout": stream.get("channel_layout", None)
            }
        else:
            return {
                "codec": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": None,
                "channel_layout": None
            }
    except:
        return {
            "codec": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "bit_rate": None,
            "channel_layout": None
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

def format_duration(seconds):
    """Formata duração em segundos para HH:MM:SS.ms"""
    try:
        seconds = float(seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    except:
        return str(seconds)

def sync_audio(reference_file, target_file, script_dir):
    try:
        # Resolve caminhos de atalho .lnk
        reference_file = resolve_lnk_path(reference_file)
        target_file = resolve_lnk_path(target_file)
        
        # Obtém informações dos arquivos
        print("\n===== ANALISANDO ARQUIVO DE REFERÊNCIA =====")
        ref_data = ffprobe_json(reference_file)
        ref_audio_streams = get_audio_streams(ref_data)
        
        if not ref_audio_streams:
            error_msg = "Erro: Não encontrou faixas de áudio no arquivo de referência."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        print(f"Arquivo: {os.path.basename(reference_file)}")
        print("\nFaixas de áudio disponíveis:")
        for i, audio in enumerate(ref_audio_streams, 1):
            duration_str = format_duration(audio['duration']) if audio['duration'] != 'unknown' else 'Desconhecida'
            print(f"{i}. Lang={audio['lang']}, Title=\"{audio['title']}\", Codec={audio['codec']}, Canais={audio['channels']}, Duração={duration_str}")
        
        # Seleciona faixa de referência
        while True:
            try:
                choice = input("\nDigite o número da faixa de REFERÊNCIA: ")
                choice = int(choice)
                if 1 <= choice <= len(ref_audio_streams):
                    ref_audio = ref_audio_streams[choice - 1]
                    break
                else:
                    print(f"Por favor, escolha um número entre 1 e {len(ref_audio_streams)}.")
            except ValueError:
                print("Entrada inválida. Digite um número.")
        
        ref_duration = float(ref_audio['duration']) if ref_audio['duration'] != 'unknown' else None
        if ref_duration is None:
            error_msg = "Erro: Não foi possível determinar a duração da faixa de referência."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        print(f"\n✓ Faixa de referência selecionada: Duração total = {format_duration(ref_duration)}")
        
        # Pergunta sobre silêncio inicial na REFERÊNCIA
        print("\n===== AJUSTE DE SILÊNCIO INICIAL (REFERÊNCIA) =====")
        print("Se houver silêncio no início do áudio de REFERÊNCIA que deve ser")
        print("desconsiderado no cálculo (ex: 1000ms de silêncio no BD),")
        print("digite o valor em milissegundos.")
        print("Pressione ENTER para não descontar nenhum silêncio.")
        
        ref_silence_offset = 0
        while True:
            try:
                silence_input = input("\nSilêncio inicial na REFERÊNCIA (ms): ").strip()
                if silence_input == "":
                    ref_silence_offset = 0
                    break
                else:
                    silence_ms = float(silence_input)
                    if silence_ms < 0:
                        print("O valor deve ser positivo ou zero.")
                        continue
                    if silence_ms >= ref_duration * 1000:
                        print(f"O valor deve ser menor que a duração total ({ref_duration * 1000:.0f}ms).")
                        continue
                    ref_silence_offset = silence_ms / 1000.0  # Converte para segundos
                    break
            except ValueError:
                print("Entrada inválida. Digite um número em milissegundos ou pressione ENTER.")
        
        ref_duration_adjusted = ref_duration - ref_silence_offset
        
        if ref_silence_offset > 0:
            print(f"\n✓ Silêncio descontado: {ref_silence_offset * 1000:.0f}ms")
            print(f"✓ Duração ajustada da REFERÊNCIA: {format_duration(ref_duration_adjusted)} (de {format_duration(ref_duration)})")
        else:
            print(f"\n✓ Nenhum silêncio descontado. Usando duração total: {format_duration(ref_duration)}")
        
        # Obtém informações do arquivo alvo
        print("\n===== ANALISANDO ARQUIVO ALVO =====")
        target_data = ffprobe_json(target_file)
        target_audio_streams = get_audio_streams(target_data)
        
        if not target_audio_streams:
            error_msg = "Erro: Não encontrou faixas de áudio no arquivo alvo."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        print(f"Arquivo: {os.path.basename(target_file)}")
        print("\nFaixas de áudio disponíveis:")
        for i, audio in enumerate(target_audio_streams, 1):
            duration_str = format_duration(audio['duration']) if audio['duration'] != 'unknown' else 'Desconhecida'
            print(f"{i}. Lang={audio['lang']}, Title=\"{audio['title']}\", Codec={audio['codec']}, Canais={audio['channels']}, Duração={duration_str}")
        
        # Seleciona faixa alvo
        while True:
            try:
                choice = input("\nDigite o número da faixa ALVO a converter: ")
                choice = int(choice)
                if 1 <= choice <= len(target_audio_streams):
                    target_audio = target_audio_streams[choice - 1]
                    break
                else:
                    print(f"Por favor, escolha um número entre 1 e {len(target_audio_streams)}.")
            except ValueError:
                print("Entrada inválida. Digite um número.")
        
        target_duration = float(target_audio['duration']) if target_audio['duration'] != 'unknown' else None
        if target_duration is None:
            error_msg = "Erro: Não foi possível determinar a duração da faixa alvo."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        print(f"\n✓ Faixa alvo selecionada: Duração total = {format_duration(target_duration)}")
        
        # Pergunta sobre silêncio inicial no ALVO
        print("\n===== AJUSTE DE SILÊNCIO INICIAL (ALVO) =====")
        print("Se houver silêncio no início do áudio ALVO que deve ser")
        print("desconsiderado no cálculo, digite o valor em milissegundos.")
        print("Pressione ENTER para não descontar nenhum silêncio.")
        
        target_silence_offset = 0
        while True:
            try:
                silence_input = input("\nSilêncio inicial no ALVO (ms): ").strip()
                if silence_input == "":
                    target_silence_offset = 0
                    break
                else:
                    silence_ms = float(silence_input)
                    if silence_ms < 0:
                        print("O valor deve ser positivo ou zero.")
                        continue
                    if silence_ms >= target_duration * 1000:
                        print(f"O valor deve ser menor que a duração total ({target_duration * 1000:.0f}ms).")
                        continue
                    target_silence_offset = silence_ms / 1000.0  # Converte para segundos
                    break
            except ValueError:
                print("Entrada inválida. Digite um número em milissegundos ou pressione ENTER.")
        
        target_duration_adjusted = target_duration - target_silence_offset
        
        if target_silence_offset > 0:
            print(f"\n✓ Silêncio descontado: {target_silence_offset * 1000:.0f}ms")
            print(f"✓ Duração ajustada do ALVO: {format_duration(target_duration_adjusted)} (de {format_duration(target_duration)})")
        else:
            print(f"\n✓ Nenhum silêncio descontado. Usando duração total: {format_duration(target_duration)}")
        
        # Calcula fator de expansão com durações ajustadas
        expansion_factor = ref_duration_adjusted / target_duration_adjusted
        
        print(f"\n===== CÁLCULO DO FATOR DE EXPANSÃO =====")
        if ref_silence_offset > 0 or target_silence_offset > 0:
            print(f"Duração REFERÊNCIA (original): {format_duration(ref_duration)} ({ref_duration:.6f}s)")
            if ref_silence_offset > 0:
                print(f"  - Silêncio descontado: {ref_silence_offset * 1000:.0f}ms")
                print(f"  = Duração ajustada: {format_duration(ref_duration_adjusted)} ({ref_duration_adjusted:.6f}s)")
            print(f"\nDuração ALVO (original):       {format_duration(target_duration)} ({target_duration:.6f}s)")
            if target_silence_offset > 0:
                print(f"  - Silêncio descontado: {target_silence_offset * 1000:.0f}ms")
                print(f"  = Duração ajustada: {format_duration(target_duration_adjusted)} ({target_duration_adjusted:.6f}s)")
        else:
            print(f"Duração REFERÊNCIA: {format_duration(ref_duration_adjusted)} ({ref_duration_adjusted:.6f}s)")
            print(f"Duração ALVO:       {format_duration(target_duration_adjusted)} ({target_duration_adjusted:.6f}s)")
        
        print(f"\nFator de expansão: {expansion_factor:.10f}")
        print(f"Duração final do áudio convertido: {format_duration(target_duration_adjusted * expansion_factor)}")
        
        # Preparar conversão
        stream_index = target_audio['index']
        audio_info = get_audio_info(target_file, stream_index)
        codec = audio_info['codec']
        sample_rate = audio_info['sample_rate']
        bit_rate = audio_info['bit_rate']
        lang = target_audio['lang']
        title = target_audio['title']
        channels = audio_info['channels']
        
        base_name = os.path.splitext(os.path.basename(target_file))[0]
        ext_out = get_extension_for_codec(codec)
        output_file = os.path.join(script_dir, f"{base_name}_track{stream_index}_synced.{ext_out}")
        
        atempo = 1.0 / expansion_factor
        atempo_filter = build_atempo_filter(atempo)
        
        # Determina bitrate
        if bit_rate:
            bitrate_str = f"{int(int(bit_rate) / 1000)}k"
        else:
            bitrate_str = "192k"  # Padrão caso não detecte
        
        print(f"\n===== CONVERTENDO =====")
        print(f"Arquivo: {os.path.basename(target_file)}")
        print(f"Faixa: {stream_index} ({lang}, {codec})")
        print(f"Sample Rate: {sample_rate} Hz")
        print(f"Bitrate: {bitrate_str}")
        print(f"Canais: {channels}")
        print(f"Fator de tempo (atempo): {atempo:.10f}")
        if ref_silence_offset > 0:
            print(f"Delay a ser adicionado: {ref_silence_offset * 1000:.0f}ms")
        print(f"Arquivo de saída: {output_file}")
        print("Aguarde...\n")
        
        # Comando ffmpeg - mantém mesmo formato, bitrate e qualidade
        # Se houver delay, aplica adelay DEPOIS do atempo
        if ref_silence_offset > 0:
            delay_ms = int(ref_silence_offset * 1000)
            filter_chain = f"{atempo_filter},aresample={sample_rate},adelay={delay_ms}|{delay_ms}"
        else:
            filter_chain = f"{atempo_filter},aresample={sample_rate}"
        
        cmd = [
            FFMPEG_PATH,
            "-i", target_file,
            "-map", f"0:{stream_index}",
            "-af", filter_chain,
            "-c:a", codec,
            "-b:a", bitrate_str,
            "-ar", sample_rate,
        ]
        
        # Adiciona channel layout se disponível
        if audio_info['channel_layout']:
            cmd.extend(["-channel_layout", audio_info['channel_layout']])
        
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
        
        print(f"✓ Conversão concluída com sucesso!")
        print(f"✓ Codec: {codec}")
        print(f"✓ Bitrate: {bitrate_str}")
        if ref_silence_offset > 0:
            print(f"✓ Delay automático adicionado: {ref_silence_offset * 1000:.0f}ms")
        print(f"✓ Arquivo temporário salvo em: {output_file}")
        
        # Pergunta sobre delay extra
        print("\n===== DELAY EXTRA (OPCIONAL) =====")
        print("Deseja adicionar um delay extra ao áudio?")
        print("Digite o valor em milissegundos ou pressione ENTER para finalizar.")
        
        extra_delay_ms = 0
        while True:
            try:
                delay_input = input("\nDelay extra (ms): ").strip()
                if delay_input == "":
                    # Sem delay extra, apenas renomeia o arquivo
                    print(f"\n✓ Nenhum delay extra adicionado.")
                    print(f"✓ Arquivo final: {output_file}\n")
                    return
                else:
                    extra_delay_ms = float(delay_input)
                    if extra_delay_ms < 0:
                        print("O valor deve ser positivo ou zero.")
                        continue
                    break
            except ValueError:
                print("Entrada inválida. Digite um número em milissegundos ou pressione ENTER.")
        
        # Aplica delay extra
        print(f"\n===== APLICANDO DELAY EXTRA =====")
        print(f"Adicionando {extra_delay_ms:.0f}ms de delay extra...")
        
        base_name = os.path.splitext(os.path.basename(target_file))[0]
        ext_out = get_extension_for_codec(codec)
        final_output = os.path.join(script_dir, f"{base_name}_track{stream_index}_synced_final.{ext_out}")
        
        # Calcula delay total
        total_delay = int((ref_silence_offset * 1000) + extra_delay_ms)
        
        cmd_delay = [
            FFMPEG_PATH,
            "-i", output_file,
            "-af", f"adelay={int(extra_delay_ms)}|{int(extra_delay_ms)}",
            "-c:a", codec,
            "-b:a", bitrate_str,
            "-ar", sample_rate,
        ]
        
        if audio_info['channel_layout']:
            cmd_delay.extend(["-channel_layout", audio_info['channel_layout']])
        
        cmd_delay.extend([
            "-metadata:s:a:0", f"language={lang}",
            "-metadata:s:a:0", f"title={title}",
            final_output,
            "-y"
        ])
        
        result_delay = subprocess.run(cmd_delay, capture_output=True, text=True, encoding="utf-8")
        
        if result_delay.returncode != 0:
            print(f"ERRO ao aplicar delay extra: {result_delay.stderr}")
            print(f"Arquivo original mantido em: {output_file}")
            sys.exit(1)
        
        # Remove arquivo temporário
        try:
            os.remove(output_file)
        except:
            pass
        
        print(f"\n✓ Delay extra aplicado com sucesso!")
        print(f"✓ Delay automático: {ref_silence_offset * 1000:.0f}ms")
        print(f"✓ Delay extra: {extra_delay_ms:.0f}ms")
        print(f"✓ Delay TOTAL: {total_delay:.0f}ms")
        print(f"✓ Pronto para muxar! O delay total já está aplicado no áudio.")
        print(f"✓ Arquivo final salvo em: {final_output}\n")
    
    except Exception as e:
        error_msg = f"Erro: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def main():
    try:
        if len(sys.argv) < 3:
            error_msg = "Uso: python sync_audio_duration.py <arquivo_referencia> <arquivo_alvo>"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        
        reference_path = sys.argv[1]
        target_path = sys.argv[2]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"Arquivo de referência: {reference_path}")
        print(f"Arquivo alvo: {target_path}")
        
        sync_audio(reference_path, target_path, script_dir)
    
    except Exception as e:
        error_msg = f"Erro no script: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()