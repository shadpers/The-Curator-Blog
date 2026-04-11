"""
srt_style_mux.py
Extrai tracks SRT de um MKV, aplica estilo de um .ass de referência e remux automático.

Uso:
    python srt_style_mux.py "arquivo.mkv" "estilo_referencia.ass"

    Ou via srt_style_mux.bat arrastando os dois arquivos.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Ferramentas MKV
# ──────────────────────────────────────────────────────────────────────────────

def find_tool(name: str) -> str:
    """Procura o executável no PATH e nas pastas padrão do MKVToolNix."""
    from shutil import which
    found = which(name)
    if found:
        return found
    candidates = [
        Path(r"C:\Program Files\MKVToolNix") / (name + ".exe"),
        Path(r"C:\Program Files (x86)\MKVToolNix") / (name + ".exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    sys.exit(f"[ERRO] '{name}' não encontrado. Instale o MKVToolNix e adicione ao PATH.")


def get_tracks(mkv: Path) -> list[dict]:
    """Retorna a lista de tracks via mkvmerge -J."""
    mkvmerge = find_tool("mkvmerge")
    result = subprocess.run(
        [mkvmerge, "-J", str(mkv)],
        capture_output=True, text=True, encoding="utf-8"
    )
    data = json.loads(result.stdout)
    return data.get("tracks", [])


def extract_srts(mkv: Path, track_ids: list[int], out_dir: Path) -> dict[int, Path]:
    """Extrai tracks SRT para out_dir. Retorna {track_id: path}."""
    mkvextract = find_tool("mkvextract")
    spec = [f"{tid}:{out_dir / f'track_{tid}.srt'}" for tid in track_ids]
    subprocess.run(
        [mkvextract, str(mkv), "tracks"] + spec,
        check=True
    )
    return {tid: out_dir / f"track_{tid}.srt" for tid in track_ids}


# ──────────────────────────────────────────────────────────────────────────────
# Conversão SRT → ASS
# ──────────────────────────────────────────────────────────────────────────────

def srt_ts_to_ass(ts: str) -> str:
    ts = ts.strip()
    hms, ms = ts.split(",")
    h, m, s = hms.split(":")
    cc = int(ms) // 10
    return f"{int(h)}:{m}:{s}.{cc:02d}"


def parse_srt(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    pattern = re.compile(
        r"\d+\n"
        r"(\d{2}:\d{2}:\d{2},\d{3})"
        r" --> "
        r"(\d{2}:\d{2}:\d{2},\d{3})"
        r"[^\n]*\n"
        r"([\s\S]*?)(?=\n\n|\Z)"
    )
    entries = []
    for m in pattern.finditer(text):
        raw = m.group(3).strip()
        raw = re.sub(r"<b>(.*?)</b>", r"{\\b1}\1{\\b0}", raw, flags=re.IGNORECASE | re.DOTALL)
        raw = re.sub(r"<i>(.*?)</i>", r"{\\i1}\1{\\i0}", raw, flags=re.IGNORECASE | re.DOTALL)
        raw = re.sub(r"<u>(.*?)</u>", r"{\\u1}\1{\\u0}", raw, flags=re.IGNORECASE | re.DOTALL)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = raw.replace("\n", "\\N")
        entries.append({
            "start": srt_ts_to_ass(m.group(1)),
            "end":   srt_ts_to_ass(m.group(2)),
            "text":  raw,
        })
    return entries


def extract_header(ref_path: Path) -> str:
    text = ref_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    header_lines = []
    for line in lines:
        if re.match(r"\[Events\]", line, re.IGNORECASE):
            break
        header_lines.append(line)
    while header_lines and header_lines[-1].strip() == "":
        header_lines.pop()
    return "\n".join(header_lines)


def extract_fonts_from_ass(ref_path: Path) -> list[str]:
    """Retorna lista de fontes únicas declaradas nos estilos do .ass."""
    text = ref_path.read_text(encoding="utf-8-sig")
    fonts = []
    in_styles = False
    fmt_indices: dict[str, int] = {}

    for line in text.splitlines():
        line = line.strip()
        if re.match(r"\[V4\+? Styles\]", line, re.IGNORECASE):
            in_styles = True
            continue
        if line.startswith("[") and in_styles:
            break
        if not in_styles:
            continue
        if line.lower().startswith("format:"):
            fields = [f.strip().lower() for f in line[7:].split(",")]
            fmt_indices = {f: i for i, f in enumerate(fields)}
        elif line.lower().startswith("style:"):
            values = [v.strip() for v in line[6:].split(",")]
            idx = fmt_indices.get("fontname")
            if idx is not None and idx < len(values):
                font = values[idx]
                if font and font not in fonts:
                    fonts.append(font)
    return fonts


def check_font(fonts: list[str], ttf_path: Path | None):
    """Exibe aviso sobre dependências de fonte e status do arquivo fornecido."""
    print("\nDependências de fonte do estilo:")
    for font in fonts:
        print(f"  → {font}")

    if not fonts:
        print("  (nenhuma fonte declarada nos estilos)")
        return

    if ttf_path is None:
        print("\n  [AVISO] Nenhum arquivo de fonte fornecido — a fonte NÃO será embedada.")
        print("          Arraste o .ttf/.otf no .bat para embeddá-la automaticamente.")
    else:
        print(f"\n  Fonte fornecida : {ttf_path.name}")
        # Verificação simples: nome do arquivo contém algum token do nome da fonte
        font_tokens = {t.lower() for f in fonts for t in f.split()}
        file_stem   = ttf_path.stem.lower()
        match = any(tok in file_stem for tok in font_tokens if len(tok) > 2)
        if match:
            print("  Status          : ✓ Nome do arquivo bate com o estilo — OK para embedar.")
        else:
            print("  Status          : ⚠ Nome do arquivo não parece corresponder ao estilo.")
            print(f"                    Esperado algo relacionado a: {', '.join(fonts)}")
            resp = input("  Continuar mesmo assim? [s/N]: ").strip().lower()
            if resp not in ("s", "sim", "y", "yes"):
                sys.exit("Operação cancelada pelo usuário.")


def convert_to_ass(srt_path: Path, header: str, out_path: Path):
    try:
        raw = srt_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = srt_path.read_text(encoding="latin-1")

    entries = parse_srt(raw)
    if not entries:
        raise ValueError("Nenhum diálogo encontrado no SRT.")

    lines = [header, "", "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for e in entries:
        lines.append(f"Dialogue: 0,{e['start']},{e['end']},Default,,0,0,0,,{e['text']}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return len(entries)


# ──────────────────────────────────────────────────────────────────────────────
# Remux
# ──────────────────────────────────────────────────────────────────────────────

def remux(mkv: Path, all_tracks: list[dict], selected_ids: list[int],
          all_sub_ids: list[int], ass_files: dict[int, Path],
          track_meta: dict[int, dict], ttf_path: Path | None, out_path: Path):
    """
    Remux preservando a ordem exata das tracks originais via --track-order.
    Cada .ass convertido entra no slot exato do SRT que substituiu.
    """
    mkvmerge = find_tool("mkvmerge")
    cmd = [mkvmerge, "-o", str(out_path)]

    # Subtitles do MKV original que NÃO foram convertidos
    keep_sub_ids = [sid for sid in all_sub_ids if sid not in selected_ids]
    if keep_sub_ids:
        cmd += ["--subtitle-tracks", ",".join(str(i) for i in keep_sub_ids)]
    else:
        cmd += ["--no-subtitles"]

    cmd.append(str(mkv))

    # Mapeia track_id → índice do arquivo extra (1-based, pois 0 = MKV original)
    # A ordem de append dos .ass define o file index no mkvmerge
    ass_file_index: dict[int, int] = {}
    for file_idx, (tid, ass_path) in enumerate(ass_files.items(), start=1):
        meta = track_meta.get(tid, {})
        lang    = meta.get("language", "")
        name    = meta.get("name", "")
        forced  = meta.get("forced_track", False)
        default = meta.get("default_track", False)

        if lang:
            cmd += ["--language",     f"0:{lang}"]
        if name:
            cmd += ["--track-name",   f"0:{name}"]
        if forced:
            cmd += ["--forced-track", "0:yes"]
        if default:
            cmd += ["--default-track","0:yes"]
        cmd.append(str(ass_path))
        ass_file_index[tid] = file_idx

    # Reconstrói --track-order na ordem original das tracks
    order_parts = []
    for t in all_tracks:
        tid  = t["id"]
        ttype = t.get("type", "")
        if tid in ass_file_index:
            # Track convertida: vem do arquivo extra correspondente
            order_parts.append(f"{ass_file_index[tid]}:0")
        elif ttype == "subtitles" and tid in selected_ids:
            pass  # não deveria ocorrer, mas ignora por segurança
        else:
            # Track original mantida
            order_parts.append(f"0:{tid}")

    if ttf_path is not None:
        mime = "font/otf" if ttf_path.suffix.lower() == ".otf" else "font/ttf"
        cmd += ["--attachment-mime-type", mime,
                "--attach-file", str(ttf_path)]

    cmd += ["--track-order", ",".join(order_parts)]

    subprocess.run(cmd, check=True)


# ──────────────────────────────────────────────────────────────────────────────
# UI de seleção no terminal
# ──────────────────────────────────────────────────────────────────────────────

def ask_selection(srt_tracks: list[dict]) -> list[int]:
    print("\nTracks SRT encontradas:")
    print(f"  {'#':<4} {'ID':<6} {'Lang':<8} {'Nome'}")
    print("  " + "-" * 45)
    for i, t in enumerate(srt_tracks, 1):
        props = t.get("properties", {})
        lang  = props.get("language", "und")
        name  = props.get("track_name", "")
        print(f"  {i:<4} {t['id']:<6} {lang:<8} {name}")

    print()
    resp = input("Aplicar estilo em TODAS as tracks? [S/n]: ").strip().lower()
    if resp in ("", "s", "sim", "y", "yes"):
        return [t["id"] for t in srt_tracks]

    print("Digite os números das tracks separados por vírgula (ex: 1,3):")
    raw = input("> ").strip()
    chosen = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(srt_tracks):
                chosen.append(srt_tracks[idx]["id"])
            else:
                print(f"  [AVISO] Número {part} inválido, ignorado.")
    if not chosen:
        sys.exit("[ERRO] Nenhuma track selecionada.")
    return chosen


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mkv_path = Path(sys.argv[1])
    ref_path = Path(sys.argv[2])
    ttf_path = Path(sys.argv[3]) if len(sys.argv) >= 4 else None

    if not mkv_path.is_file():
        sys.exit(f"[ERRO] MKV não encontrado: {mkv_path}")
    if not ref_path.is_file():
        sys.exit(f"[ERRO] Referência .ass não encontrada: {ref_path}")
    if ttf_path is not None and not ttf_path.is_file():
        sys.exit(f"[ERRO] Fonte não encontrada: {ttf_path}")

    print("=" * 55)
    print(f"  MKV      : {mkv_path.name}")
    print(f"  Estilo   : {ref_path.name}")
    if ttf_path:
        print(f"  Fonte    : {ttf_path.name}")
    print("=" * 55)

    # Dependências de fonte
    fonts = extract_fonts_from_ass(ref_path)
    check_font(fonts, ttf_path)

    # Listar tracks
    tracks     = get_tracks(mkv_path)
    srt_tracks = [t for t in tracks
                  if t.get("type") == "subtitles"
                  and t.get("properties", {}).get("codec_id") == "S_TEXT/UTF8"]
    all_sub_ids = [t["id"] for t in tracks if t.get("type") == "subtitles"]

    if not srt_tracks:
        sys.exit("[AVISO] Nenhuma track SRT (S_TEXT/UTF8) encontrada no MKV.")

    # Seleção
    selected_ids = ask_selection(srt_tracks)

    # Metadados para preservar no remux
    track_meta = {
        t["id"]: {
            "language":     t.get("properties", {}).get("language", ""),
            "name":         t.get("properties", {}).get("track_name", ""),
            "forced_track": t.get("properties", {}).get("forced_track", False),
            "default_track":t.get("properties", {}).get("default_track", False),
        }
        for t in srt_tracks if t["id"] in selected_ids
    }

    header = extract_header(ref_path)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Extrair SRTs
        print(f"\nExtraindo {len(selected_ids)} track(s)...")
        srt_files = extract_srts(mkv_path, selected_ids, tmp_dir)

        # Converter para ASS
        ass_files: dict[int, Path] = {}
        for tid, srt_path in srt_files.items():
            ass_path = tmp_dir / f"track_{tid}.ass"
            count = convert_to_ass(srt_path, header, ass_path)
            lang = track_meta[tid]["language"]
            name = track_meta[tid]["name"] or "-"
            print(f"  Convertido  track {tid} [{lang}] '{name}'  ({count} linhas)")
            ass_files[tid] = ass_path

        # Remux
        out_path = mkv_path.parent / (mkv_path.stem + "_styled.mkv")
        print(f"\nRemuxando → {out_path.name} ...")
        remux(mkv_path, tracks, selected_ids, all_sub_ids, ass_files, track_meta, ttf_path, out_path)

    print(f"\n✓ Concluído: {out_path.name}")
    print("=" * 55)


if __name__ == "__main__":
    main()
