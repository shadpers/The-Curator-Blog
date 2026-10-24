"""
srt_style_mux.py
Extrai tracks SRT de múltiplos MKVs, aplica o estilo de um .ass de referência
e remuxa automaticamente para uma pasta de saída.

Uso:
    python srt_style_mux.py "estilo_referencia.ass" "fonte.ttf" "video1.mkv" "video2.mkv" ...
    (A fonte é opcional. Se não houver fonte, passe os MKVs após o .ass)

    Ou via srt_style_mux.bat arrastando os arquivos juntos.

Saída:
    <pasta do primeiro MKV>/styled/<nome>_styled.mkv
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Console
# ──────────────────────────────────────────────────────────────────────────────

def _enable_ansi() -> None:
    """Liga sequências ANSI no console do Windows 10+."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_enable_ansi()

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    CYAN   = "\033[36m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"


W = 58


def paint(text: str, *styles: str) -> str:
    return "".join(styles) + text + C.RESET


def rule(char: str = "─") -> str:
    return paint(char * W, C.GRAY)


def banner() -> None:
    print()
    print(paint("┌" + "─" * (W - 2) + "┐", C.CYAN))
    print(paint("│", C.CYAN) + paint("  SRT STYLE MUX".center(W - 2), C.BOLD, C.WHITE) + paint("│", C.CYAN))
    print(paint("│", C.CYAN) + paint("  estilo · fonte · remux".center(W - 2), C.DIM) + paint("│", C.CYAN))
    print(paint("└" + "─" * (W - 2) + "┘", C.CYAN))


def section(title: str) -> None:
    print()
    print(paint(f"  {title}", C.BOLD, C.CYAN))
    print(rule())


def kv(label: str, value: str) -> None:
    print(f"  {paint(f'{label:<10}', C.GRAY)} {value}")


def info(msg: str) -> None:
    print(f"  {paint('·', C.CYAN)} {msg}")


def ok(msg: str) -> None:
    print(f"  {paint('✓', C.GREEN)} {msg}")


def warn(msg: str) -> None:
    print(f"  {paint('!', C.YELLOW)} {paint(msg, C.YELLOW)}")


def err(msg: str) -> None:
    print(f"  {paint('✗', C.RED)} {paint(msg, C.RED)}")


def ask(prompt: str) -> str:
    try:
        return input(f"  {paint('›', C.CYAN)} {prompt} ").strip()
    except EOFError:
        return ""


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
    sys.exit(f"\n  {paint('✗', C.RED)} '{name}' não encontrado. Instale o MKVToolNix e adicione ao PATH.\n")


def get_tracks(mkv: Path) -> list[dict]:
    """Retorna a lista de tracks via mkvmerge -J."""
    mkvmerge = find_tool("mkvmerge")
    result = subprocess.run(
        [mkvmerge, "-J", str(mkv)],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or result.stdout or "sem saída").strip()
        raise RuntimeError(detail)
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


def check_font(fonts: list[str], ttf_path: Path | None) -> None:
    """Exibe aviso sobre dependências de fonte e status do arquivo fornecido."""
    section("Fontes do estilo")
    if not fonts:
        info("Nenhuma fonte declarada nos estilos.")
        return

    for font in fonts:
        info(font)

    if ttf_path is None:
        print()
        warn("Nenhum arquivo de fonte fornecido — a fonte NÃO será embedada.")
        info("Arraste o .ttf/.otf junto no .bat para embedar automaticamente.")
        return

    print()
    kv("Arquivo", ttf_path.name)
    font_tokens = {t.lower() for f in fonts for t in f.split()}
    file_stem = ttf_path.stem.lower()
    match = any(tok in file_stem for tok in font_tokens if len(tok) > 2)
    if match:
        ok("Nome do arquivo bate com o estilo. OK para embedar.")
    else:
        warn("O nome do arquivo não parece corresponder ao estilo.")
        info(f"Esperado algo relacionado a: {', '.join(fonts)}")
        resp = ask("Continuar mesmo assim? [s/N]:").lower()
        if resp not in ("s", "sim", "y", "yes"):
            print()
            err("Operação cancelada.")
            sys.exit(1)


def convert_to_ass(srt_path: Path, header: str, out_path: Path) -> int:
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
          track_meta: dict[int, dict], ttf_path: Path | None, out_path: Path) -> None:
    """
    Remux preservando a ordem exata das tracks originais via --track-order.
    Cada .ass convertido entra no slot exato do SRT que substituiu.
    """
    mkvmerge = find_tool("mkvmerge")
    cmd = [mkvmerge, "-o", str(out_path)]

    keep_sub_ids = [sid for sid in all_sub_ids if sid not in selected_ids]
    if keep_sub_ids:
        cmd += ["--subtitle-tracks", ",".join(str(i) for i in keep_sub_ids)]
    else:
        cmd += ["--no-subtitles"]

    cmd.append(str(mkv))

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

    order_parts = []
    for t in all_tracks:
        tid = t["id"]
        ttype = t.get("type", "")
        if tid in ass_file_index:
            order_parts.append(f"{ass_file_index[tid]}:0")
        elif ttype == "subtitles" and tid in selected_ids:
            pass
        else:
            order_parts.append(f"0:{tid}")

    if ttf_path is not None:
        mime = "font/otf" if ttf_path.suffix.lower() == ".otf" else "font/ttf"
        cmd += ["--attachment-mime-type", mime,
                "--attach-file", str(ttf_path)]

    cmd += ["--track-order", ",".join(order_parts)]

    subprocess.run(cmd, check=True)


# ──────────────────────────────────────────────────────────────────────────────
# Saída
# ──────────────────────────────────────────────────────────────────────────────

def output_dir_for(mkv_paths: list[Path]) -> Path:
    """Uma pasta 'styled' ao lado do primeiro MKV da fila."""
    return mkv_paths[0].parent / "styled"


def unique_output(folder: Path, mkv: Path, used: set[str]) -> Path:
    """Evita colisão quando dois MKVs de pastas diferentes têm o mesmo nome."""
    stem = mkv.stem + "_styled"
    candidate = stem
    if candidate.lower() in used:
        candidate = f"{mkv.parent.name}_{stem}"
        n = 2
        while candidate.lower() in used:
            candidate = f"{mkv.parent.name}_{stem}_{n}"
            n += 1
    used.add(candidate.lower())
    return folder / f"{candidate}.mkv"


# ──────────────────────────────────────────────────────────────────────────────
# UI de seleção no terminal
# ──────────────────────────────────────────────────────────────────────────────

def print_tracks(srt_tracks: list[dict]) -> None:
    print()
    print(f"  {paint('#', C.GRAY):<5}  {paint('ID', C.GRAY):<6}  {paint('Lang', C.GRAY):<8}  {paint('Nome', C.GRAY)}")
    print(rule())
    for i, t in enumerate(srt_tracks, 1):
        props = t.get("properties", {})
        lang = props.get("language", "und") or "und"
        name = props.get("track_name", "") or "—"
        forced = "  " + paint("forced", C.YELLOW) if props.get("forced_track") else ""
        default = "  " + paint("default", C.GREEN) if props.get("default_track") else ""
        print(f"  {paint(str(i), C.BOLD):<5}  {t['id']:<6}  {lang:<8}  {name}{forced}{default}")


def ask_selection(srt_tracks: list[dict], global_choice: str | None = None) -> tuple[list[int], str]:
    """Retorna os IDs selecionados e a decisão global ('all' ou 'manual')."""
    if global_choice == "all":
        info(f"Aplicando em todas as {len(srt_tracks)} track(s) SRT.")
        return [t["id"] for t in srt_tracks], "all"

    print_tracks(srt_tracks)
    print()

    if global_choice is None:
        resp = ask("Aplicar em TODAS as tracks deste e dos próximos? [S/n]:").lower()
        if resp in ("", "s", "sim", "y", "yes"):
            return [t["id"] for t in srt_tracks], "all"
        global_choice = "manual"

    print(paint("  Números separados por vírgula. Ex: 1,3", C.DIM))
    raw = ask("Tracks:")
    chosen = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(srt_tracks):
                chosen.append(srt_tracks[idx]["id"])
            else:
                warn(f"Número {part} inválido, ignorado.")
    if not chosen:
        warn("Nenhuma track válida. Este arquivo será pulado.")
    return chosen, global_choice


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mkv_paths: list[Path] = []
    ref_path = None
    ttf_path = None

    for arg in sys.argv[1:]:
        p = Path(arg)
        suffix = p.suffix.lower()
        if suffix == ".mkv":
            mkv_paths.append(p)
        elif suffix == ".ass":
            ref_path = p
        elif suffix in (".ttf", ".otf"):
            ttf_path = p

    banner()

    if not mkv_paths:
        err("Nenhum arquivo MKV fornecido.")
        sys.exit(1)
    if ref_path is None or not ref_path.is_file():
        err("Referência .ass inválida ou não encontrada.")
        sys.exit(1)
    if ttf_path is not None and not ttf_path.is_file():
        err(f"Fonte não encontrada: {ttf_path}")
        sys.exit(1)

    out_dir = output_dir_for(mkv_paths)
    out_dir.mkdir(parents=True, exist_ok=True)

    section("Fila")
    kv("Estilo", ref_path.name)
    kv("Fonte", ttf_path.name if ttf_path else "— não embedada")
    kv("Vídeos", str(len(mkv_paths)))
    kv("Saída", str(out_dir))

    fonts = extract_fonts_from_ass(ref_path)
    check_font(fonts, ttf_path)

    header = extract_header(ref_path)
    global_choice = None
    used_names: set[str] = set()
    done: list[Path] = []
    skipped: list[str] = []
    started = time.perf_counter()

    for idx, mkv_path in enumerate(mkv_paths, 1):
        section(f"[{idx}/{len(mkv_paths)}]  {mkv_path.name}")

        if not mkv_path.is_file():
            err(f"Arquivo não encontrado: {mkv_path}")
            skipped.append(mkv_path.name)
            continue

        try:
            tracks = get_tracks(mkv_path)
        except (RuntimeError, json.JSONDecodeError) as e:
            err(f"Não foi possível ler as tracks: {e}")
            skipped.append(mkv_path.name)
            continue

        srt_tracks = [t for t in tracks
                      if t.get("type") == "subtitles"
                      and t.get("properties", {}).get("codec_id") == "S_TEXT/UTF8"]
        all_sub_ids = [t["id"] for t in tracks if t.get("type") == "subtitles"]

        if not srt_tracks:
            warn("Nenhuma track SRT (S_TEXT/UTF8). Pulando.")
            skipped.append(mkv_path.name)
            continue

        selected_ids, global_choice = ask_selection(srt_tracks, global_choice)
        if not selected_ids:
            skipped.append(mkv_path.name)
            continue

        track_meta = {
            t["id"]: {
                "language":      t.get("properties", {}).get("language", ""),
                "name":          t.get("properties", {}).get("track_name", ""),
                "forced_track":  t.get("properties", {}).get("forced_track", False),
                "default_track": t.get("properties", {}).get("default_track", False),
            }
            for t in srt_tracks if t["id"] in selected_ids
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            print()
            info(f"Extraindo {len(selected_ids)} track(s)...")
            srt_files = extract_srts(mkv_path, selected_ids, tmp_dir)

            ass_files: dict[int, Path] = {}
            for tid, srt_path in srt_files.items():
                ass_path = tmp_dir / f"track_{tid}.ass"
                try:
                    count = convert_to_ass(srt_path, header, ass_path)
                    lang = track_meta[tid]["language"] or "und"
                    name = track_meta[tid]["name"] or "—"
                    ok(f"track {tid}  [{lang}]  {name}  ·  {count} linhas")
                    ass_files[tid] = ass_path
                except ValueError as e:
                    warn(f"track {tid}: {e}. Ignorada.")

            if not ass_files:
                warn("Nenhuma legenda pôde ser convertida.")
                skipped.append(mkv_path.name)
                continue

            out_path = unique_output(out_dir, mkv_path, used_names)
            if out_path.exists():
                warn(f"Substituindo {out_path.name}")
            print()
            info(f"Remuxando → {out_path.name}")
            try:
                remux(mkv_path, tracks, selected_ids, all_sub_ids, ass_files, track_meta, ttf_path, out_path)
            except subprocess.CalledProcessError:
                err(f"mkvmerge falhou em {mkv_path.name}")
                skipped.append(mkv_path.name)
                continue

        done.append(out_path)
        ok(f"Salvo em styled/{out_path.name}")

    elapsed = time.perf_counter() - started
    section("Resumo")
    kv("Pasta", str(out_dir))
    kv("Prontos", str(len(done)))
    kv("Pulados", str(len(skipped)))
    kv("Tempo", f"{elapsed:.1f}s")
    if done:
        print()
        for path in done:
            ok(path.name)
    if skipped:
        print()
        for name in skipped:
            warn(name)
    print()
    print(paint("  Fila encerrada.", C.BOLD, C.GREEN))
    print()


if __name__ == "__main__":
    main()
