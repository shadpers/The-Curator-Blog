#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKV Cover Tool - Adiciona/substitui/extrai capa em arquivos MKV

Modos (automáticos, conforme o que for arrastado):
  • MKVs + imagem  -> adiciona/substitui a capa via mkvpropedit (in-place, sem remux)
  • Só MKVs/pastas -> extrai as capas dos MKVs via mkvextract
"""

import subprocess
import sys
import os
import json
import ctypes
from pathlib import Path
from typing import List, Optional, Tuple

# Habilita ANSI no terminal Windows
try:
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

MKVPROPEDIT_PATH = r"C:\Program Files\MKVToolNix\mkvpropedit.exe"
MKVMERGE_PATH    = r"C:\Program Files\MKVToolNix\mkvmerge.exe"
MKVEXTRACT_PATH  = r"C:\Program Files\MKVToolNix\mkvextract.exe"

# Ao soltar uma pasta, procurar MKVs também nas subpastas?
RECURSIVE_FOLDERS = True

# Mime types reconhecidos como capa
COVER_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

# Extensão usada na extração quando o attachment não tem extensão no nome
MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/bmp":  ".bmp",
}

# Cores ANSI
WHITE  = "\033[97m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SEP  = f"{DIM}{'─' * 60}{RESET}"
SEP2 = f"{DIM}{'═' * 60}{RESET}"

def colored(text, color):
    return f"{color}{text}{RESET}{WHITE}"

def bold(text):
    return f"{BOLD}{WHITE}{text}{RESET}{WHITE}"

def dim(text):
    return f"{DIM}{text}{RESET}{WHITE}"

# ─────────────────────────────────────────────
# Helpers de arquivo
# ─────────────────────────────────────────────

def find_cover_image(files: List[str]) -> Optional[str]:
    for f in files:
        p = Path(f)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            return f
    return None

def get_mkv_files(files: List[str]) -> List[str]:
    """
    Recebe os itens arrastados (arquivos e/ou pastas) e devolve a lista de MKVs.
    Pastas são varridas (com subpastas se RECURSIVE_FOLDERS = True).
    """
    found: List[str] = []
    for f in files:
        p = Path(f)
        if p.is_dir():
            pattern = "**/*" if RECURSIVE_FOLDERS else "*"
            for sub in sorted(p.glob(pattern)):
                if sub.is_file() and sub.suffix.lower() == ".mkv":
                    found.append(str(sub))
        elif p.is_file() and p.suffix.lower() == ".mkv":
            found.append(str(p))

    # Remove duplicatas preservando a ordem
    seen = set()
    unique = []
    for f in found:
        key = os.path.normcase(os.path.abspath(f))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique

def unique_path(path: Path) -> Path:
    """Se o arquivo já existir, acrescenta _2, _3... ao nome."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1

# ─────────────────────────────────────────────
# Leitura de attachments via mkvmerge -J
# ─────────────────────────────────────────────

def get_attachments(mkv_file: str) -> List[dict]:
    """Retorna lista de attachments do arquivo MKV."""
    result = subprocess.run(
        [MKVMERGE_PATH, "-J", mkv_file],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="ignore"
    )
    try:
        data = json.loads(result.stdout)
        return data.get("attachments", [])
    except Exception:
        return []

def find_cover_attachments(attachments: List[dict]) -> List[dict]:
    """Filtra attachments que são imagens (capas)."""
    covers = []
    for att in attachments:
        mime = att.get("content_type", "").lower()
        if mime in COVER_MIMES:
            covers.append(att)
    return covers

def find_extractable_covers(attachments: List[dict]) -> List[dict]:
    """
    Para extração: além do mime type, aceita attachments cujo NOME é de imagem
    (alguns MKVs trazem a capa como application/octet-stream).
    """
    covers = []
    for att in attachments:
        mime = att.get("content_type", "").lower()
        ext = Path(att.get("file_name", "") or "").suffix.lower()
        if mime in COVER_MIMES or ext in IMAGE_EXTENSIONS:
            covers.append(att)
    return covers

# ─────────────────────────────────────────────
# Modo 1: adicionar/substituir capa
# ─────────────────────────────────────────────

def process_file(mkv_file: str, cover_image: str, index: int, total: int) -> bool:
    """
    Remove capas existentes e adiciona a nova via mkvpropedit.
    Retorna True se bem-sucedido.
    """
    input_path = Path(mkv_file)
    cover_path = Path(cover_image)

    print(f"\n{WHITE}  {dim('[' + str(index) + '/' + str(total) + ']')} {bold(input_path.name)}{RESET}")

    # ── Etapa 1: Verifica attachments existentes ──────────────────────────
    attachments = get_attachments(mkv_file)
    covers_found = find_cover_attachments(attachments)

    cmd = [MKVPROPEDIT_PATH, mkv_file]

    if covers_found:
        names = [att.get("file_name", "?") for att in covers_found]
        print(f"{WHITE}    {colored('⚠ Capa(s) existente(s) encontrada(s):', YELLOW)} "
              f"{dim(', '.join(names))}{RESET}")
        for att in covers_found:
            att_id = att.get("id")
            if att_id is not None:
                cmd += ["--delete-attachment", str(att_id)]
        print(f"{WHITE}    {dim('→ Serão removidas antes de adicionar a nova.')}{RESET}")
    else:
        print(f"{WHITE}    {dim('Nenhuma capa prévia detectada.')}{RESET}")

    # ── Etapa 2: Adiciona nova capa ───────────────────────────────────────
    mime = "image/jpeg" if cover_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"

    cmd += [
        "--attachment-name",      cover_path.name,
        "--attachment-mime-type", mime,
        "--add-attachment",       str(cover_path),
    ]

    print(f"{WHITE}    {dim('Aplicando: ' + cover_path.name + ' (' + mime + ')...')}{RESET}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="ignore"
        )

        if result.returncode == 0:
            print(f"{WHITE}    {colored('✔ Concluído', GREEN)}{RESET}")
            return True
        else:
            print(f"{WHITE}    {colored('✘ Erro ao processar', RED)}{RESET}")
            if result.stderr:
                print(f"{WHITE}    {dim(result.stderr.strip())}{RESET}")
            return False

    except FileNotFoundError:
        print(f"{WHITE}    {colored('✘ mkvpropedit não encontrado!', RED)}")
        print(f"    {dim('Verifique: ' + MKVPROPEDIT_PATH)}{RESET}")
        return False

# ─────────────────────────────────────────────
# Modo 2: extrair capas
# ─────────────────────────────────────────────

def extract_covers(mkv_file: str, index: int, total: int) -> Tuple[str, int]:
    """
    Extrai as capas de um MKV via mkvextract, salvando ao lado do MKV
    como '<nome_do_mkv>_cover.<ext>'.
    Retorna (status, qtd) onde status ∈ {"ok", "none", "error"}.
    """
    input_path = Path(mkv_file)
    print(f"\n{WHITE}  {dim('[' + str(index) + '/' + str(total) + ']')} {bold(input_path.name)}{RESET}")

    attachments = get_attachments(mkv_file)
    covers = find_extractable_covers(attachments)

    if not covers:
        print(f"{WHITE}    {colored('— Nenhuma capa encontrada', YELLOW)}{RESET}")
        return "none", 0

    jobs = []   # (att_id, out_path)
    reserved = set()
    for att in covers:
        att_id = att.get("id")
        if att_id is None:
            continue

        # Define a extensão: pelo nome do attachment, ou pelo mime
        ext = Path(att.get("file_name", "") or "").suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = MIME_TO_EXT.get(att.get("content_type", "").lower(), ".jpg")

        out_path = unique_path(input_path.with_name(f"{input_path.stem}_cover{ext}"))
        # Evita colisão entre duas capas do mesmo MKV na mesma execução
        while out_path in reserved:
            out_path = unique_path(out_path.with_name(f"{out_path.stem}_x{out_path.suffix}"))
        reserved.add(out_path)
        jobs.append((att_id, out_path, att.get("file_name", "?")))

    if not jobs:
        print(f"{WHITE}    {colored('— Nenhuma capa encontrada', YELLOW)}{RESET}")
        return "none", 0

    cmd = [MKVEXTRACT_PATH, "attachments", mkv_file]
    for att_id, out_path, _ in jobs:
        cmd.append(f"{att_id}:{out_path}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="ignore"
        )
    except FileNotFoundError:
        print(f"{WHITE}    {colored('✘ mkvextract não encontrado!', RED)}")
        print(f"    {dim('Verifique: ' + MKVEXTRACT_PATH)}{RESET}")
        return "error", 0

    if result.returncode in (0, 1):  # 1 = só avisos no mkvextract
        done = 0
        for _, out_path, original_name in jobs:
            if out_path.exists():
                done += 1
                print(f"{WHITE}    {colored('✔', GREEN)} {dim(original_name + ' → ' + out_path.name)}{RESET}")
        if done:
            return "ok", done

    print(f"{WHITE}    {colored('✘ Erro ao extrair', RED)}{RESET}")
    msg = (result.stderr or result.stdout or "").strip()
    if msg:
        print(f"{WHITE}    {dim(msg)}{RESET}")
    return "error", 0

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def run_add_mode(mkv_files: List[str], cover_image: str):
    # ── Resumo ────────────────────────────────
    print(f"\n{WHITE}  {bold('Modo:')} {colored('ADICIONAR / SUBSTITUIR CAPA', CYAN)}")
    print(f"\n  {bold('Capa:')}")
    print(f"  {colored('📷', CYAN)} {dim(Path(cover_image).name)}")
    print(f"\n  {bold(str(len(mkv_files)) + ' arquivo(s) MKV:')}")
    for f in mkv_files:
        print(f"  {colored('🎬', CYAN)} {dim(Path(f).name)}")

    print(f"\n{SEP2}")

    # ── Confirmação ───────────────────────────
    resp = input(f"{WHITE}  {bold('Prosseguir?')} {colored('[S/N]', CYAN)}: {RESET}").strip().upper()
    if resp != "S":
        print(f"{WHITE}  {dim('Operação cancelada.')}{RESET}\n")
        return

    # ── Processamento ─────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('PROCESSANDO ' + str(len(mkv_files)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)

    success = 0
    failed  = 0
    for i, mkv in enumerate(mkv_files, 1):
        if process_file(mkv, cover_image, i, len(mkv_files)):
            success += 1
        else:
            failed += 1

    # ── Resumo final ──────────────────────────
    print(f"\n{SEP2}")
    s_str = colored(f"{success} OK", GREEN)
    f_str = colored(f"{failed} erro(s)", RED) if failed else dim("0 erro(s)")
    print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {f_str}{RESET}")
    print(f"{SEP2}\n")


def run_extract_mode(mkv_files: List[str]):
    # ── Resumo ────────────────────────────────
    print(f"\n{WHITE}  {bold('Modo:')} {colored('EXTRAIR CAPAS', CYAN)}")
    print(f"\n  {bold(str(len(mkv_files)) + ' arquivo(s) MKV:')}")
    for f in mkv_files:
        print(f"  {colored('🎬', CYAN)} {dim(Path(f).name)}")
    print(f"\n  {dim('As capas serão salvas ao lado de cada MKV (<nome>_cover.<ext>).')}")

    print(f"\n{SEP2}")

    # ── Confirmação ───────────────────────────
    resp = input(f"{WHITE}  {bold('Prosseguir?')} {colored('[S/N]', CYAN)}: {RESET}").strip().upper()
    if resp != "S":
        print(f"{WHITE}  {dim('Operação cancelada.')}{RESET}\n")
        return

    # ── Processamento ─────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('EXTRAINDO DE ' + str(len(mkv_files)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)

    extracted_files = 0   # MKVs de onde saiu capa
    extracted_imgs  = 0   # total de imagens salvas
    no_cover        = 0
    failed          = 0
    for i, mkv in enumerate(mkv_files, 1):
        status, qty = extract_covers(mkv, i, len(mkv_files))
        if status == "ok":
            extracted_files += 1
            extracted_imgs += qty
        elif status == "none":
            no_cover += 1
        else:
            failed += 1

    # ── Resumo final ──────────────────────────
    print(f"\n{SEP2}")
    s_str = colored(f"{extracted_imgs} capa(s) de {extracted_files} MKV(s)", GREEN)
    n_str = colored(f"{no_cover} sem capa", YELLOW) if no_cover else dim("0 sem capa")
    f_str = colored(f"{failed} erro(s)", RED) if failed else dim("0 erro(s)")
    print(f"{WHITE}  {bold('CONCLUÍDO:')}  {s_str}  |  {n_str}  |  {f_str}{RESET}")
    print(f"{SEP2}\n")


def main():
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('MKV COVER TOOL', CYAN))}{RESET}")
    print(SEP2)

    if len(sys.argv) < 2:
        print(f"{WHITE}  Arraste arquivos MKV + uma imagem sobre o .bat para {bold('adicionar')} a capa.")
        print(f"  Arraste só MKVs (ou uma pasta) para {bold('extrair')} as capas.{RESET}\n")
        return

    all_args = sys.argv[1:]

    cover_image = find_cover_image(all_args)
    mkv_files = get_mkv_files(all_args)

    if not mkv_files:
        print(f"{WHITE}  {colored('✘ Nenhum arquivo MKV encontrado!', RED)}{RESET}\n")
        return

    if cover_image:
        run_add_mode(mkv_files, cover_image)
    else:
        run_extract_mode(mkv_files)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{WHITE}  {dim('Operação cancelada pelo usuário.')}{RESET}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n{WHITE}  {colored('✘ ERRO CRÍTICO:', RED)} {type(e).__name__}: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
