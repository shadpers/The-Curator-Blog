# sync_detector_v2.py
import sys
import subprocess
import os
import json
import tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile

try:
    import win32com.client
except ImportError:
    print("Erro: Instale 'pywin32' com: pip install pywin32")
    sys.exit(1)

# Configurações
FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"
EXTRACT_DURATION = 30  # Aumentado para 30s para melhor análise

# Prioridade de idiomas para matching
LANGUAGE_PRIORITY = {
    'ja': ['ja', 'jpn', 'japanese'],
    'en': ['en', 'eng', 'english'],
    'es': ['es', 'spa', 'spanish'],
    'pt': ['pt', 'por', 'portuguese'],
    'fr': ['fr', 'fre', 'french'],
    'de': ['de', 'ger', 'german'],
    'it': ['it', 'ita', 'italian'],
}

sys.stdout.reconfigure(line_buffering=True)

def resolve_lnk_path(file_path):
    """Resolve atalhos .lnk para caminhos reais."""
    try:
        if file_path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            resolved = shortcut.TargetPath
            if not os.path.exists(resolved):
                print(f"Erro: Atalho aponta para arquivo inexistente: {resolved}")
                sys.exit(1)
            print(f"Atalho resolvido: {os.path.basename(resolved)}")
            return resolved
        return file_path
    except Exception as e:
        print(f"Erro ao resolver atalho: {e}")
        sys.exit(1)

def ffprobe_json(file_path):
    """Obtém informações do arquivo via ffprobe."""
    try:
        cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
               "-show_streams", "-show_format", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            print(f"Erro ffprobe: {result.stderr}")
            sys.exit(1)
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Erro ao processar ffprobe: {e}")
        sys.exit(1)

def get_audio_streams(data):
    """Lista streams de áudio com duração robusta."""
    streams = []
    container_duration = float(data.get("format", {}).get("duration", 0))
    
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            # Tenta obter duração de múltiplas fontes
            duration = 0
            if "duration" in s and s["duration"] != "N/A":
                duration = float(s["duration"])
            elif "DURATION" in s.get("tags", {}):
                dur_str = s["tags"]["DURATION"]
                h, m, sec = dur_str.split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(sec)
            elif container_duration > 0:
                duration = container_duration
            
            streams.append({
                "index": s["index"],
                "codec": s.get("codec_name", "unknown"),
                "channels": s.get("channels", 0),
                "sample_rate": s.get("sample_rate", "unknown"),
                "lang": s.get("tags", {}).get("language", "und").lower(),
                "title": s.get("tags", {}).get("title", "Sem título"),
                "duration": duration
            })
    return streams

def normalize_language(lang):
    """Normaliza código de idioma para matching."""
    lang = lang.lower()
    for key, variants in LANGUAGE_PRIORITY.items():
        if lang in variants:
            return key
    return lang

def find_matching_language(bd_streams, web_streams):
    """Encontra o idioma em comum entre BD e WEB."""
    bd_langs = set(normalize_language(s['lang']) for s in bd_streams)
    web_langs = set(normalize_language(s['lang']) for s in web_streams)
    
    # Tenta encontrar match na ordem de prioridade
    for priority_lang in LANGUAGE_PRIORITY.keys():
        if priority_lang in bd_langs and priority_lang in web_langs:
            return priority_lang
    
    # Se não achar, retorna primeiro idioma comum
    common = bd_langs & web_langs
    if common:
        return list(common)[0]
    
    return None

def select_audio_stream(streams, file_type, target_lang=None):
    """Seleciona stream de áudio, priorizando idioma alvo."""
    if not streams:
        print(f"Erro: Nenhuma faixa de áudio em {file_type}")
        sys.exit(1)
    
    print(f"\n=== Faixas de áudio em {file_type} ===")
    for i, s in enumerate(streams, 1):
        dur_str = f"{s['duration']:.1f}s" if s['duration'] > 0 else "N/A"
        print(f"{i}. [{s['lang']}] {s['codec']} {s['channels']}ch - \"{s['title']}\" ({dur_str})")
    
    # Se há idioma alvo, tenta selecionar automaticamente
    if target_lang:
        candidates = [s for s in streams if normalize_language(s['lang']) == target_lang]
        # Filtra commentary/SFX
        main_tracks = [s for s in candidates 
                      if 'commentary' not in s['title'].lower() 
                      and 'sfx' not in s['title'].lower()]
        
        if len(main_tracks) == 1:
            selected = main_tracks[0]
            print(f"✓ Selecionado automaticamente: [{selected['lang']}] {selected['title']}")
            return selected
        elif len(main_tracks) > 1:
            print(f"⚠ Múltiplas faixas {target_lang} encontradas. Escolha manualmente:")
            streams = main_tracks
        elif len(candidates) == 1:
            selected = candidates[0]
            print(f"✓ Selecionado automaticamente: [{selected['lang']}] {selected['title']}")
            return selected
    
    # Seleção manual
    if len(streams) == 1:
        print("✓ Apenas uma faixa disponível, selecionando automaticamente.")
        return streams[0]
    
    while True:
        try:
            choice = int(input(f"Escolha a faixa para {file_type} (1-{len(streams)}): "))
            if 1 <= choice <= len(streams):
                return streams[choice - 1]
        except ValueError:
            pass
        print("Entrada inválida.")

def extract_audio_segment(file_path, stream_index, duration, output_wav):
    """Extrai segmento de áudio para WAV mono."""
    try:
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", file_path,
            "-map", f"0:{stream_index}",
            "-t", str(duration),
            "-ar", "22050",  # 22kHz suficiente para sync (mais rápido)
            "-ac", "1",      # Mono
            "-acodec", "pcm_s16le",
            output_wav
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", 
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode != 0:
            print(f"Erro ao extrair áudio: {result.stderr}")
            sys.exit(1)
        if not os.path.exists(output_wav) or os.path.getsize(output_wav) == 0:
            print(f"Erro: Arquivo {output_wav} vazio ou não criado")
            sys.exit(1)
    except Exception as e:
        print(f"Erro na extração: {e}")
        sys.exit(1)

def trim_silence(audio, sample_rate, threshold_db=-40):
    """Remove silêncio inicial/final do áudio."""
    # Converte threshold dB para amplitude
    threshold = 10 ** (threshold_db / 20)
    
    # Encontra primeiro sample acima do threshold
    mask = np.abs(audio) > threshold
    if not mask.any():
        return audio, 0  # Sem áudio detectável
    
    start_idx = np.argmax(mask)
    
    # Retorna áudio trimado e offset em segundos
    offset_sec = start_idx / sample_rate
    return audio[start_idx:], offset_sec

def find_offset_correlation(audio1, audio2, sample_rate):
    """
    Encontra offset usando correlação cruzada.
    Retorna: (offset_ms, confidence, trimmed_offset1_ms, trimmed_offset2_ms)
    """
    try:
        # Trim silêncio inicial de ambos
        audio1_trimmed, trim_offset1 = trim_silence(audio1, sample_rate)
        audio2_trimmed, trim_offset2 = trim_silence(audio2, sample_rate)
        
        print(f"  Silêncio inicial detectado:")
        print(f"    BD:  {trim_offset1*1000:.1f} ms")
        print(f"    WEB: {trim_offset2*1000:.1f} ms")
        
        # Limita tamanho para análise (primeiros 20s após trim)
        max_samples = int(20 * sample_rate)
        audio1_trimmed = audio1_trimmed[:max_samples]
        audio2_trimmed = audio2_trimmed[:max_samples]
        
        if len(audio1_trimmed) < sample_rate or len(audio2_trimmed) < sample_rate:
            print("Aviso: Áudio muito curto após trim de silêncio")
            return 0, 0, trim_offset1*1000, trim_offset2*1000
        
        # Correlação cruzada
        correlation = signal.correlate(audio1_trimmed, audio2_trimmed, mode='full')
        lags = signal.correlation_lags(len(audio1_trimmed), len(audio2_trimmed), mode='full')
        
        # Encontra pico
        peak_idx = np.argmax(correlation)
        lag = lags[peak_idx]
        
        # Calcula confiança (normalizada)
        confidence = correlation[peak_idx] / (np.sqrt(np.sum(audio1_trimmed**2) * np.sum(audio2_trimmed**2)))
        
        # Offset em ms (positivo = BD começa depois)
        offset_ms = (lag / sample_rate) * 1000
        
        # Adiciona diferença de trim
        total_offset_ms = offset_ms + (trim_offset1 - trim_offset2) * 1000
        
        return total_offset_ms, confidence, trim_offset1*1000, trim_offset2*1000
        
    except Exception as e:
        print(f"Erro na correlação: {e}")
        return 0, 0, 0, 0

def analyze_audio_sync(bd_path, web_path):
    """Analisa sincronização entre BD e WEB via áudio."""
    try:
        print("\n" + "="*70)
        print("🎬 SYNC DETECTOR - Análise de Delay de Áudio")
        print("="*70)
        
        # Resolve atalhos
        bd_path = resolve_lnk_path(bd_path)
        web_path = resolve_lnk_path(web_path)
        
        print(f"\n📀 BD:  {os.path.basename(bd_path)}")
        print(f"🌐 WEB: {os.path.basename(web_path)}")
        
        # Obtém streams
        print("\n⏳ Analisando streams de áudio...")
        bd_data = ffprobe_json(bd_path)
        web_data = ffprobe_json(web_path)
        
        bd_streams = get_audio_streams(bd_data)
        web_streams = get_audio_streams(web_data)
        
        # Encontra idioma em comum
        target_lang = find_matching_language(bd_streams, web_streams)
        if target_lang:
            print(f"\n✓ Idioma comum detectado: {target_lang.upper()}")
        else:
            print("\n⚠ Nenhum idioma em comum. Seleção manual necessária.")
        
        # Seleciona streams
        bd_stream = select_audio_stream(bd_streams, "BD", target_lang)
        web_stream = select_audio_stream(web_streams, "WEB", target_lang)
        
        # Validação
        if normalize_language(bd_stream['lang']) != normalize_language(web_stream['lang']):
            print(f"\n⚠ AVISO: Idiomas diferentes selecionados!")
            print(f"  BD:  {bd_stream['lang']}")
            print(f"  WEB: {web_stream['lang']}")
            resp = input("Deseja continuar mesmo assim? (s/n): ")
            if resp.lower() != 's':
                print("Operação cancelada.")
                sys.exit(0)
        
        print(f"\n⏳ Extraindo primeiros {EXTRACT_DURATION}s de áudio...")
        
        # Extrai segmentos
        with tempfile.TemporaryDirectory() as tmpdir:
            bd_wav = os.path.join(tmpdir, "bd_audio.wav")
            web_wav = os.path.join(tmpdir, "web_audio.wav")
            
            extract_audio_segment(bd_path, bd_stream["index"], EXTRACT_DURATION, bd_wav)
            extract_audio_segment(web_path, web_stream["index"], EXTRACT_DURATION, web_wav)
            
            print("⏳ Analisando correlação de áudio...")
            
            # Carrega áudios
            bd_rate, bd_audio = wavfile.read(bd_wav)
            web_rate, web_audio = wavfile.read(web_wav)
            
            # Normaliza para float
            bd_audio = bd_audio.astype(np.float32) / 32768.0
            web_audio = web_audio.astype(np.float32) / 32768.0
            
            # Calcula offset
            offset_ms, confidence, trim_bd, trim_web = find_offset_correlation(
                bd_audio, web_audio, bd_rate
            )
        
        # Resultados
        print("\n" + "="*70)
        print("📊 RESULTADOS DA ANÁLISE")
        print("="*70)
        
        print(f"\n🎯 Offset detectado: {offset_ms:.1f} ms")
        print(f"📈 Confiança: {confidence:.3f} (quanto mais próximo de 1.0, melhor)")
        
        if confidence < 0.3:
            print("\n⚠ AVISO: Confiança baixa! Possíveis causas:")
            print("  • Áudios muito diferentes (idiomas, mixagens)")
            print("  • Muito ruído/silêncio no início")
            print("  • Edições diferentes entre BD e WEB")
        
        print("\n" + "-"*70)
        if abs(offset_ms) < 10:
            print("✅ Áudios praticamente SINCRONIZADOS (diferença < 10ms)")
            print("   Nenhum ajuste necessário!")
        elif offset_ms > 0:
            print(f"⏩ BD começa {offset_ms:.1f} ms DEPOIS do WEB")
            print(f"   Para sincronizar no MKVToolNix:")
            print(f"   → Adicione -{offset_ms:.1f} ms de delay no áudio do BD")
            print(f"   → OU adicione +{offset_ms:.1f} ms no áudio do WEB")
        else:
            print(f"⏪ WEB começa {abs(offset_ms):.1f} ms DEPOIS do BD")
            print(f"   Para sincronizar no MKVToolNix:")
            print(f"   → Adicione +{abs(offset_ms):.1f} ms de delay no áudio do WEB")
            print(f"   → OU adicione -{abs(offset_ms):.1f} ms no áudio do BD")
        
        print("\n" + "="*70)
        print("✨ Análise concluída!")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Operação cancelada pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro na análise: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    try:
        if len(sys.argv) < 3:
            print("\n" + "="*70)
            print("🎬 SYNC DETECTOR - Detector de Delay de Áudio")
            print("="*70)
            print("\nUso: python sync_detector_v2.py <arquivo_BD> <arquivo_WEB>")
            print("\nArraste os arquivos para o .bat ou execute via linha de comando.")
            print("="*70 + "\n")
            sys.exit(1)
        
        bd_path = sys.argv[1].strip('"')
        web_path = sys.argv[2].strip('"')
        
        analyze_audio_sync(bd_path, web_path)
        
    except KeyboardInterrupt:
        print("\n\n⚠ Operação cancelada.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()