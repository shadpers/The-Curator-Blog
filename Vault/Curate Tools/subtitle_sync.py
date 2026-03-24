#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subtitle Sync Tool - Extrai e modifica legendas de múltiplos arquivos MKV
Aplica delay e stretch em legendas selecionadas mantendo metadados
"""

import subprocess
import sys
import json
import os
from pathlib import Path
from typing import List, Dict, Tuple, Set

# Configurações
MKVMERGE = r"C:\Program Files\MKVToolNix\mkvmerge.exe"
MKVEXTRACT = r"C:\Program Files\MKVToolNix\mkvextract.exe"


class SubtitleInfo:
    """Informações de uma faixa de legenda"""
    def __init__(self, track_id: int, language: str, title: str, codec: str):
        self.track_id = track_id
        self.language = language
        self.title = title.strip('[] \t')  # normalize stray brackets/whitespace in track names
        self.codec = codec
    
    def __repr__(self):
        return f"#{self.track_id} [{self.language}] {self.title} ({self.codec})"
    
    def __eq__(self, other):
        if not isinstance(other, SubtitleInfo):
            return False
        return (self.language == other.language and 
                self.title == other.title and 
                self.codec == other.codec)
    
    def __hash__(self):
        return hash((self.language, self.title, self.codec))


def get_subtitle_tracks(mkv_path: str) -> List[SubtitleInfo]:
    """Extrai informações das faixas de legenda de um arquivo MKV"""
    try:
        result = subprocess.run(
            [MKVMERGE, "-J", mkv_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        
        data = json.loads(result.stdout)
        subtitles = []
        
        for track in data.get('tracks', []):
            if track['type'] == 'subtitles':
                track_id = track['id']
                language = track['properties'].get('language', 'und')
                title = track['properties'].get('track_name', '')
                codec = track['codec']
                
                subtitles.append(SubtitleInfo(track_id, language, title, codec))
        
        return subtitles
    
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Falha ao analisar {mkv_path}")
        print(f"Erro: {e.stderr}")
        return []
    except json.JSONDecodeError:
        print(f"[ERRO] Falha ao decodificar JSON de {mkv_path}")
        return []


def compare_subtitles(files: List[str]) -> Tuple[bool, List[SubtitleInfo]]:
    """
    Verifica se todos os arquivos têm as mesmas legendas
    Retorna (são_iguais, lista_de_legendas)
    """
    print("\n[INFO] Verificando consistência das legendas...\n")
    
    all_subs = {}
    
    for mkv_file in files:
        filename = Path(mkv_file).name
        subs = get_subtitle_tracks(mkv_file)
        
        if not subs:
            print(f"[AVISO] {filename}: Nenhuma legenda encontrada")
            return False, []
        
        all_subs[mkv_file] = subs
        print(f"✓ {filename}: {len(subs)} legendas")
    
    # Compara quantidade
    subtitle_counts = [len(subs) for subs in all_subs.values()]
    if len(set(subtitle_counts)) > 1:
        print("\n[ERRO] Os arquivos têm quantidades diferentes de legendas!")
        for mkv_file, subs in all_subs.items():
            print(f"  {Path(mkv_file).name}: {len(subs)} legendas")
        return False, []
    
    # Compara ordem e conteúdo
    reference_subs = list(all_subs.values())[0]
    for mkv_file, subs in all_subs.items():
        if subs != reference_subs:
            print(f"\n[ERRO] Legendas diferentes em: {Path(mkv_file).name}")
            print("\nReferência:")
            for i, sub in enumerate(reference_subs):
                print(f"  {i}: {sub}")
            print(f"\n{Path(mkv_file).name}:")
            for i, sub in enumerate(subs):
                print(f"  {i}: {sub}")
            return False, []
    
    print("\n✓ Todos os arquivos têm as mesmas legendas!\n")
    return True, reference_subs


def parse_selection(selection: str, max_index: int) -> Set[int]:
    """
    Converte entrada do usuário em conjunto de índices
    Aceita: "1,2,3" ou "1-4" ou combinações "1,3-5,7"
    """
    indices = set()
    
    for part in selection.split(','):
        part = part.strip()
        
        if '-' in part:
            # Range: 1-4
            try:
                start, end = map(int, part.split('-'))
                if start < 0 or end >= max_index or start > end:
                    raise ValueError
                indices.update(range(start, end + 1))
            except ValueError:
                print(f"[AVISO] Range inválido ignorado: {part}")
        else:
            # Número único
            try:
                idx = int(part)
                if 0 <= idx < max_index:
                    indices.add(idx)
                else:
                    print(f"[AVISO] Índice fora do range ignorado: {idx}")
            except ValueError:
                print(f"[AVISO] Valor inválido ignorado: {part}")
    
    return indices


def get_user_selections(subtitles: List[SubtitleInfo]) -> Tuple[Set[int], int, float]:
    """Coleta seleções do usuário: tracks, delay e stretch"""
    
    # Mostra legendas disponíveis
    print("=" * 60)
    print("LEGENDAS DISPONÍVEIS")
    print("=" * 60)
    for i, sub in enumerate(subtitles):
        print(f"{i:2d}: {sub}")
    print("=" * 60)
    
    # Seleciona tracks
    while True:
        print("\nQuais legendas deseja modificar?")
        print("Exemplos: '0,1,2' ou '0-5' ou '1,3-7,9'")
        print("Digite 'all' ou '*' para selecionar TODAS")
        selection = input("Seleção: ").strip()
        
        if not selection:
            print("[ERRO] Seleção vazia!")
            continue
        
        # Verifica se quer todas
        if selection.lower() in ['all', '*', 'todas', 'todos']:
            selected = set(range(len(subtitles)))
            print(f"\n✓ TODAS as {len(selected)} legendas selecionadas")
        else:
            selected = parse_selection(selection, len(subtitles))
            
            if not selected:
                print("[ERRO] Nenhuma legenda válida selecionada!")
                continue
            
            print(f"\n✓ {len(selected)} legenda(s) selecionada(s):")
            for idx in sorted(selected):
                print(f"  {idx}: {subtitles[idx]}")
        
        confirm = input("\nConfirmar? (s/n): ").strip().lower()
        if confirm == 's':
            break
    
    # Delay
    while True:
        print("\n" + "=" * 60)
        print("DELAY (em milissegundos)")
        print("=" * 60)
        print("Exemplos: -3000 (atrasa 3s), 1500 (adianta 1.5s), 0 (sem delay)")
        delay_str = input("Delay (ms): ").strip()
        
        try:
            delay = int(delay_str)
            print(f"✓ Delay: {delay}ms")
            break
        except ValueError:
            print("[ERRO] Valor inválido! Digite um número inteiro.")
    
    # Stretch
    while True:
        print("\n" + "=" * 60)
        print("STRETCH (multiplicador de tempo)")
        print("=" * 60)
        print("Exemplos:")
        print("  1.001001 (alonga levemente)")
        print("  0.999    (encurta levemente)")
        print("  1.0      (sem alteração)")
        stretch_str = input("Stretch: ").strip()
        
        try:
            stretch = float(stretch_str)
            if stretch <= 0:
                print("[ERRO] Stretch deve ser maior que 0!")
                continue
            print(f"✓ Stretch: {stretch}")
            break
        except ValueError:
            print("[ERRO] Valor inválido! Digite um número (use . para decimal).")
    
    return selected, delay, stretch


def process_files(files: List[str], selected_indices: Set[int], 
                  delay: int, stretch: float, subtitles: List[SubtitleInfo]):
    """Processa todos os arquivos aplicando sync nas legendas selecionadas"""
    
    output_dir = Path(files[0]).parent / "subtitle_sync_output"
    output_dir.mkdir(exist_ok=True)
    
    print("\n" + "=" * 60)
    print("PROCESSANDO ARQUIVOS")
    print("=" * 60)
    
    for mkv_file in files:
        input_path = Path(mkv_file)
        output_name = f"{input_path.stem}_synced.mkv"
        output_path = output_dir / output_name
        
        print(f"\n► Processando: {input_path.name}")
        
        # Monta comando mkvmerge
        cmd = [MKVMERGE, "-o", str(output_path)]
        
        # NÃO incluir vídeo nem áudio (apenas legendas)
        cmd.extend(["-D", "-A"])  # -D = sem vídeo, -A = sem áudio
        
        # Mantém apenas as legendas selecionadas
        selected_track_ids = [str(subtitles[idx].track_id) for idx in selected_indices]
        cmd.extend(["-s", ",".join(selected_track_ids)])
        
        # Aplica sync nas tracks selecionadas
        for idx in selected_indices:
            track_id = subtitles[idx].track_id
            sync_param = f"{track_id}:{delay},{stretch}"
            cmd.extend(["--sync", sync_param])
        
        # Arquivo de entrada
        cmd.append(str(input_path))
        
        # Executa
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=True
            )
            print(f"  ✓ Salvo: {output_path.name}")
        
        except subprocess.CalledProcessError as e:
            print(f"  ✗ ERRO ao processar {input_path.name}")
            print(f"  Comando: {' '.join(cmd)}")
            print(f"  Erro: {e.stderr}")
    
    print("\n" + "=" * 60)
    print(f"✓ CONCLUÍDO! Arquivos salvos em:")
    print(f"  {output_dir}")
    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("[ERRO] Nenhum arquivo fornecido!")
        print("\nUso:")
        print("  Arraste arquivos MKV sobre subtitle_sync.bat")
        print("  OU execute: python subtitle_sync.py arquivo1.mkv arquivo2.mkv ...")
        sys.exit(1)
    
    # Coleta arquivos
    mkv_files = [f for f in sys.argv[1:] if f.lower().endswith('.mkv')]
    
    if not mkv_files:
        print("[ERRO] Nenhum arquivo MKV válido encontrado!")
        sys.exit(1)
    
    print(f"\n[INFO] {len(mkv_files)} arquivo(s) recebido(s)")
    for f in mkv_files:
        print(f"  - {Path(f).name}")
    
    # Verifica consistência
    consistent, subtitles = compare_subtitles(mkv_files)
    
    if not consistent:
        print("\n[ERRO] Os arquivos não têm legendas consistentes!")
        print("Todos os arquivos devem ter as mesmas legendas na mesma ordem.")
        sys.exit(1)
    
    if not subtitles:
        print("\n[ERRO] Nenhuma legenda encontrada nos arquivos!")
        sys.exit(1)
    
    # Coleta parâmetros do usuário
    selected_indices, delay, stretch = get_user_selections(subtitles)
    
    # Processa arquivos
    process_files(mkv_files, selected_indices, delay, stretch, subtitles)


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