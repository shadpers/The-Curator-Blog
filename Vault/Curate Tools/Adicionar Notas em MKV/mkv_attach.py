#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKV Attach Tool - Adiciona/substitui arquivos de texto (.txt/.md) em MKVs via mkvpropedit
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

# Mime types reconhecidos como texto
TEXT_MIMES = {"text/plain", "text/markdown"}
TEXT_EXTENSIONS = {'.txt', '.md'}

MIME_MAP = {
    '.txt': 'text/plain',
    '.md':  'text/markdown',
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

def find_text_file(files: List[str]) -> Optional[str]:
    for f in files:
        if Path(f).suffix.lower() in TEXT_EXTENSIONS:
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

def find_text_attachments(attachments: List[dict]) -> List[dict]:
    """Filtra attachments que são arquivos de texto."""
    found = []
    for att in attachments:
        mime = att.get("content_type", "").lower()
        name = att.get("file_name", "")
        if mime in TEXT_MIMES or Path(name).suffix.lower() in TEXT_EXTENSIONS:
            found.append(att)
    return found

# ─────────────────────────────────────────────
# Processamento
# ─────────────────────────────────────────────

def process_file(mkv_file: str, text_file: str, index: int, total: int) -> bool:
    """
    Remove attachments de texto existentes e adiciona o novo via mkvpropedit.
    Retorna True se bem-sucedido.
    """
    input_path = Path(mkv_file)
    attach_path = Path(text_file)

    print(f"\n{WHITE}  {dim('[' + str(index) + '/' + str(total) + ']')} {bold(input_path.name)}{RESET}")

    # ── Etapa 1: Verifica attachments existentes ──────────────────────────
    attachments = get_attachments(mkv_file)
    text_found  = find_text_attachments(attachments)

    cmd = [MKVPROPEDIT_PATH, mkv_file]

    if text_found:
        names = [att.get("file_name", "?") for att in text_found]
        print(f"{WHITE}    {colored('⚠ Attachment(s) de texto existente(s):', YELLOW)} "
              f"{dim(', '.join(names))}{RESET}")
        for att in text_found:
            att_id = att.get("id")
            if att_id is not None:
                cmd += ["--delete-attachment", str(att_id)]
        print(f"{WHITE}    {dim('→ Serão removidos antes de adicionar o novo.')}{RESET}")
    else:
        print(f"{WHITE}    {dim('Nenhum attachment de texto prévio detectado.')}{RESET}")

    # ── Etapa 2: Adiciona novo attachment ─────────────────────────────────
    mime = MIME_MAP.get(attach_path.suffix.lower(), "text/plain")

    cmd += [
        "--attachment-name",      attach_path.name,
        "--attachment-mime-type", mime,
        "--add-attachment",       str(attach_path),
    ]

    print(f"{WHITE}    {dim('Aplicando: ' + attach_path.name + ' (' + mime + ')...')}{RESET}")

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
    print(f"{WHITE}  {bold(colored('MKV ATTACH TOOL', CYAN))}{RESET}")
    print(SEP2)

    if len(sys.argv) < 2:
        print(f"{WHITE}  Arraste arquivos MKV + um arquivo .txt/.md sobre o .bat.{RESET}\n")
        return

    all_files = sys.argv[1:]

    text_file = find_text_file(all_files)
    if not text_file:
        print(f"{WHITE}  {colored('✘ Nenhum arquivo de texto encontrado!', RED)}")
        print(f"  {dim('Extensões suportadas: ' + ', '.join(TEXT_EXTENSIONS))}{RESET}\n")
        return

    mkv_files = get_mkv_files(all_files)
    if not mkv_files:
        print(f"{WHITE}  {colored('✘ Nenhum arquivo MKV encontrado!', RED)}{RESET}\n")
        return

    # ── Resumo ────────────────────────────────
    print(f"\n{WHITE}  {bold('Attachment:')}")
    print(f"  {colored('📄', CYAN)} {dim(Path(text_file).name)}")
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
        if process_file(mkv, text_file, i, len(mkv_files)):
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
