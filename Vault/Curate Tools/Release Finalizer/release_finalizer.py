"""
release_finalizer.py
Detecta via ffprobe: resolucao, codec de video, codec/canais do audio principal,
idiomas de audio, quantidade de legendas e valida a estrutura de faixas.

Novidades:
- Edita o Titulo Interno do Arquivo (metadados) com o número real do episódio.
- Define APENAS a primeira faixa de audio e legenda como Padrao (Default) e Forcada (Forced).
- Exige uso de MKVToolNix (mkvpropedit) para edicao instantanea sem re-encode.
"""

import subprocess
import json
import sys
import os
import hashlib
import re

FFPROBE_BIN = r"C:\FFmpeg\bin\ffprobe.exe"
MKVPROPEDIT_BIN = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"

# ──────────────────────────────────────────────
# Mapeamentos
# ──────────────────────────────────────────────

VIDEO_CODEC_MAP = {
    "hevc":        "HEVC",
    "h264":        "H264",
    "av1":         "AV1",
    "vp9":         "VP9",
    "vp8":         "VP8",
    "mpeg2video":  "MPEG2",
    "mpeg4":       "MPEG4",
    "vc1":         "VC1",
}

AUDIO_CODEC_MAP = {
    "flac":      "FLAC",
    "aac":       "AAC",
    "ac3":       "AC3",
    "eac3":      "EAC3",
    "dts":       "DTS",
    "truehd":    "TrueHD",
    "mp3":       "MP3",
    "opus":      "OPUS",
    "vorbis":    "VORBIS",
    "pcm_s16le": "PCM",
    "pcm_s24le": "PCM",
}

CHANNEL_MAP = {1: "1.0", 2: "2.0", 6: "5.1", 8: "7.1"}
LANG_LIMIT = 6

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def check_dependencies():
    if not os.path.exists(FFPROBE_BIN):
        print(f"\nERRO: ffprobe nao encontrado em: {FFPROBE_BIN}")
        sys.exit(1)
    if not os.path.exists(MKVPROPEDIT_BIN):
        print(f"\nERRO: mkvpropedit nao encontrado em: {MKVPROPEDIT_BIN}")
        print("Instale o MKVToolNix e verifique o caminho.")
        sys.exit(1)

def run_ffprobe(filepath: str) -> dict:
    cmd = [
        FFPROBE_BIN, "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("\nERRO: Falha ao interpretar a saida do ffprobe.")
        sys.exit(1)

def detect_resolution(stream: dict) -> str:
    h = stream.get("height", 0)
    if h >= 2160: return "2160p"
    if h >= 1080: return "1080p"
    if h >= 720:  return "720p"
    if h >= 480:  return "480p"
    if h >= 360:  return "360p"
    return f"{h}p" if h else "?p"

def detect_video_codec(stream: dict) -> str:
    name = stream.get("codec_name", "").lower()
    return VIDEO_CODEC_MAP.get(name, name.upper())

def detect_audio_label(stream: dict) -> str:
    name   = stream.get("codec_name", "").lower()
    label  = AUDIO_CODEC_MAP.get(name, name.upper())
    ch     = stream.get("channels", 2)
    ch_str = CHANNEL_MAP.get(ch, f"{ch}ch")
    return f"{label}{ch_str}"

def compute_sha256(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()

def make_hash_tag(filepath: str) -> str:
    h = compute_sha256(filepath)
    return f"[{h[:4].upper()}{h[-4:].upper()}]"

def sanitize_title(raw: str) -> str:
    cleaned = re.sub(r"[^\w\s\-\(\)\.]", "", raw, flags=re.UNICODE)
    cleaned = re.sub(r"[\s_]+", ".", cleaned.strip())
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return cleaned

def sanitize_source(raw: str) -> str:
    return raw.strip().replace(" ", "-").replace("_", "-")

def is_commentary(stream: dict) -> bool:
    title = stream.get("tags", {}).get("title", "").lower()
    return "commentary" in title or "comentario" in title

def extract_episode_tag(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', name)
    if m: return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"
    m = re.search(r'\b[Ee][Pp]?(\d{1,3})\b', name)
    if m: return f"E{int(m.group(1)):02d}"
    m = re.search(r'[-_\[\(\s](\d{1,3})[\s\]\)_\-\[]', name)
    if m: return f"E{int(m.group(1)):02d}"
    m = re.search(r'(\d{1,3})\s*$', name)
    if m: return f"E{int(m.group(1)):02d}"
    return ""

def apply_season(ep_tag: str, season: int) -> str:
    m = re.search(r'[Ee](\d+)', ep_tag)
    ep_num = int(m.group(1)) if m else 1
    return f"S{season:02d}E{ep_num:02d}"

def build_filename(title: str, year: str, resolution: str, source: str,
                   video_codec: str, audio_label: str, langs: list,
                   sub_tag: str, hash_tag: str) -> str:
    langs_part = ".".join(langs)
    parts = [
        title, year, resolution, source,
        video_codec, audio_label, langs_part,
        f"{sub_tag}{hash_tag}",
    ]
    return ".".join(p for p in parts if p) + ".mkv"

def set_internal_episode(base_title: str, ep_num: int) -> str:
    """
    Substitui o número do episódio no título interno pelo número real do arquivo.
    Preserva o padding (zeros à esquerda) do título base.
    Ex: "Hunter x Hunter (1999) E01 [The Curator]" + 10 → "Hunter x Hunter (1999) E10 [The Curator]"
    """
    if not base_title or ep_num is None:
        return base_title

    m = re.search(r'(.*[Ee])(\d+)(.*)', base_title)
    if m:
        prefix, num_str, suffix = m.groups()
        padded = f"{ep_num:0{len(num_str)}d}"
        return f"{prefix}{padded}{suffix}"
    return base_title


def extract_ep_number(ep_tag: str) -> int | None:
    """Extrai o número do episódio de uma tag como 'E01', 'S01E10', etc."""
    if not ep_tag:
        return None
    m = re.search(r'[Ee](\d+)', ep_tag)
    return int(m.group(1)) if m else None

def apply_metadata_and_flags(filepath: str, title: str, audio_count: int, sub_count: int):
    """
    Usa o mkvpropedit para definir o título interno e colocar apenas
    a primeira trilha de áudio/legenda como default e forced.
    """
    cmd = [MKVPROPEDIT_BIN, filepath, "--edit", "info", "--set", f"title={title}"]
    
    # Ajustar faixas de audio
    for i in range(1, audio_count + 1):
        cmd.extend(["--edit", f"track:a{i}"])
        if i == 1:
            cmd.extend(["--set", "flag-default=1", "--set", "flag-forced=1"])
        else:
            cmd.extend(["--set", "flag-default=0", "--set", "flag-forced=0"])
            
    # Ajustar faixas de legenda
    for i in range(1, sub_count + 1):
        cmd.extend(["--edit", f"track:s{i}"])
        if i == 1:
            cmd.extend(["--set", "flag-default=1", "--set", "flag-forced=1"])
        else:
            cmd.extend(["--set", "flag-default=0", "--set", "flag-forced=0"])

    # Executa silenciosamente
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ──────────────────────────────────────────────
# Analise de um arquivo
# ──────────────────────────────────────────────

def analyze_file(filepath: str) -> dict:
    data    = run_ffprobe(filepath)
    streams = data.get("streams", [])

    video_stream = next(
        (s for s in streams
         if s.get("codec_type") == "video"
         and not s.get("disposition", {}).get("attached_pic", 0)),
        None
    )
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    primary_audio = next(
        (s for s in audio_streams
         if s.get("disposition", {}).get("default", 0) and not is_commentary(s)),
        next((s for s in audio_streams if not is_commentary(s)), None)
        or (audio_streams[0] if audio_streams else None)
    )
    sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    resolution  = detect_resolution(video_stream)  if video_stream  else "?"
    video_codec = detect_video_codec(video_stream) if video_stream  else "?"
    audio_label = detect_audio_label(primary_audio) if primary_audio else "AAC2.0"

    audio_langs: list = []
    seen: set = set()
    for s in audio_streams:
        if is_commentary(s):
            continue
        lang = (s.get("tags") or {}).get("language", "").upper()
        if not lang or lang == "UND":
            lang = "UNK"
        if lang not in seen:
            seen.add(lang)
            audio_langs.append(lang)

    sub_count = len(sub_streams)
    sub_tag   = "Multi-Sub" if sub_count > 1 else ("1-Sub" if sub_count == 1 else "No-Sub")

    return {
        "filepath":    filepath,
        "resolution":  resolution,
        "video_codec": video_codec,
        "audio_label": audio_label,
        "audio_langs": audio_langs,
        "audio_count": len(audio_streams),
        "sub_count":   sub_count,
        "sub_tag":     sub_tag,
    }

def specs_key(info: dict) -> tuple:
    langs = tuple(info["audio_langs"][:LANG_LIMIT])
    return (
        info["resolution"],
        info["video_codec"],
        info["audio_label"],
        langs,
        info["sub_tag"],
        info["audio_count"], # Agora valida a quantidade exata de faixas de audio
        info["sub_count"],   # E legendas para garantir que sao estruturalmente iguais
    )

# ──────────────────────────────────────────────
# Modo batch (specs identicas)
# ──────────────────────────────────────────────

def batch_rename(files_info: list) -> None:
    ref   = files_info[0]
    langs = ref["audio_langs"][:LANG_LIMIT]
    sep   = "-" * 55

    print(f"\n{sep}")
    print("  Specs identicas em todos os arquivos:")
    print(f"    Resolucao  : {ref['resolution']}")
    print(f"    Video      : {ref['video_codec']}")
    print(f"    Audio      : {ref['audio_label']} ({ref['audio_count']} faixas totais)")
    print(f"    Idiomas    : {', '.join(langs)}")
    print(f"    Legendas   : {ref['sub_tag']} ({ref['sub_count']} faixas totais)")
    print(sep)

    print()
    raw_title  = input("  Titulo arquivo (ex: Another): ").strip()
    year       = input("  Ano            (ex: 2012): ").strip()
    source     = input("  Source         (WEB-DL / BluRay / BDRip): ").strip()
    raw_season = input("  Temporada      (ex: 1 / Enter p/ pular): ").strip()
    internal_title = input("  Titulo Interno (ex: Naruto S01E01): ").strip()

    title_base  = sanitize_title(raw_title) if raw_title else "Unknown"
    year_part   = re.sub(r"\D", "", year)[:4] if year else "????"
    source_part = sanitize_source(source) if source else "Unknown"
    season_num  = int(re.sub(r"\D", "", raw_season)) if raw_season else None

    print(f"\n  Montando plano para {len(files_info)} arquivo(s)...\n")

    # Cada entrada guarda os args necessários para build_filename (sem hash)
    # O hash só será calculado APÓS a aplicação dos metadados.
    plan: list = []
    for i, info in enumerate(files_info):
        fp      = info["filepath"]
        ep_tag  = extract_episode_tag(os.path.basename(fp))
        if ep_tag and season_num is not None:
            ep_tag = apply_season(ep_tag, season_num)
        title   = f"{title_base}.{ep_tag}" if ep_tag else title_base

        # Gera o titulo interno com o número REAL do episódio extraído do arquivo
        ep_num = extract_ep_number(ep_tag)
        current_internal_title = set_internal_episode(internal_title, ep_num) if internal_title and ep_num is not None else ""

        name_args = dict(
            title=title, year=year_part, resolution=info["resolution"],
            source=source_part, video_codec=info["video_codec"],
            audio_label=info["audio_label"], langs=langs, sub_tag=info["sub_tag"],
        )
        plan.append((fp, name_args, current_internal_title, info))

    # Exibe preview com hash placeholder
    print()
    for old_path, name_args, c_internal, info in plan:
        preview_name = build_filename(**name_args, hash_tag="[????????]")
        internal_display = c_internal if c_internal else preview_name
        print(f"  {os.path.basename(old_path)}")
        print(f"    -> {preview_name}")
        print(f"    -> Titulo Interno: {internal_display}\n")

    print(sep)
    confirm = input(f"  Renomear e Finalizar todos os {len(plan)} arquivo(s)? (s/n): ").strip().lower()
    if confirm != "s":
        print("  Cancelado.")
        return

    erros = 0
    print("\n  Aplicando mudancas...")
    for old_path, name_args, c_internal, info in plan:
        internal_final = c_internal  # será preenchido abaixo se necessário

        # 1. Aplica metadados no arquivo com o nome original
        apply_metadata_and_flags(old_path, internal_final or os.path.basename(old_path),
                                 info["audio_count"], info["sub_count"])

        # 2. Calcula o SHA-256 do arquivo já modificado
        print(f"  Hashing: {os.path.basename(old_path)}...", end=" ", flush=True)
        hash_tag = make_hash_tag(old_path)
        print("OK")

        # 3. Monta o nome final com o hash correto
        new_name  = build_filename(**name_args, hash_tag=hash_tag)
        if not internal_final:
            internal_final = new_name
            apply_metadata_and_flags(old_path, internal_final, info["audio_count"], info["sub_count"])

        dest = os.path.join(os.path.dirname(os.path.abspath(old_path)), new_name)

        if os.path.exists(dest) and dest != os.path.abspath(old_path):
            print(f"  AVISO: Ja existe -> {new_name} (pulado)")
            erros += 1
            continue

        # 4. Renomeia para o nome final
        os.rename(old_path, dest)

    ok = len(plan) - erros
    print(f"\n  OK - {ok}/{len(plan)} arquivo(s) finalizado(s) com sucesso.")

# ──────────────────────────────────────────────
# Modo manual (arquivo unico ou specs inconsistentes)
# ──────────────────────────────────────────────

def manual_rename_one(info: dict) -> None:
    fp    = info["filepath"]
    langs = info["audio_langs"][:LANG_LIMIT]
    sep   = "-" * 55

    print(f"\n{sep}")
    print(f"  Arquivo : {os.path.basename(fp)}")
    print(sep)
    print(f"  Resolucao       : {info['resolution']}")
    print(f"  Codec video     : {info['video_codec']}")
    print(f"  Audio principal : {info['audio_label']} ({info['audio_count']} faixas totais)")
    print(f"  Idiomas audio   : {', '.join(langs) if langs else '-'}")
    print(f"  Legendas        : {info['sub_count']} faixas totais ->  {info['sub_tag']}")

    print()
    raw_title  = input("  Titulo arquivo (ex: Another.E01): ").strip()
    year       = input("  Ano            (ex: 2012): ").strip()
    source     = input("  Source         (WEB-DL / BluRay / BDRip): ").strip()
    raw_season = input("  Temporada      (ex: 1 / Enter p/ pular): ").strip()
    internal_title = input("  Titulo Interno: ").strip()

    if raw_season:
        season_num = int(re.sub(r"\D", "", raw_season))
        ep_tag = extract_episode_tag(os.path.basename(fp))
        if ep_tag:
            base = sanitize_title(raw_title) if raw_title else "Unknown"
            ep_tag = apply_season(ep_tag, season_num)
            title_part = f"{base}.{ep_tag}"
        else:
            title_part = sanitize_title(raw_title) if raw_title else "Unknown"
    else:
        title_part = sanitize_title(raw_title) if raw_title else "Unknown"

    year_part   = re.sub(r"\D", "", year)[:4] if year else "????"
    source_part = sanitize_source(source) if source else "Unknown"

    name_args = dict(
        title=title_part, year=year_part, resolution=info["resolution"],
        source=source_part, video_codec=info["video_codec"],
        audio_label=info["audio_label"], langs=langs, sub_tag=info["sub_tag"],
    )
    preview_name = build_filename(**name_args, hash_tag="[????????]")

    print(f"\n  Nome final (hash pendente) : {preview_name}")
    print(f"  Titulo Interno : {internal_title if internal_title else preview_name}\n")

    confirm = input("  Renomear e Finalizar? (s/n): ").strip().lower()
    if confirm == "s":
        # 1. Aplica metadados no arquivo com o nome original
        apply_metadata_and_flags(fp, internal_title if internal_title else os.path.basename(fp),
                                 info["audio_count"], info["sub_count"])

        # 2. Calcula hash do arquivo JA modificado
        print(f"  Calculando SHA-256...", end=" ", flush=True)
        hash_tag = make_hash_tag(fp)
        print("OK")

        # 3. Monta nome final com hash correto
        new_name  = build_filename(**name_args, hash_tag=hash_tag)
        internal_final = internal_title if internal_title else new_name

        # Se o titulo interno estava vazio, reaplica com o nome definitivo como titulo
        if not internal_title:
            apply_metadata_and_flags(fp, internal_final, info["audio_count"], info["sub_count"])

        dest = os.path.join(os.path.dirname(os.path.abspath(fp)), new_name)
        if os.path.exists(dest) and dest != os.path.abspath(fp):
            print("  AVISO: Ja existe arquivo com esse nome. Cancelado.")
        else:
            # 4. Renomeia para o nome final
            os.rename(fp, dest)
            print(f"  OK - Finalizado com sucesso!")
            print(f"  Nome final : {new_name}")
    else:
        print("  Cancelado.")

# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    check_dependencies()
    
    print("=" * 55)
    print("        Release Finalizer - Colecao Pessoal")
    print("=" * 55)

    args = [a for a in sys.argv[1:]
            if os.path.isfile(a) and a.lower().endswith(".mkv")]

    if not args:
        print("\nUso: arraste um ou mais .mkv sobre o release_finalizer.bat")
        input("\nPressione Enter para sair...")
        sys.exit(0)

    # Ordena os arquivos pelo número real do episódio (em vez de ordem alfabética)
    def sort_key(fp: str) -> tuple:
        ep_tag = extract_episode_tag(os.path.basename(fp))
        num = extract_ep_number(ep_tag)
        return (num if num is not None else 9999, fp)

    args = sorted(args, key=sort_key)

    print(f"\n  Analisando {len(args)} arquivo(s)...\n")
    files_info: list = []
    for fp in args:
        print(f"  ffprobe -> {os.path.basename(fp)}...", end=" ", flush=True)
        try:
            info = analyze_file(fp)
            files_info.append(info)
            print("OK")
        except Exception as e:
            print(f"ERRO ({e})")

    if not files_info:
        print("\n  Nenhum arquivo valido para processar.")
        input("\nPressione Enter para sair...")
        sys.exit(0)

    if len(files_info) == 1:
        try:
            manual_rename_one(files_info[0])
        except KeyboardInterrupt:
            print("\n\n  Interrompido pelo usuario.")
    else:
        keys      = [specs_key(i) for i in files_info]
        all_same  = len(set(keys)) == 1

        if all_same:
            try:
                batch_rename(files_info)
            except KeyboardInterrupt:
                print("\n\n  Interrompido pelo usuario.")
        else:
            ref_key = keys[0]
            print("\n" + "=" * 55)
            print("  INCONSISTENCIA DETECTADA")
            print("=" * 55)
            print(f"\n  Referencia (primeiro arquivo):")
            print(f"    {os.path.basename(files_info[0]['filepath'])}")

            labels = ["Resolucao", "Video", "Audio", "Idiomas", "Legendas", "Qtd Audio", "Qtd Legenda"]
            print("  Arquivos com specs/faixas diferentes:\n")
            for info, key in zip(files_info, keys):
                if key != ref_key:
                    diffs = []
                    for label, a, b in zip(labels, ref_key, key):
                        if a != b:
                            diffs.append(f"{label}: {b}  (ref: {a})")
                    print(f"    {os.path.basename(info['filepath'])}")
                    for d in diffs:
                        print(f"      ! {d}")

            print("\n  Renomeacao manual necessaria. Processando um por um...\n")
            for info in files_info:
                try:
                    manual_rename_one(info)
                except KeyboardInterrupt:
                    print("\n\n  Interrompido pelo usuario.")
                    break

    print("\n" + "=" * 55)
    input("  Pressione Enter para sair...")

if __name__ == "__main__":
    main()