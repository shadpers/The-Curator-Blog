#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKV Cover Tool - Adiciona capa (artwork) a múltiplos arquivos MKV
Detecta automaticamente a imagem e aplica em todos os MKVs
"""

import subprocess
import sys
import os
from pathlib import Path
from typing import List, Optional

# Configurações
MKVMERGE = r"C:\Program Files\MKVToolNix\mkvmerge.exe"

# Extensões de imagem suportadas
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}


def find_cover_image(files: List[str]) -> Optional[str]:
    """Encontra a primeira imagem nos arquivos fornecidos"""
    for file in files:
        ext = Path(file).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return file
    return None


def get_mkv_files(files: List[str]) -> List[str]:
    """Filtra apenas arquivos MKV"""
    return [f for f in files if Path(f).suffix.lower() == '.mkv']


def attach_cover(mkv_file: str, cover_image: str, output_dir: Path) -> bool:
    """
    Adiciona capa a um arquivo MKV
    Retorna True se bem-sucedido
    """
    input_path = Path(mkv_file)
    output_name = f"{input_path.stem}_cover.mkv"
    output_path = output_dir / output_name
    
    print(f"\n► Processando: {input_path.name}")
    
    # Monta comando mkvmerge
    # --attachment-mime-type e --attach-file para adicionar a capa
    cmd = [
        MKVMERGE,
        "-o", str(output_path),
        "--attachment-mime-type", "image/jpeg",
        "--attachment-name", "cover.jpg",
        "--attach-file", cover_image,
        str(input_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        print(f"  ✓ Salvo: {output_path.name}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"  ✗ ERRO ao processar {input_path.name}")
        print(f"  Comando: {' '.join(cmd)}")
        if e.stderr:
            print(f"  Erro: {e.stderr}")
        return False


def main():
    print("=" * 60)
    print("MKV COVER TOOL - Adicionar Capa Automaticamente")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\n[ERRO] Nenhum arquivo fornecido!")
        print("\nUso:")
        print("  Arraste arquivos MKV + uma imagem JPG sobre mkv_cover.bat")
        print("  OU execute: python mkv_cover.py arquivo1.mkv arquivo2.mkv capa.jpg")
        sys.exit(1)
    
    # Separa imagem e MKVs
    all_files = sys.argv[1:]
    
    cover_image = find_cover_image(all_files)
    if not cover_image:
        print("\n[ERRO] Nenhuma imagem encontrada!")
        print(f"Extensões suportadas: {', '.join(IMAGE_EXTENSIONS)}")
        sys.exit(1)
    
    mkv_files = get_mkv_files(all_files)
    if not mkv_files:
        print("\n[ERRO] Nenhum arquivo MKV encontrado!")
        sys.exit(1)
    
    # Mostra resumo
    print(f"\n[INFO] Capa encontrada:")
    print(f"  📷 {Path(cover_image).name}")
    
    print(f"\n[INFO] {len(mkv_files)} arquivo(s) MKV para processar:")
    for f in mkv_files:
        print(f"  🎬 {Path(f).name}")
    
    # Confirmação
    print("\n" + "=" * 60)
    confirm = input("Deseja prosseguir? (s/n): ").strip().lower()
    
    if confirm != 's':
        print("\n[INFO] Operação cancelada pelo usuário.")
        sys.exit(0)
    
    # Cria diretório de saída
    output_dir = Path(mkv_files[0]).parent / "mkv_cover_output"
    output_dir.mkdir(exist_ok=True)
    
    # Processa arquivos
    print("\n" + "=" * 60)
    print("PROCESSANDO ARQUIVOS")
    print("=" * 60)
    
    success_count = 0
    for mkv_file in mkv_files:
        if attach_cover(mkv_file, cover_image, output_dir):
            success_count += 1
    
    # Resumo final
    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"✓ {success_count}/{len(mkv_files)} arquivo(s) processado(s) com sucesso")
    
    if success_count > 0:
        print(f"\n📁 Arquivos salvos em:")
        print(f"  {output_dir}")
    
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Operação cancelada pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERRO CRÍTICO] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
