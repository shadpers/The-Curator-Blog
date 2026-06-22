"""
release_renamer.py
Detecta via ffprobe: resolucao, codec de video, codec/canais do audio principal,
idiomas de audio (sem comentarios) e quantidade de legendas.

Modo batch  : se todos os arquivos tiverem as mesmas specs, pergunta titulo base,
              ano e source uma vez e renomeia tudo automaticamente.
Modo manual : se houver inconsistencia, avisa e processa arquivo por arquivo.
"""

import subprocess
import json
import sys
import os
import hashlib
import re

FFPROBE_BIN = r"C:\FFmpeg\bin\ffprobe.exe"

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
    except FileNotFoundError:
        print("\nERRO: ffprobe nao encontrado em: " + FFPROBE_BIN)
        input("Pressione Enter para sair...")
        sys.exit(1)
    except json.JSONDecodeError:
        print("\nERRO: Falha ao interpretar a saida do ffprobe.")
        input("Pressione Enter para sair...")
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
    """
    Extrai numeracao do nome original.
    Reconhece: S01E01, EP01, E01, - 01, _01, etc.
    Retorna string vazia se nao encontrar.
    """
    name = os.path.splitext(filename)[0]

    # S01E01 ou S1E1
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', name)
    if m:
        return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"

    # EP01 ou E01 isolado
    m = re.search(r'\b[Ee][Pp]?(\d{1,3})\b', name)
    if m:
        return f"E{int(m.group(1)):02d}"

    # - 01 / _01 / [ 01 ] / ( 01 )
    m = re.search(r'[-_\[\(\s](\d{1,3})[\s\]\)_\-\[]', name)
    if m:
        return f"E{int(m.group(1)):02d}"

    # numero no final do nome (antes da extensao)
    m = re.search(r'(\d{1,3})\s*$', name)
    if m:
        return f"E{int(m.group(1)):02d}"

    return ""


def apply_season(ep_tag: str, season: int) -> str:
    """
    Dado ep_tag (E01 ou S01E01) e numero de temporada,
    retorna sempre S{season}E{num}.
    """
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
    print(f"    Audio      : {ref['audio_label']}")
    print(f"    Idiomas    : {', '.join(langs)}")
    print(f"    Legendas   : {ref['sub_tag']}")
    print(sep)

    if len(ref["audio_langs"]) > LANG_LIMIT:
        print(f"\n  AVISO: {len(ref['audio_langs'])} idiomas detectados."
              f" Usando apenas os primeiros {LANG_LIMIT} no nome.")

    print()
    raw_title  = input("  Titulo base (ex: Another): ").strip()
    year       = input("  Ano        (ex: 2012): ").strip()
    source     = input("  Source     (WEB-DL / BluRay / BDRip / WEBRip): ").strip()
    raw_season = input("  Temporada  (ex: 1 / Enter para pular): ").strip()

    title_base  = sanitize_title(raw_title) if raw_title else "Unknown"
    year_part   = re.sub(r"\D", "", year)[:4] if year else "????"
    source_part = sanitize_source(source) if source else "Unknown"
    season_num  = int(re.sub(r"\D", "", raw_season)) if raw_season else None

    print(f"\n  Calculando SHA-256 de {len(files_info)} arquivo(s)...\n")

    plan: list = []
    for info in files_info:
        fp      = info["filepath"]
        ep_tag  = extract_episode_tag(os.path.basename(fp))
        if ep_tag and season_num is not None:
            ep_tag = apply_season(ep_tag, season_num)
        title   = f"{title_base}.{ep_tag}" if ep_tag else title_base

        print(f"  Hashing: {os.path.basename(fp)}...", end=" ", flush=True)
        hash_tag = make_hash_tag(fp)
        print("OK")

        new_name = build_filename(
            title, year_part, info["resolution"], source_part,
            info["video_codec"], info["audio_label"], langs,
            info["sub_tag"], hash_tag
        )
        plan.append((fp, new_name))

    print()
    for old_path, new_name in plan:
        print(f"  {os.path.basename(old_path)}")
        print(f"    -> {new_name}\n")

    print(sep)
    confirm = input(f"  Renomear todos os {len(plan)} arquivo(s)? (s/n): ").strip().lower()
    if confirm != "s":
        print("  Cancelado.")
        return

    erros = 0
    for old_path, new_name in plan:
        dest = os.path.join(os.path.dirname(os.path.abspath(old_path)), new_name)
        if os.path.exists(dest) and dest != os.path.abspath(old_path):
            print(f"  AVISO: Ja existe -> {new_name}  (pulado)")
            erros += 1
            continue
        os.rename(old_path, dest)

    ok = len(plan) - erros
    print(f"\n  OK - {ok}/{len(plan)} arquivo(s) renomeado(s) com sucesso.")


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
    print(f"  Audio principal : {info['audio_label']}")
    print(f"  Idiomas audio   : {', '.join(langs) if langs else '-'}")
    print(f"  Legendas        : {info['sub_count']}  ->  {info['sub_tag']}")

    if len(info["audio_langs"]) > LANG_LIMIT:
        print(f"\n  AVISO: {len(info['audio_langs'])} idiomas detectados."
              f" Usando apenas os primeiros {LANG_LIMIT} no nome.")

    print()
    raw_title  = input("  Titulo  (ex: Another.E01): ").strip()
    year       = input("  Ano     (ex: 2012): ").strip()
    source     = input("  Source  (WEB-DL / BluRay / BDRip / WEBRip): ").strip()
    raw_season = input("  Temporada  (ex: 1 / Enter para pular): ").strip()

    # Se temporada informada, tenta extrair ep do nome e reescreve o titulo
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

    print(f"\n  Calculando SHA-256...", end=" ", flush=True)
    hash_tag = make_hash_tag(fp)
    print("OK")

    new_name = build_filename(
        title_part, year_part, info["resolution"], source_part,
        info["video_codec"], info["audio_label"], langs,
        info["sub_tag"], hash_tag
    )

    if len(new_name) > 180:
        print(f"\n  AVISO: Nome tem {len(new_name)} caracteres. Considere abreviar.")

    print(f"\n  Nome final:\n    {new_name}\n")

    confirm = input("  Renomear? (s/n): ").strip().lower()
    if confirm == "s":
        dest = os.path.join(os.path.dirname(os.path.abspath(fp)), new_name)
        if os.path.exists(dest) and dest != os.path.abspath(fp):
            print("  AVISO: Ja existe um arquivo com esse nome. Operacao cancelada.")
        else:
            os.rename(fp, dest)
            print("  OK - Renomeado com sucesso!")
    else:
        print("  Cancelado.")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    print("=" * 55)
    print("         Release Renamer - Colecao Pessoal")
    print("=" * 55)

    args = [a for a in sys.argv[1:]
            if os.path.isfile(a) and a.lower().endswith(".mkv")]

    if not args:
        print("\nUso: arraste um ou mais .mkv sobre o release_renamer.bat")
        input("\nPressione Enter para sair...")
        sys.exit(0)

    # Analisa todos os arquivos primeiro
    print(f"\n  Analisando {len(args)} arquivo(s)...\n")
    files_info: list = []
    for fp in sorted(args):
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
        # Arquivo unico: modo manual direto
        try:
            manual_rename_one(files_info[0])
        except KeyboardInterrupt:
            print("\n\n  Interrompido pelo usuario.")

    else:
        keys      = [specs_key(i) for i in files_info]
        all_same  = len(set(keys)) == 1

        if all_same:
            # Specs identicas: modo batch
            try:
                batch_rename(files_info)
            except KeyboardInterrupt:
                print("\n\n  Interrompido pelo usuario.")

        else:
            # Inconsistencia encontrada
            ref_key = keys[0]
            print("\n" + "=" * 55)
            print("  INCONSISTENCIA DETECTADA")
            print("=" * 55)
            print(f"\n  Referencia (primeiro arquivo):")
            print(f"    {os.path.basename(files_info[0]['filepath'])}")

            labels = ["Resolucao", "Video", "Audio", "Idiomas", "Legendas"]
            print("  Arquivos com specs diferentes:\n")
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
