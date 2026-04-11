#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKV Remote Mux - Extrai faixas de audio, legenda e attachments de MKVs remotos via CDN
Backend: ffprobe (identificacao) + ffmpeg (mux)
HTTP Range Requests nativos -- sem baixar o arquivo completo.
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, unquote

# ─────────────────────────────────────────────
# CONFIGURACAO
# ─────────────────────────────────────────────
FFMPEG  = r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE = r"C:\ffmpeg\bin\ffprobe.exe"

HTTP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ─────────────────────────────────────────────
# UTILITARIOS
# ─────────────────────────────────────────────

def get_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name)
    return name if name.lower().endswith('.mkv') else "output.mkv"


def resolve_output_path(output_dir: Path, filename: str) -> Path:
    path = output_dir / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 1
    while path.exists():
        path = output_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return path


def print_separator(title: str = ""):
    line = "=" * 62
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)


def yn(prompt: str) -> bool:
    return input(f"  {prompt} (s/n) > ").strip().lower() == 's'


def check_tools():
    missing = []
    for name, path in [("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)]:
        try:
            subprocess.run([path, "-version"], capture_output=True, timeout=10)
        except FileNotFoundError:
            missing.append((name, path))
    if missing:
        print("\n[ERRO FATAL] Ferramentas nao encontradas:")
        for name, path in missing:
            print(f"  {name}: {path}")
        print("\nInstale o ffmpeg: https://ffmpeg.org/download.html")
        print("Ajuste FFMPEG/FFPROBE no topo do script.")
        sys.exit(1)


# ─────────────────────────────────────────────
# IDENTIFICACAO DE FAIXAS
# ─────────────────────────────────────────────

def identify_tracks(url: str) -> Optional[Dict]:
    print(f"  [URL] {url[:110]}{'...' if len(url) > 110 else ''}")

    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        "-user_agent", HTTP_UA,
        url
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', timeout=120
        )

        print(f"  [EXIT CODE] {result.returncode}")

        if result.stderr.strip():
            useful = [l for l in result.stderr.splitlines()
                      if any(k in l.lower() for k in ('error', 'invalid', 'fail', 'cannot', 'no such'))]
            if useful:
                print("  [STDERR relevante]")
                for line in useful[:10]:
                    print(f"    {line}")

        if not result.stdout.strip():
            print("  [STDOUT] (vazio)")
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON invalido: {e}")
            return None

        streams = data.get('streams', [])
        if not streams:
            print("  ✗ Nenhum stream encontrado")
            return None

        print(f"  ✓ OK -- {len(streams)} streams identificados")
        return data

    except subprocess.TimeoutExpired:
        print("  ✗ Timeout (120s)")
        return None
    except FileNotFoundError:
        print(f"\n[ERRO FATAL] ffprobe nao encontrado: {FFPROBE}")
        sys.exit(1)


def parse_tracks(info: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Retorna (audio_tracks, subtitle_tracks, attachments).

    attachments inclui:
      - codec_type='attachment'  => fontes, arquivos genericos
      - codec_type='video' + disposition.attached_pic=1  => capa (cover.jpg)
        Marcados com attached_pic=True para tratamento especial no mux.
    """
    audio_tracks    = []
    subtitle_tracks = []
    attachments     = []

    CODEC_MAP = {
        'aac': 'AAC', 'ac3': 'AC-3', 'eac3': 'E-AC-3',
        'dts': 'DTS', 'truehd': 'TrueHD', 'flac': 'FLAC',
        'mp3': 'MP3', 'opus': 'OPUS', 'vorbis': 'Vorbis',
        'subrip': 'SRT', 'ass': 'ASS', 'ssa': 'SSA',
        'hdmv_pgs_subtitle': 'PGS', 'dvd_subtitle': 'VobSub',
        'webvtt': 'WebVTT',
    }

    for stream in info.get('streams', []):
        codec_type  = stream.get('codec_type', '')
        idx         = stream.get('index', 0)
        tags        = stream.get('tags', {})
        disposition = stream.get('disposition', {})

        # Capa embedded (attached_pic) -- armazenada como stream de video
        if codec_type == 'video' and disposition.get('attached_pic', 0):
            attachments.append({
                'index':        idx,
                'filename':     tags.get('filename', f'cover_{idx}.jpg'),
                'mimetype':     tags.get('mimetype', 'image/jpeg'),
                'attached_pic': True,
            })
            continue

        # Attachments normais (fontes, etc.)
        if codec_type == 'attachment':
            attachments.append({
                'index':        idx,
                'filename':     tags.get('filename', f'attachment_{idx}'),
                'mimetype':     tags.get('mimetype', ''),
                'attached_pic': False,
            })
            continue

        if codec_type not in ('audio', 'subtitle'):
            continue

        codec_name = stream.get('codec_name', '?')
        codec_disp = CODEC_MAP.get(codec_name.lower(), codec_name.upper())
        lang       = tags.get('language', 'und')
        title      = tags.get('title', '') or tags.get('handler_name', '')

        entry = {
            'index':   idx,
            'lang':    lang,
            'name':    title,
            'codec':   codec_disp,
            'default': bool(disposition.get('default', 0)),
            'forced':  bool(disposition.get('forced', 0)),
        }

        if codec_type == 'audio':
            entry['channels'] = stream.get('channels', '')
            audio_tracks.append(entry)
        else:
            subtitle_tracks.append(entry)

    return audio_tracks, subtitle_tracks, attachments


def display_tracks(audio: List[Dict], subs: List[Dict], attachments: List[Dict], filename: str):
    print(f"\n  {filename}")
    print(f"  {'─' * 58}")

    print(f"  AUDIO  ({len(audio)} faixas):")
    if audio:
        for i, t in enumerate(audio):
            tags  = (" [DEFAULT]" if t['default'] else "") + (" [FORCED]" if t['forced'] else "")
            ch    = f" {t['channels']}ch" if t.get('channels') else ""
            label = f" | {t['name']}" if t['name'] else ""
            print(f"    [{i}] idx:{t['index']:>2}  {t['lang']:<8} {t['codec']:<16}{ch}{label}{tags}")
    else:
        print("    (nenhuma)")

    print(f"  LEGENDA ({len(subs)} faixas):")
    if subs:
        for i, t in enumerate(subs):
            tags  = (" [DEFAULT]" if t['default'] else "") + (" [FORCED]" if t['forced'] else "")
            label = f" | {t['name']}" if t['name'] else ""
            print(f"    [{i}] idx:{t['index']:>2}  {t['lang']:<8} {t['codec']:<16}{label}{tags}")
    else:
        print("    (nenhuma)")

    print(f"  ATTACHMENTS ({len(attachments)}):")
    if attachments:
        for i, a in enumerate(attachments):
            kind = " [capa]" if a.get('attached_pic') else ""
            mime = f" [{a['mimetype']}]" if a['mimetype'] else ""
            print(f"    [{i}] idx:{a['index']:>2}  {a['filename']}{kind}{mime}")
    else:
        print("    (nenhum)")


def tracks_are_compatible(all_info: List[Dict]) -> bool:
    if len(all_info) <= 1:
        return True
    ref_a = len(all_info[0]['audio'])
    ref_s = len(all_info[0]['subtitles'])
    return all(len(f['audio']) == ref_a and len(f['subtitles']) == ref_s for f in all_info[1:])


# ─────────────────────────────────────────────
# SELECAO INTERATIVA
# ─────────────────────────────────────────────

def _parse_selection(raw: str, count: int) -> List[int]:
    raw = raw.strip().lower()
    if not raw:
        return []
    if raw in ('all', 'a', 'todos'):
        return list(range(count))
    try:
        indices = [int(x.strip()) for x in raw.replace(';', ',').split(',')]
        return [i for i in indices if 0 <= i < count]
    except ValueError:
        print("  [!] Entrada invalida -- selecionando todas")
        return list(range(count))


def select_tracks(audio: List[Dict], subs: List[Dict]) -> Tuple[List[int], List[int]]:
    print()
    print("  Selecione faixas de AUDIO   (ex: 0,1  |  all  |  vazio = nenhuma):")
    sel_audio = _parse_selection(input("  Audio   > "), len(audio))
    print("  Selecione faixas de LEGENDA (ex: 0,2  |  all  |  vazio = nenhuma):")
    sel_subs  = _parse_selection(input("  Legenda > "), len(subs))
    return sel_audio, sel_subs


def ask_embed_attachments(has_attachments: bool) -> bool:
    """Pergunta se deve incluir attachments (fontes + capa) no MKV de saida."""
    if not has_attachments:
        return False
    print()
    print("  ATTACHMENTS detectados (fontes, capas, etc.)")
    return yn("  Incluir attachments no MKV de saida?")


# ─────────────────────────────────────────────
# MUXING
# ─────────────────────────────────────────────

def do_mux(
    url: str,
    filename: str,
    audio: List[Dict],
    subs: List[Dict],
    attachments: List[Dict],
    sel_audio: List[int],
    sel_subs: List[int],
    embed_attachments: bool,
    output_dir: Path
) -> bool:
    """
    Mux das faixas selecionadas + attachments opcionais.

    Fontes normais:  -map 0:t  (cobre todos os attachment streams)
    attached_pic:    -map 0:<idx> + -disposition:v:<n> attached_pic
                     Sem a disposition, o ffmpeg embute como faixa V_MJPEG comum.
    """
    output_path = resolve_output_path(output_dir, filename)

    map_args  = []
    disp_args = []

    for i in sel_audio:
        map_args += ["-map", f"0:{audio[i]['index']}"]
    for i in sel_subs:
        map_args += ["-map", f"0:{subs[i]['index']}"]

    if embed_attachments and attachments:
        normal_atts = [a for a in attachments if not a['attached_pic']]
        pics        = [a for a in attachments if a['attached_pic']]

        if normal_atts:
            map_args += ["-map", "0:t"]

        # Cada attached_pic precisa de -map explicito e disposition no output.
        # Como nao mapeamos o video principal, sao os unicos streams de video --
        # entao o indice de output comeca em v:0.
        for out_vid_idx, pic in enumerate(pics):
            map_args  += ["-map", f"0:{pic['index']}"]
            disp_args += [f"-disposition:v:{out_vid_idx}", "attached_pic"]
    else:
        normal_atts = []
        pics        = []

    if not map_args:
        print("  ⚠ Nenhuma faixa selecionada -- pulando")
        return False

    cmd = [
        FFMPEG,
        "-user_agent", HTTP_UA,
        "-i", url,
        *map_args,
        "-c", "copy",
        *disp_args,
        "-y",
        str(output_path)
    ]

    audio_labels = [f"{audio[i]['lang']} ({audio[i]['codec']})" for i in sel_audio] or ["nenhuma"]
    sub_labels   = [f"{subs[i]['lang']}  ({subs[i]['codec']})"  for i in sel_subs]  or ["nenhuma"]

    if embed_attachments and attachments:
        att_label = f"sim ({len(normal_atts)} fonte(s)"
        att_label += f" + {len(pics)} capa(s)" if pics else ""
        att_label += ")"
    else:
        att_label = "nao"

    print(f"  Audio:       {', '.join(audio_labels)}")
    print(f"  Legenda:     {', '.join(sub_labels)}")
    print(f"  Attachments: {att_label}")
    print(f"  Saida:       {output_path}")
    print()

    try:
        result = subprocess.run(cmd, text=True, encoding='utf-8')
        print(f"\n  [EXIT CODE] {result.returncode}")
        if result.returncode == 0 and output_path.exists():
            size = output_path.stat().st_size / (1024 * 1024)
            print(f"  ✓ Concluido -- {size:.1f} MB")
            return True
        else:
            print(f"  ✗ ffmpeg encerrou com erro (codigo {result.returncode})")
            return False
    except Exception as e:
        print(f"\n  ✗ Excecao durante o mux: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def collect_urls() -> List[str]:
    if len(sys.argv) > 1:
        return [u for u in sys.argv[1:] if u.startswith('http')]

    print("\nCole os links CDN (um por linha -- linha vazia para continuar):")
    urls = []
    while True:
        line = input("  URL > ").strip()
        if not line:
            break
        if line.startswith('http'):
            urls.append(line)
        else:
            print("  [!] Ignorado -- nao parece uma URL valida")
    return urls


def main():
    print_separator()
    print("  MKV REMOTE MUX -- Extracao de Faixas via CDN")
    print("  Backend: ffprobe + ffmpeg | HTTP Range Requests")
    print_separator()

    check_tools()

    urls = collect_urls()
    if not urls:
        print("\n[ERRO] Nenhuma URL fornecida!")
        sys.exit(1)

    print(f"\n  {len(urls)} URL(s) recebida(s)")

    # ── Identificacao ──────────────────────────────────────
    print_separator("IDENTIFICANDO FAIXAS")

    all_info: List[Dict] = []

    for url in urls:
        filename = get_filename_from_url(url)
        print(f"\n► {filename}")

        raw = identify_tracks(url)
        if not raw:
            print("  ✗ Pulando este arquivo")
            continue

        audio, subs, attachments = parse_tracks(raw)
        display_tracks(audio, subs, attachments, filename)

        all_info.append({
            'url':         url,
            'filename':    filename,
            'audio':       audio,
            'subtitles':   subs,
            'attachments': attachments,
        })

    if not all_info:
        print("\n[ERRO] Nenhum arquivo pode ser identificado. Encerrando.")
        sys.exit(1)

    # ── Modo batch vs individual ───────────────────────────
    print_separator("MODO DE SELECAO")

    use_batch  = False
    compatible = tracks_are_compatible(all_info)

    if len(all_info) > 1:
        if compatible:
            print(f"\n  ✓ Todos os {len(all_info)} arquivos tem o mesmo layout de faixas.")
            print("  Aplicar a mesma selecao para todos? (s = batch / n = individual):")
            use_batch = input("  > ").strip().lower() == 's'
        else:
            print(f"\n  ⚠ Layouts diferentes -- modo individual obrigatorio.")

    # ── Selecao e muxing ────────────────────────────────────
    print_separator("SELECAO E MUXING")

    output_dir  = Path.cwd()
    batch_audio = None
    batch_subs  = None
    batch_embed = None
    success     = 0

    if use_batch:
        ref = all_info[0]
        print(f"\n  Referencia: {ref['filename']}")
        display_tracks(ref['audio'], ref['subtitles'], ref['attachments'], "Todos os arquivos")
        batch_audio, batch_subs = select_tracks(ref['audio'], ref['subtitles'])
        has_att     = any(len(f['attachments']) > 0 for f in all_info)
        batch_embed = ask_embed_attachments(has_att)

    for file_info in all_info:
        print(f"\n  ► {file_info['filename']}")
        if use_batch:
            sel_a, sel_s = batch_audio, batch_subs
            embed        = batch_embed
        else:
            display_tracks(file_info['audio'], file_info['subtitles'],
                           file_info['attachments'], file_info['filename'])
            sel_a, sel_s = select_tracks(file_info['audio'], file_info['subtitles'])
            embed        = ask_embed_attachments(len(file_info['attachments']) > 0)

        if do_mux(
            file_info['url'],
            file_info['filename'],
            file_info['audio'],
            file_info['subtitles'],
            file_info['attachments'],
            sel_a, sel_s,
            embed,
            output_dir
        ):
            success += 1

    # ── Resultado ───────────────────────────────────────────
    print_separator("RESULTADO")
    print(f"  ✓ {success}/{len(all_info)} arquivo(s) processado(s) com sucesso")
    print(f"  Salvos em: {output_dir}")
    print_separator()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Operacao cancelada pelo usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERRO CRITICO] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
