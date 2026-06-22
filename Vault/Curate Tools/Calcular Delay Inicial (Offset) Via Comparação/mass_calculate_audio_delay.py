# mass_calculate_audio_delay.py
# Versão em lote: compara episódios de mesmo número entre duas pastas
import sys
import subprocess
import os
import re
import json
import tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile

try:
    import win32com.client
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# ── Configurações ─────────────────────────────────────────────────────────────
FFPROBE_PATH  = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH   = r"C:\FFmpeg\bin\ffmpeg.exe"
EXTRACT_DURATION = 30   # segundos extraídos para análise

VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.m2ts', '.ts', '.mov', '.wmv'}

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

# ── Utilitários ───────────────────────────────────────────────────────────────

def resolve_lnk(path):
    """Resolve atalhos .lnk (Windows) para o caminho real."""
    if not HAS_WIN32:
        return path
    try:
        if path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            resolved = shell.CreateShortCut(path).TargetPath
            if not os.path.exists(resolved):
                print(f"  ⚠ Atalho aponta para inexistente: {resolved}")
                return None
            return resolved
    except Exception:
        pass
    return path


def extract_episode_number(filename):
    """
    Extrai o número de episódio de um nome de arquivo.
    Tenta vários padrões em ordem decrescente de especificidade.
    Retorna int ou None.
    """
    name = os.path.splitext(os.path.basename(filename))[0]

    patterns = [
        r'[Ss]\d+[Ee](\d+)',                                       # S01E01
        r'[-_ ](\d{2,3})[-_ \[\(]',                               # ' - 002 [' ou ' - 002 ('
        r'[-_ ](\d{2,3})$',                                        # termina em ' - 001'
        r'(\d{2,3})[vV]\d',                                        # 001v2
        r'(?:^|[\s\[\(#-])Ep?\.?\s*(\d{2,3})(?:[\s\]\)_.-]|$)',  # EP01/Ep.02 (restrito)
        r'\b(\d{2,3})\b',                                          # fallback
    ]

    for pat in patterns:
        m = re.search(pat, name)
        if m:
            return int(m.group(1))
    return None


def list_video_files(folder):
    """Lista arquivos de vídeo numa pasta, mapeados por número de episódio."""
    result = {}
    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in VIDEO_EXTENSIONS:
            continue
        ep_num = extract_episode_number(fname)
        if ep_num is None:
            print(f"  ⚠ Não foi possível extrair número de: {fname} (ignorado)")
            continue
        if ep_num in result:
            print(f"  ⚠ Número {ep_num:03d} duplicado — '{fname}' ignorado (já existe '{result[ep_num]}')")
            continue
        result[ep_num] = os.path.join(folder, fname)
    return result


def match_episodes(bd_folder, web_folder):
    """
    Cruza os episódios das duas pastas pelo número.
    Retorna lista de (ep_num, bd_path, web_path) ordenada.
    Reporta os que ficaram sem par.
    """
    bd_map  = list_video_files(bd_folder)
    web_map = list_video_files(web_folder)

    common  = sorted(set(bd_map) & set(web_map))
    only_bd = sorted(set(bd_map) - set(web_map))
    only_web = sorted(set(web_map) - set(bd_map))

    if only_bd:
        print(f"\n  ⚠ Episódios APENAS na pasta BD (sem par WEB): {[f'{n:03d}' for n in only_bd]}")
    if only_web:
        print(f"  ⚠ Episódios APENAS na pasta WEB (sem par BD): {[f'{n:03d}' for n in only_web]}")

    return [(n, bd_map[n], web_map[n]) for n in common]

# ── FFprobe / seleção de stream ───────────────────────────────────────────────

def ffprobe_json(file_path):
    cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
           "-show_streams", "-show_format", file_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe falhou: {r.stderr[:200]}")
    return json.loads(r.stdout)


def get_audio_streams(data):
    container_dur = float(data.get("format", {}).get("duration", 0))
    streams = []
    for s in data.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        dur = 0
        if "duration" in s and s["duration"] != "N/A":
            dur = float(s["duration"])
        elif "DURATION" in s.get("tags", {}):
            h, m, sec = s["tags"]["DURATION"].split(":")
            dur = int(h)*3600 + int(m)*60 + float(sec)
        elif container_dur > 0:
            dur = container_dur
        streams.append({
            "index":       s["index"],
            "codec":       s.get("codec_name", "?"),
            "channels":    s.get("channels", 0),
            "sample_rate": s.get("sample_rate", "?"),
            "lang":        s.get("tags", {}).get("language", "und").lower(),
            "title":       s.get("tags", {}).get("title", ""),
            "duration":    dur,
        })
    return streams


def normalize_lang(lang):
    lang = lang.lower()
    for key, variants in LANGUAGE_PRIORITY.items():
        if lang in variants:
            return key
    return lang


def find_common_lang(bd_streams, web_streams):
    bd_langs  = {normalize_lang(s['lang']) for s in bd_streams}
    web_langs = {normalize_lang(s['lang']) for s in web_streams}
    for prio in LANGUAGE_PRIORITY:
        if prio in bd_langs and prio in web_langs:
            return prio
    common = bd_langs & web_langs
    return list(common)[0] if common else None


def select_best_stream_auto(streams, target_lang):
    """
    Seleciona a faixa de áudio automaticamente (sem prompt).
    Critérios: idioma alvo → descarta commentary/sfx → mais canais.
    Retorna (stream, aviso_str).
    """
    if not streams:
        return None, "nenhuma faixa disponível"

    pool = streams
    if target_lang:
        candidates = [s for s in streams if normalize_lang(s['lang']) == target_lang]
        if candidates:
            pool = candidates

    # Remove commentary / SFX
    main = [s for s in pool
            if 'commentary' not in s['title'].lower()
            and 'sfx' not in s['title'].lower()]
    if main:
        pool = main

    # Pega o de maior número de canais (áudio principal)
    best = max(pool, key=lambda s: s['channels'])
    note = f"[{best['lang']}] {best['codec']} {best['channels']}ch" + (f' "{best["title"]}"' if best['title'] else "")
    return best, note

# ── Extração e correlação ─────────────────────────────────────────────────────

def extract_audio(file_path, stream_index, duration, output_wav):
    cmd = [
        FFMPEG_PATH, "-y",
        "-i", file_path,
        "-map", f"0:{stream_index}",
        "-t", str(duration),
        "-ar", "22050",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        output_wav,
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", creationflags=flags)
    if r.returncode != 0 or not os.path.exists(output_wav) or os.path.getsize(output_wav) == 0:
        raise RuntimeError(f"ffmpeg falhou: {r.stderr[:200]}")


def trim_silence(audio, sample_rate, threshold_db=-40):
    threshold = 10 ** (threshold_db / 20)
    mask = np.abs(audio) > threshold
    if not mask.any():
        return audio, 0
    start = int(np.argmax(mask))
    return audio[start:], start / sample_rate


def correlate_offset(audio1, audio2, sample_rate):
    """Retorna (offset_ms, confidence)."""
    a1, t1 = trim_silence(audio1, sample_rate)
    a2, t2 = trim_silence(audio2, sample_rate)

    max_s = int(20 * sample_rate)
    a1 = a1[:max_s]
    a2 = a2[:max_s]

    if len(a1) < sample_rate or len(a2) < sample_rate:
        return 0.0, 0.0

    corr = signal.correlate(a1, a2, mode='full')
    lags = signal.correlation_lags(len(a1), len(a2), mode='full')
    peak = int(np.argmax(corr))
    lag  = lags[peak]

    norm = np.sqrt(np.sum(a1**2) * np.sum(a2**2))
    conf = float(corr[peak] / norm) if norm > 0 else 0.0

    offset_ms = (lag / sample_rate) * 1000
    trim_diff  = (t1 - t2) * 1000
    return offset_ms + trim_diff, conf

# ── Análise de um par ─────────────────────────────────────────────────────────

def analyze_pair(ep_num, bd_path, web_path):
    """
    Analisa um par de episódios completamente automático.
    Retorna dict com os resultados ou 'error'.
    """
    result = {
        "ep":        ep_num,
        "bd_name":   os.path.basename(bd_path),
        "web_name":  os.path.basename(web_path),
        "offset_ms": None,
        "confidence": None,
        "bd_track":  "",
        "web_track": "",
        "warning":   "",
        "error":     "",
    }

    try:
        bd_data  = ffprobe_json(bd_path)
        web_data = ffprobe_json(web_path)

        bd_streams  = get_audio_streams(bd_data)
        web_streams = get_audio_streams(web_data)

        if not bd_streams:
            result["error"] = "BD sem faixas de áudio"
            return result
        if not web_streams:
            result["error"] = "WEB sem faixas de áudio"
            return result

        target_lang = find_common_lang(bd_streams, web_streams)

        bd_stream,  bd_note  = select_best_stream_auto(bd_streams,  target_lang)
        web_stream, web_note = select_best_stream_auto(web_streams, target_lang)

        result["bd_track"]  = bd_note
        result["web_track"] = web_note

        if normalize_lang(bd_stream['lang']) != normalize_lang(web_stream['lang']):
            result["warning"] += "idiomas diferentes; "

        with tempfile.TemporaryDirectory() as tmp:
            bd_wav  = os.path.join(tmp, "bd.wav")
            web_wav = os.path.join(tmp, "web.wav")

            extract_audio(bd_path,  bd_stream["index"],  EXTRACT_DURATION, bd_wav)
            extract_audio(web_path, web_stream["index"], EXTRACT_DURATION, web_wav)

            bd_rate,  bd_audio  = wavfile.read(bd_wav)
            web_rate, web_audio = wavfile.read(web_wav)

            bd_audio  = bd_audio.astype(np.float32)  / 32768.0
            web_audio = web_audio.astype(np.float32) / 32768.0

            offset_ms, conf = correlate_offset(bd_audio, web_audio, bd_rate)

        result["offset_ms"]   = offset_ms
        result["confidence"]  = conf

        if conf < 0.3:
            result["warning"] += "confiança baixa"

    except Exception as e:
        result["error"] = str(e)[:120]

    return result

# ── Tabela de resultados ──────────────────────────────────────────────────────

def format_offset(offset_ms):
    if offset_ms is None:
        return "N/A"
    sign = "+" if offset_ms >= 0 else ""
    return f"{sign}{offset_ms:.1f} ms"


def confidence_tag(conf):
    if conf is None:
        return ""
    if conf >= 0.6:
        return "✅"
    if conf >= 0.3:
        return "⚠"
    return "❌"


def sync_verdict(offset_ms):
    if offset_ms is None:
        return ""
    if abs(offset_ms) < 10:
        return "✅ Sincronizado"
    if offset_ms > 0:
        return f"BD +{offset_ms:.0f} ms atrás"
    return f"WEB +{abs(offset_ms):.0f} ms atrás"


def print_summary(results):
    # Larguras
    W_EP   = 4
    W_NAME = 28
    W_OFF  = 11
    W_CONF = 8
    W_VERD = 22
    W_WARN = 24

    sep   = "─"
    h_sep = "═"

    def row(*cols, widths, char="│"):
        parts = []
        for val, w in zip(cols, widths):
            parts.append(f" {str(val):<{w}} ")
        return char + char.join(parts) + char

    widths = [W_EP, W_NAME, W_NAME, W_OFF, W_CONF, W_VERD, W_WARN]
    total  = sum(w + 3 for w in widths) + 1

    header = row("Ep", "Arquivo BD", "Arquivo WEB",
                 "Offset", "Conf.", "Diagnóstico", "Avisos",
                 widths=widths, char="║")
    h_line = "╔" + "╦".join(h_sep*(w+2) for w in widths) + "╗"
    m_line = "╠" + "╬".join(h_sep*(w+2) for w in widths) + "╣"
    s_line = "├" + "┼".join(sep*(w+2) for w in widths) + "┤"
    b_line = "╚" + "╩".join(h_sep*(w+2) for w in widths) + "╝"

    print("\n")
    print("═"*total)
    print("  📊  RESUMO DA ANÁLISE EM LOTE")
    print("═"*total)
    print(h_line)
    print(header)
    print(m_line)

    ok_count  = 0
    err_count = 0

    for i, r in enumerate(results):
        if i > 0:
            print(s_line)

        ep_str   = f"{r['ep']:03d}"
        bd_name  = r['bd_name'][:W_NAME]
        web_name = r['web_name'][:W_NAME]

        if r["error"]:
            err_count += 1
            print(row(ep_str, bd_name, web_name,
                      "ERRO", "", r["error"][:W_VERD], "",
                      widths=widths, char="│"))
        else:
            ok_count += 1
            conf_str = f"{r['confidence']:.3f} {confidence_tag(r['confidence'])}" if r['confidence'] is not None else "N/A"
            print(row(
                ep_str,
                bd_name,
                web_name,
                format_offset(r['offset_ms']),
                conf_str[:W_CONF],
                sync_verdict(r['offset_ms'])[:W_VERD],
                r['warning'][:W_WARN],
                widths=widths, char="│"
            ))

    print(b_line)
    print(f"\n  Total: {len(results)} pares  |  ✅ OK: {ok_count}  |  ❌ Erros: {err_count}")
    print("═"*total)


def print_mkvmerge_commands(results):
    """Imprime os comandos --sync sugeridos para casos com offset relevante."""
    relevant = [r for r in results
                if r["offset_ms"] is not None and abs(r["offset_ms"]) >= 10]
    if not relevant:
        print("\n✅ Todos os episódios estão sincronizados (offset < 10 ms). Nenhum ajuste necessário.")
        return

    print("\n")
    print("═"*70)
    print("  🔧  SUGESTÕES DE AJUSTE (mkvmerge --sync)")
    print("═"*70)
    print("  Referência: aplicar delay no áudio do WEB para alinhar ao BD.")
    print()

    for r in relevant:
        if r["error"]:
            continue
        offset = r["offset_ms"]
        # Se BD está atrasado em relação ao WEB (offset > 0),
        # o áudio WEB precisa de delay negativo para compensar.
        # Convenção: offset positivo = BD começa depois = WEB está adiantado.
        web_delay = round(-offset)
        bd_delay  = round(offset)

        print(f"  Ep {r['ep']:03d} — {r['bd_name']}")
        print(f"    Offset: {format_offset(offset)}  |  Confiança: {r['confidence']:.3f}")

        # Identifica índice de stream (informativo)
        print(f"    Opção A → delay no áudio WEB:  --sync <índice_áudio_web>:{web_delay}")
        print(f"    Opção B → delay no áudio BD:   --sync <índice_áudio_bd>:{bd_delay}")
        print()

    print("  ℹ  Substitua <índice_áudio_xxx> pelo índice real da faixa no mkvmerge.")
    print("═"*70)

# ── Ponto de entrada ──────────────────────────────────────────────────────────

def main():
    print()
    print("═"*70)
    print("  🎬  SYNC DETECTOR MASS — Análise em Lote de Delay de Áudio")
    print("═"*70)

    if len(sys.argv) < 3:
        print("\nUso: python mass_calculate_audio_delay.py <pasta_BD> <pasta_WEB>")
        print("\nArraste as duas pastas para o .bat ou execute via linha de comando.")
        print("═"*70 + "\n")
        sys.exit(1)

    bd_folder  = sys.argv[1].strip('"').strip("'")
    web_folder = sys.argv[2].strip('"').strip("'")

    # Resolve atalhos
    if HAS_WIN32:
        bd_folder  = resolve_lnk(bd_folder)  or bd_folder
        web_folder = resolve_lnk(web_folder) or web_folder

    # Valida pastas
    if not os.path.isdir(bd_folder):
        print(f"\n❌ Pasta BD não encontrada: {bd_folder}")
        sys.exit(1)
    if not os.path.isdir(web_folder):
        print(f"\n❌ Pasta WEB não encontrada: {web_folder}")
        sys.exit(1)

    print(f"\n  📀 BD:  {bd_folder}")
    print(f"  🌐 WEB: {web_folder}")

    # Pareia episódios
    print("\n⏳ Relacionando episódios...")
    pairs = match_episodes(bd_folder, web_folder)

    if not pairs:
        print("\n❌ Nenhum par de episódios encontrado. Verifique os nomes dos arquivos.")
        sys.exit(1)

    print(f"\n✓ {len(pairs)} par(es) encontrado(s):")
    for ep, bd, web in pairs:
        print(f"    Ep {ep:03d}: {os.path.basename(bd)}  ←→  {os.path.basename(web)}")

    # Analisa cada par
    print("\n" + "─"*70)
    results = []
    for i, (ep_num, bd_path, web_path) in enumerate(pairs, 1):
        print(f"\n[{i}/{len(pairs)}] Ep {ep_num:03d} — {os.path.basename(bd_path)}")
        print(f"         ←→   {os.path.basename(web_path)}")
        r = analyze_pair(ep_num, bd_path, web_path)
        results.append(r)
        if r["error"]:
            print(f"  ❌ Erro: {r['error']}")
        else:
            print(f"  ✓ Offset: {format_offset(r['offset_ms'])}  |  "
                  f"Confiança: {r['confidence']:.3f} {confidence_tag(r['confidence'])}")
            if r["warning"]:
                print(f"  ⚠ {r['warning']}")

    # Sumário final
    print_summary(results)
    print_mkvmerge_commands(results)

    print("\n✨ Análise concluída!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Operação cancelada pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
