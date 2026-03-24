import sys
import json
import subprocess
import os

sys.stdout.reconfigure(line_buffering=True)

FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG_PATH  = r"C:\FFmpeg\bin\ffmpeg.exe"

# ─────────────────────────────────────────────
#  Utilitários
# ─────────────────────────────────────────────

def get_audio_streams(file_path):
    """Retorna lista de streams de áudio do arquivo."""
    cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json", "-show_streams", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    return [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

def get_audio_info(file_path, stream_index):
    """Obtém informações detalhadas de uma faixa específica."""
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
        return None
    data = json.loads(result.stdout)
    return data["streams"][0] if data.get("streams") else None

def get_stream_bitrate(file_path, stream_index, channels):
    """
    Tenta obter o bitrate real do stream via ffprobe com 3 estrategias:
      1. Tag BPS nos metadados do stream (MKV/Opus — valor exato gravado pelo mkvmerge)
      2. bit_rate do proprio stream (disponivel em alguns containers)
      3. bit_rate do container inteiro (valido para arquivos de audio puro, ex: M4A com 1 stream)
    So usa fallback por canais se nenhuma estrategia retornar valor plausivel.
    """
    # ── Estrategia 1: tag BPS (MKV grava esse valor com precisao) ────────────
    cmd = [
        FFPROBE_PATH, "-v", "quiet",
        "-select_streams", f"{stream_index}",
        "-show_entries", "stream_tags=BPS",
        "-print_format", "json",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            bps = int(streams[0].get("tags", {}).get("BPS") or 0)
            if bps >= 32000:
                return bps

    # ── Estrategia 2: bit_rate do stream ─────────────────────────────────────
    cmd = [
        FFPROBE_PATH, "-v", "quiet",
        "-select_streams", f"{stream_index}",
        "-show_entries", "stream=bit_rate",
        "-print_format", "json",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            br = int(streams[0].get("bit_rate") or 0)
            if br >= 32000:
                return br

    # ── Estrategia 3: bit_rate do container (M4A/audio puro de 1 stream) ─────
    cmd = [
        FFPROBE_PATH, "-v", "quiet",
        "-show_entries", "format=bit_rate",
        "-print_format", "json",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        data = json.loads(result.stdout)
        br = int(data.get("format", {}).get("bit_rate") or 0)
        if br >= 32000:
            print(f"  Info: bitrate lido do container: {br//1000}k")
            return br

    # ── Fallback por canais ───────────────────────────────────────────────────
    fallback = 192000 if int(channels) <= 2 else 384000
    print(f"  Aviso: bitrate nao detectado, usando fallback {fallback//1000}k ({channels}ch)")
    return fallback

def stream_signature(stream):
    """Retorna tupla (lang, codec) para comparação entre arquivos."""
    lang  = stream.get("tags", {}).get("language", "unknown")
    codec = stream.get("codec_name", "unknown")
    return (lang, codec)

def build_atempo_filter(stretch_factor):
    """Constrói filtro atempo encadeado (FFmpeg limita cada estágio a 0.5-2.0)."""
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

def parse_track_selection(input_str, max_tracks):
    """Parseia '1,3' -> [1, 3]. Retorna lista ordenada de números 1-based."""
    selected = []
    for part in input_str.strip().split(","):
        part = part.strip()
        try:
            num = int(part)
            if 1 <= num <= max_tracks:
                if num not in selected:
                    selected.append(num)
            else:
                print(f"  Aviso: faixa {num} fora do intervalo (1-{max_tracks}), ignorada.")
        except ValueError:
            print(f"  Aviso: '{part}' nao e um numero valido, ignorado.")
    return sorted(selected)

def format_tag(value, unit="ms"):
    """Formata valor numerico para nome de arquivo (ex: p100ms, n500ms, 0ms)."""
    if value > 0:
        return f"p{value:.0f}{unit}"
    elif value < 0:
        return f"n{abs(value):.0f}{unit}"
    else:
        return f"0{unit}"


# ─────────────────────────────────────────────
#  Validacao em massa
# ─────────────────────────────────────────────

def validate_batch(file_list):
    """
    Verifica se todos os arquivos têm a mesma quantidade e disposição de faixas.
    Retorna (streams_do_primeiro, None) se OK, ou (None, mensagem_erro).
    """
    reference_file    = file_list[0]
    reference_streams = get_audio_streams(reference_file)

    if reference_streams is None:
        return None, f"Nao foi possivel ler streams de: {reference_file}"

    reference_sigs = [stream_signature(s) for s in reference_streams]

    print(f"\nReferencia: {os.path.basename(reference_file)}")
    print(f"Faixas de audio: {len(reference_streams)}")
    for i, sig in enumerate(reference_sigs, 1):
        print(f"  {i}. lang={sig[0]}, codec={sig[1]}")

    errors = []
    for f in file_list[1:]:
        streams = get_audio_streams(f)
        if streams is None:
            errors.append(f"  x Nao foi possivel ler: {os.path.basename(f)}")
            continue
        sigs = [stream_signature(s) for s in streams]
        if sigs != reference_sigs:
            errors.append(
                f"  x {os.path.basename(f)}: faixas divergem\n"
                f"     Esperado  : {reference_sigs}\n"
                f"     Encontrado: {sigs}"
            )

    if errors:
        return reference_streams, "Inconsistencias encontradas:\n" + "\n".join(errors)

    return reference_streams, None


# ─────────────────────────────────────────────
#  Coleta de parametros (interativa, uma vez)
# ─────────────────────────────────────────────

def collect_params(audio_streams):
    """Pergunta ao usuario faixas, stretch, delay e fades. Retorna dict."""

    print("\n===== FAIXAS DE AUDIO =====")
    for i, s in enumerate(audio_streams, 1):
        lang  = s.get("tags", {}).get("language", "unknown")
        title = s.get("tags", {}).get("title", "Sem titulo")
        codec = s.get("codec_name", "unknown")
        print(f"{i}. Lang={lang}, Title=\"{title}\", Codec={codec}")

    while True:
        raw = input("\nNumero(s) da(s) faixa(s) (ex: 1 ou 1,3): ")
        selected_nums = parse_track_selection(raw, len(audio_streams))
        if selected_nums:
            print(f"Faixas selecionadas: {', '.join(str(n) for n in selected_nums)}")
            break
        print(f"Selecione ao menos uma faixa valida entre 1 e {len(audio_streams)}.")

    # ── Idiomas das faixas (somente para und/unknown) ────────────────────────
    UNDEFINED = {"und", "unknown"}
    track_langs = {}
    faixas_sem_lang = [n for n in selected_nums
                       if audio_streams[n - 1].get("tags", {}).get("language", "unknown").lower() in UNDEFINED]

    if faixas_sem_lang:
        print("\n===== IDIOMAS DAS FAIXAS =====")
        print("Codigo ISO 639-2/B de 3 letras (ex: fre, por, jpn, spa, eng).")
        print("Enter = manter 'und'.")
        for n in faixas_sem_lang:
            raw_lang = input(f"  Faixa {n} [und]: ").strip().lower()
            if raw_lang:
                track_langs[n] = raw_lang

    # ── Titulos personalizados por faixa ──────────────────────────────────────
    print("\n===== TITULOS DAS FAIXAS =====")
    print("Digite o titulo para cada faixa (Enter = manter titulo original).")
    print("Exemplos: Japanese | Brazilian Portuguese | Spanish (Latin)")
    track_titles = {}
    for n in selected_nums:
        s = audio_streams[n - 1]
        original_title = s.get("tags", {}).get("title", "")
        lang           = s.get("tags", {}).get("language", "unknown")
        if original_title:
            prompt = f"  Faixa {n} ({lang}) [atual: \"{original_title}\"]: "
        else:
            prompt = f"  Faixa {n} ({lang}) [sem titulo]: "
        user_input = input(prompt).strip()
        # Preserva o titulo original se o usuario nao digitar nada
        track_titles[n] = user_input if user_input else original_title

    print("\n===== FORMATO DE SAIDA =====")
    print("1. Manter original (AAC/AC3 -> MKA)")
    print("2. Lossless (FLAC) - Recomendado para curadoria/BD")
    while True:
        try:
            out_format_choice = int(input("\nEscolha o formato (1 ou 2): "))
            if out_format_choice in [1, 2]:
                break
            print("Escolha 1 ou 2.")
        except ValueError:
            print("Digite um numero valido.")

    print("\n===== METODO DE ENTRADA =====")
    print("1. Fator de Stretch (ex: 1.001102)")
    print("2. Fator FFmpeg atempo (ex: 0.95878663)")
    while True:
        try:
            method = int(input("\nEscolha o metodo (1 ou 2): "))
            if method in [1, 2]:
                break
            print("Escolha 1 ou 2.")
        except ValueError:
            print("Digite um numero valido.")

    if method == 1:
        while True:
            try:
                stretch = float(input("\nFator de stretch (ex: 1.001102): "))
                if stretch > 0:
                    atempo_value = 1.0 / stretch
                    print(f"-> Fator FFmpeg equivalente: atempo={atempo_value:.8f}")
                    break
                print("O fator deve ser maior que zero.")
            except ValueError:
                print("Digite um numero valido.")
    else:
        while True:
            try:
                atempo_value = float(input("\nFator FFmpeg atempo (ex: 0.95878663): "))
                if atempo_value > 0:
                    stretch = 1.0 / atempo_value
                    print(f"-> Fator de Stretch equivalente: {stretch:.8f}")
                    break
                print("O fator deve ser maior que zero.")
            except ValueError:
                print("Digite um numero valido.")

    print("\nDelay no inicio em ms.")
    print("  Positivo (ex: 100)  -> adiciona silencio no inicio")
    print("  Negativo (ex: -500) -> corta o inicio do audio (nao considerado no stretch)")
    while True:
        try:
            delay_ms = float(input("Delay (ms): "))
            break
        except ValueError:
            print("Digite um numero valido.")

    while True:
        try:
            mute_in_ms = float(input("\nMute inicio em ms (0 = sem mute): "))
            if mute_in_ms >= 0:
                break
            print("O mute deve ser >= 0.")
        except ValueError:
            print("Digite um numero valido.")

    while True:
        try:
            fade_in_ms = float(input("Fade IN apos mute em ms (0 = sem fade): "))
            if fade_in_ms >= 0:
                break
            print("O fade in deve ser >= 0.")
        except ValueError:
            print("Digite um numero valido.")

    while True:
        try:
            fade_out_ms = float(input("Fade OUT em ms (0 = sem fade): "))
            if fade_out_ms >= 0:
                break
            print("O fade out deve ser >= 0.")
        except ValueError:
            print("Digite um numero valido.")

    return {
        "selected_nums": selected_nums,
        "track_titles":  track_titles,
        "track_langs":   track_langs,
        "out_format":    "flac" if out_format_choice == 2 else "aac",
        "stretch":       stretch,
        "atempo_value":  atempo_value,
        "delay_ms":      delay_ms,
        "mute_in_ms":    mute_in_ms,
        "fade_in_ms":    fade_in_ms,
        "fade_out_ms":   fade_out_ms,
    }


# ─────────────────────────────────────────────
#  Conversao de um arquivo
# ─────────────────────────────────────────────

def process_file(video_file, audio_streams, params):
    """Processa todas as faixas selecionadas de um arquivo."""

    selected_nums = params["selected_nums"]
    track_titles  = params["track_titles"]
    track_langs   = params.get("track_langs", {})
    stretch       = params["stretch"]
    atempo_value  = params["atempo_value"]
    delay_ms      = params["delay_ms"]
    mute_in_ms    = params["mute_in_ms"]
    fade_in_ms    = params["fade_in_ms"]
    fade_out_ms   = params["fade_out_ms"]

    selected_streams = [audio_streams[n - 1] for n in selected_nums]

    base_name  = os.path.splitext(os.path.basename(video_file))[0]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_format = params["out_format"]

    for selected in selected_streams:
        stream_index = selected['index']
        audio_info   = get_audio_info(video_file, stream_index)

        codec       = audio_info.get("codec_name", "unknown")
        sample_rate = audio_info.get("sample_rate", "48000")
        channels    = audio_info.get("channels", 2)
        lang_raw    = audio_info.get("tags", {}).get("language", "unknown")
        track_num_1based = selected_nums[selected_streams.index(selected)]
        lang        = track_langs.get(track_num_1based, lang_raw)

        # Usa o titulo definido pelo usuario (pode ser vazio se nao havia titulo e usuario nao digitou)
        title = track_titles.get(track_num_1based, audio_info.get("tags", {}).get("title", ""))

        # Detecta se e possivel usar stream copy (sem processamento de audio real)
        is_stream_copy = (
            out_format != "flac"
            and "dts" not in codec.lower()
            and stretch == 1.0
            and delay_ms == 0
            and mute_in_ms == 0
            and fade_in_ms == 0
            and fade_out_ms == 0
        )

        # bit_rate nao e necessario no modo copy
        bitrate = None if is_stream_copy else get_stream_bitrate(video_file, stream_index, channels)

        # Lógica de Extensão e Formato
        if out_format == "flac" or "dts" in codec.lower():
            ext = "flac"
            current_out_format = "flac"
        else:
            current_out_format = out_format
            # MKA para AAC/AC3/EAC3: unico container que suporta tags por stream
            # corretamente lidas pelo MKVToolNix (idioma + titulo).
            # Opus e FLAC suportam tags nativamente em seus containers originais.
            ext_map = {
                'aac':  'mka',
                'eac3': 'mka',
                'ac3':  'mka',
                'opus': 'opus',
                'flac': 'flac',
                'mp3':  'mp3'
            }
            ext = ext_map.get(codec.lower(), 'mka')

        delay_tag   = format_tag(delay_ms)
        fadein_tag  = format_tag(fade_in_ms)
        fadeout_tag = format_tag(fade_out_ms)

        output_file = os.path.join(
            script_dir,
            f"{base_name}_track{stream_index}_{lang}"
            f"_stretch{stretch:.6f}"
            f"_delay{delay_tag}"
            f"_mute{format_tag(mute_in_ms)}"
            f"_fadein{fadein_tag}"
            f"_fadeout{fadeout_tag}"
            f".{ext}"
        )

        print(f"\n  -- Faixa {stream_index} ({lang}) --")
        if is_stream_copy:
            print(f"  Codec: {codec} | Sample rate: {sample_rate} | Canais: {channels}")
            print(f"  Modo  : STREAM COPY (sem reencode)")
        else:
            print(f"  Codec: {codec} | Bitrate: {bitrate//1000}k | Sample rate: {sample_rate} | Canais: {channels}")
            print(f"  Stretch: {stretch:.8f} | atempo: {atempo_value:.8f}")
            print(f"  Delay: {delay_ms:.0f}ms | Mute IN: {mute_in_ms:.0f}ms | Fade IN: {fade_in_ms:.0f}ms | Fade OUT: {fade_out_ms:.0f}ms")
        print(f"  Saida  : {output_file}")

        if is_stream_copy:
            # ── Modo stream copy: apenas remux, sem filtros ───────────────────
            # -fflags +discardcorrupt: descarta pacotes corrompidos em vez de abortar
            # (necessario para fontes TS com AAC-ADTS e streams com erros de PES)
            cmd = [
                FFMPEG_PATH,
                "-fflags", "+discardcorrupt",
                "-i", video_file,
                "-map", f"0:{stream_index}",
                "-c:a", "copy",
                "-map_metadata", "-1",
                "-map_chapters", "-1",
            ]
            cmd.extend(["-metadata:s:a:0", f"language={lang}"])
            if title:
                cmd.extend(["-metadata:s:a:0", f"title={title}"])
            cmd.extend(["-sn", "-dn"])
            cmd.extend([output_file, "-y"])
        else:
            # ── Modo reencode: aplica filtros e recodifica ────────────────────
            filter_parts = ["aformat=sample_fmts=fltp"]

            if delay_ms < 0:
                trim_sec = abs(delay_ms) / 1000.0
                filter_parts.append(f"atrim=start={trim_sec:.6f}")
                filter_parts.append("asetpts=PTS-STARTPTS")

            filter_parts.append(build_atempo_filter(stretch))

            if delay_ms > 0:
                filter_parts.append(f"adelay={delay_ms:.0f}|{delay_ms:.0f}")

            if mute_in_ms > 0:
                mute_end = mute_in_ms / 1000.0
                filter_parts.append(f"volume=enable='between(t,0,{mute_end:.6f})':volume=0")

            if fade_in_ms > 0:
                fade_start = mute_in_ms / 1000.0
                filter_parts.append(f"afade=t=in:st={fade_start:.6f}:d={fade_in_ms/1000:.6f}")

            if fade_out_ms > 0:
                filter_parts.append(f"areverse,afade=t=in:st=0:d={fade_out_ms/1000:.6f},areverse")

            audio_filter = ",".join(filter_parts)
            print(f"  Filtro : {audio_filter}")

            # Configuração de codificação
            if current_out_format == "flac":
                audio_codec = "flac"
                quality_args = ["-compression_level", "5"]
            elif codec.lower() == "aac":
                audio_codec = "aac"
                if bitrate and bitrate > 0:
                    quality_args = ["-b:a", str(bitrate)]
                else:
                    quality_args = ["-q:a", "2"]
            elif codec.lower() == "eac3" or codec.lower() == "ac3":
                audio_codec = "ac3"
                quality_args = ["-b:a", str(min(bitrate, 640000)) if bitrate else "640k"]
            elif codec.lower() == "opus":
                audio_codec = "libopus"
                quality_args = ["-b:a", str(bitrate) if bitrate else "320k"]
            else:
                audio_codec = codec
                quality_args = ["-b:a", str(bitrate)] if bitrate else []

            cmd = [
                FFMPEG_PATH,
                "-i", video_file,
                "-map", f"0:{stream_index}",
                "-af", audio_filter,
                "-c:a", audio_codec,
                *quality_args,
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-map_metadata", "-1",
                "-map_chapters", "-1",
            ]
            cmd.extend(["-metadata:s:a:0", f"language={lang}"])
            if title:
                cmd.extend(["-metadata:s:a:0", f"title={title}"])
            cmd.extend(["-sn", "-dn", "-fflags", "+bitexact", "-flags:a", "+bitexact"])
            cmd.extend([output_file, "-y"])

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            print(f"  x ERRO: {result.stderr}")
        else:
            print(f"  OK Concluido!")


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Arraste um ou mais arquivos de video sobre o .bat")
        sys.exit(1)

    file_list = [a.strip('"') for a in sys.argv[1:]]
    missing   = [f for f in file_list if not os.path.exists(f)]
    if missing:
        for m in missing:
            print(f"Erro: Arquivo nao encontrado: {m}")
        sys.exit(1)

    is_batch = len(file_list) > 1

    if is_batch:
        print(f"\n===== MODO EM MASSA: {len(file_list)} arquivo(s) =====")
        for f in file_list:
            print(f"  - {os.path.basename(f)}")

        print("\nValidando faixas de audio em todos os arquivos...")
        reference_streams, error = validate_batch(file_list)
        if error:
            print(f"\n{error}")
            print("\nAviso: foram encontradas inconsistencias entre os arquivos.")
            while True:
                resp = input("Deseja ignorar e prosseguir com o encode mesmo assim? (s/n): ").strip().lower()
                if resp in ("s", "n"):
                    break
                print("Digite 's' para sim ou 'n' para nao.")
            if resp == "n":
                print("Abortando.")
                sys.exit(1)
            print("OK Prosseguindo com as faixas do arquivo de referencia.")
        else:
            print("\nOK Todos os arquivos tem faixas compativeis.")
    else:
        print(f"\nArquivo: {file_list[0]}")
        reference_streams = get_audio_streams(file_list[0])
        if not reference_streams:
            print("Erro: Nenhuma faixa de audio encontrada.")
            sys.exit(1)

    # Coleta parametros uma unica vez
    params = collect_params(reference_streams)

    # Processa cada arquivo
    total = len(file_list)
    for idx, video_file in enumerate(file_list, 1):
        print(f"\n{'='*50}")
        print(f"ARQUIVO {idx}/{total}: {os.path.basename(video_file)}")
        print(f"{'='*50}")
        streams = get_audio_streams(video_file) if is_batch else reference_streams
        process_file(video_file, streams, params)

    print(f"\n{'='*50}")
    print(f"OK PROCESSAMENTO CONCLUIDO - {total} arquivo(s)")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()