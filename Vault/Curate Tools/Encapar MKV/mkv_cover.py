#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKV Cover Tool - Adiciona/substitui capa em arquivos MKV via mkvpropedit
Edita in-place: sem remux, sem metadados extras.
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

# Mime types reconhecidos como capa
COVER_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

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
        if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
            return f
    return None

def get_mkv_files(files: List[str]) -> List[str]:
    return [f for f in files if Path(f).suffix.lower() == '.mkv']

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

# ─────────────────────────────────────────────
# Processamento
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
# Main
# ─────────────────────────────────────────────

def main():
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('MKV COVER TOOL', CYAN))}{RESET}")
    print(SEP2)

    if len(sys.argv) < 2:
        print(f"{WHITE}  Arraste arquivos MKV + uma imagem sobre o .bat.{RESET}\n")
        return

    all_files = sys.argv[1:]

    cover_image = find_cover_image(all_files)
    if not cover_image:
        print(f"{WHITE}  {colored('✘ Nenhuma imagem encontrada!', RED)}")
        print(f"  {dim('Extensões suportadas: ' + ', '.join(IMAGE_EXTENSIONS))}{RESET}\n")
        return

    mkv_files = get_mkv_files(all_files)
    if not mkv_files:
        print(f"{WHITE}  {colored('✘ Nenhum arquivo MKV encontrado!', RED)}{RESET}\n")
        return

    # ── Resumo ────────────────────────────────
    print(f"\n{WHITE}  {bold('Capa:')}")
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
