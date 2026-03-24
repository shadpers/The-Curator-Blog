#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mass Mux Tool v2 - Muxing em massa de episódios de anime
Combina vídeo, áudio e legendas de múltiplas pastas aplicando configurações uniformes
"""

import subprocess
import sys
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

# Configurações
MKVMERGE = r"C:\Program Files\MKVToolNix\mkvmerge.exe"
MKVEXTRACT = r"C:\Program Files\MKVToolNix\mkvextract.exe"
CONFIG_FILE = "last_config.json"


@dataclass
class TrackInfo:
    """Informações de uma faixa (vídeo/áudio/legenda)"""
    track_id: int
    track_type: str  # 'video', 'audio', 'subtitles'
    codec: str
    language: str
    title: str
    duration_ms: Optional[int] = None
    
    def __repr__(self):
        duration_str = f" [{self.duration_ms}ms]" if self.duration_ms else ""
        title_str = f" '{self.title}'" if self.title else ""
        return f"#{self.track_id} [{self.language}]{title_str} ({self.codec}){duration_str}"


@dataclass
class AudioModification:
    """Modificações a serem aplicadas em uma faixa de áudio"""
    new_name: Optional[str] = None
    delay_ms: int = 0


@dataclass
class SubtitleModification:
    """Modificações a serem aplicadas em uma faixa de legenda"""
    new_name: Optional[str] = None
    delay_ms: int = 0
    stretch: float = 1.0


@dataclass
class MuxConfig:
    """Configuração completa do muxing"""
    video_source_folder: str
    audio_selections: Dict[str, List[int]]  # folder -> [track_indices]
    audio_order: List[int]  # Ordem global das faixas de áudio
    audio_modifications: Dict[int, AudioModification]  # global_index -> modification
    subtitle_selections: Dict[str, List[int]]  # folder -> [track_indices]
    subtitle_order: List[int]  # Ordem global das faixas de legenda
    subtitle_modifications: Dict[int, SubtitleModification]  # global_index -> modification
    
    def to_dict(self):
        """Converte para dicionário serializável"""
        return {
            'video_source_folder': self.video_source_folder,
            'audio_selections': self.audio_selections,
            'audio_order': self.audio_order,
            'audio_modifications': {k: asdict(v) for k, v in self.audio_modifications.items()},
            'subtitle_selections': self.subtitle_selections,
            'subtitle_order': self.subtitle_order,
            'subtitle_modifications': {k: asdict(v) for k, v in self.subtitle_modifications.items()}
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'MuxConfig':
        """Cria instância a partir de dicionário"""
        audio_mods = {int(k): AudioModification(**v) for k, v in data['audio_modifications'].items()}
        sub_mods = {int(k): SubtitleModification(**v) for k, v in data['subtitle_modifications'].items()}
        
        return MuxConfig(
            video_source_folder=data['video_source_folder'],
            audio_selections=data['audio_selections'],
            audio_order=data['audio_order'],
            audio_modifications=audio_mods,
            subtitle_selections=data['subtitle_selections'],
            subtitle_order=data['subtitle_order'],
            subtitle_modifications=sub_mods
        )


def natural_sort_key(text: str) -> List:
    """
    Chave para ordenação natural (números como inteiros)
    "EP1" < "EP2" < "EP10" (não alfabética)
    """
    def convert(part):
        return int(part) if part.isdigit() else part.lower()
    
    return [convert(c) for c in re.split(r'(\d+)', text)]


def resolve_path(path_str: str) -> Path:
    """
    Resolve caminhos, incluindo atalhos (.lnk)
    """
    path = Path(path_str)
    
    # Se for atalho do Windows
    if path.suffix.lower() == '.lnk':
        try:
            import winshell
            shortcut = winshell.shortcut(str(path))
            resolved = Path(shortcut.path)
            print(f"  [INFO] Atalho resolvido: {path.name} -> {resolved}")
            return resolved
        except ImportError:
            print(f"  [AVISO] winshell não instalado, tentando resolver atalho manualmente...")
            pass
    
    return path.resolve()


def get_mkv_files(folder: Path) -> List[Path]:
    """Retorna arquivos MKV ordenados naturalmente"""
    mkv_files = [f for f in folder.iterdir() if f.suffix.lower() == '.mkv']
    return sorted(mkv_files, key=lambda x: natural_sort_key(x.name))


def get_track_info(mkv_path: Path) -> Tuple[List[TrackInfo], List[TrackInfo], List[TrackInfo]]:
    """
    Extrai informações de todas as faixas de um arquivo MKV
    Retorna: (videos, audios, subtitles)
    """
    try:
        result = subprocess.run(
            [MKVMERGE, "-J", str(mkv_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        
        data = json.loads(result.stdout)
        
        videos = []
        audios = []
        subtitles = []
        
        for track in data.get('tracks', []):
            track_id = track['id']
            track_type = track['type']
            codec = track['codec']
            props = track['properties']
            language = props.get('language', 'und')
            title = props.get('track_name', '')
            
            track_info = TrackInfo(
                track_id=track_id,
                track_type=track_type,
                codec=codec,
                language=language,
                title=title
            )
            
            if track_type == 'video':
                videos.append(track_info)
            elif track_type == 'audio':
                audios.append(track_info)
            elif track_type == 'subtitles':
                subtitles.append(track_info)
        
        return videos, audios, subtitles
    
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Falha ao analisar {mkv_path.name}")
        print(f"Erro: {e.stderr}")
        return [], [], []
    except json.JSONDecodeError:
        print(f"[ERRO] Falha ao decodificar JSON de {mkv_path.name}")
        return [], [], []


def get_track_durations(mkv_path: Path) -> Dict[int, int]:
    """
    Extrai duração de cada faixa em milissegundos
    Retorna: {track_id: duration_ms}
    """
    try:
        result = subprocess.run(
            [MKVMERGE, "-J", str(mkv_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        
        data = json.loads(result.stdout)
        durations = {}
        
        # Duração do container
        container_duration_ns = data.get('container', {}).get('properties', {}).get('duration')
        
        for track in data.get('tracks', []):
            track_id = track['id']
            # Usa duração da track se disponível, senão usa do container
            track_duration_ns = track['properties'].get('duration', container_duration_ns)
            
            if track_duration_ns:
                durations[track_id] = track_duration_ns // 1_000_000  # ns -> ms
        
        return durations
    
    except Exception as e:
        print(f"[AVISO] Não foi possível extrair durações de {mkv_path.name}: {e}")
        return {}


def validate_folder_structure(folders: List[Path]) -> bool:
    """
    Valida que todas as pastas tenham:
    1. Mesma quantidade de arquivos MKV
    2. Cada pasta internamente consistente (mesmas faixas em todos os eps)
    """
    print("\n" + "=" * 70)
    print("VALIDANDO ESTRUTURA DAS PASTAS")
    print("=" * 70)
    
    folder_episodes = {}
    
    for folder in folders:
        mkv_files = get_mkv_files(folder)
        
        if not mkv_files:
            print(f"\n[ERRO] Pasta sem arquivos MKV: {folder.name}")
            return False
        
        folder_episodes[folder] = mkv_files
        print(f"\n📁 {folder.name}")
        print(f"   ✓ {len(mkv_files)} episódios encontrados")
    
    # Verifica mesma quantidade de episódios
    episode_counts = [len(eps) for eps in folder_episodes.values()]
    if len(set(episode_counts)) > 1:
        print("\n[ERRO] As pastas têm quantidades diferentes de episódios!")
        for folder, episodes in folder_episodes.items():
            print(f"  {folder.name}: {len(episodes)} episódios")
        return False
    
    print(f"\n✓ Todas as pastas têm {episode_counts[0]} episódios")
    
    # Valida consistência interna de cada pasta
    print("\n" + "-" * 70)
    print("Validando consistência interna de cada pasta...")
    print("-" * 70)
    
    for folder, episodes in folder_episodes.items():
        print(f"\n📁 {folder.name}")
        
        # Analisa primeiro episódio como referência
        ref_videos, ref_audios, ref_subs = get_track_info(episodes[0])
        
        if not ref_videos:
            print(f"  [ERRO] Nenhuma faixa de vídeo encontrada em {episodes[0].name}")
            return False
        
        print(f"  Referência: {episodes[0].name}")
        print(f"    Vídeo: {len(ref_videos)}, Áudio: {len(ref_audios)}, Legendas: {len(ref_subs)}")
        
        # Verifica todos os outros episódios
        all_consistent = True
        for ep in episodes[1:]:
            videos, audios, subs = get_track_info(ep)
            
            if len(audios) < len(ref_audios):
                print(f"  ✗ {ep.name}: Tem MENOS faixas de áudio ({len(audios)} vs {len(ref_audios)})")
                all_consistent = False
            
            if len(subs) < len(ref_subs):
                print(f"  ✗ {ep.name}: Tem MENOS faixas de legenda ({len(subs)} vs {len(ref_subs)})")
                all_consistent = False
            
            if len(videos) != len(ref_videos):
                print(f"  ✗ {ep.name}: Quantidade diferente de vídeo ({len(videos)} vs {len(ref_videos)})")
                all_consistent = False
        
        if all_consistent:
            print(f"  ✓ Todos os episódios consistentes")
        else:
            print(f"\n[ERRO] Pasta {folder.name} tem episódios inconsistentes!")
            return False
    
    print("\n" + "=" * 70)
    print("✓ VALIDAÇÃO CONCLUÍDA COM SUCESSO")
    print("=" * 70)
    
    return True


def display_track_table(folders: List[Path], track_type: str) -> Dict[str, List[TrackInfo]]:
    """
    Exibe tabela comparativa de faixas (vídeo/áudio/legendas) de todas as pastas
    Retorna: {folder_name: [tracks]}
    """
    print(f"\n{'=' * 70}")
    print(f"FAIXAS DE {track_type.upper()} DISPONÍVEIS")
    print(f"{'=' * 70}")
    
    folder_tracks = {}
    
    for i, folder in enumerate(folders):
        # Pega primeiro episódio como referência
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        videos, audios, subs = get_track_info(episodes[0])
        
        if track_type == 'video':
            tracks = videos
        elif track_type == 'audio':
            tracks = audios
        else:  # subtitles
            tracks = subs
        
        folder_tracks[folder.name] = tracks
        
        print(f"\n[{i}] 📁 {folder.name} ({episodes[0].name})")
        if not tracks:
            print(f"    Nenhuma faixa de {track_type} encontrada")
        else:
            for j, track in enumerate(tracks):
                print(f"    [{j}] {track}")
    
    print(f"\n{'=' * 70}")
    
    return folder_tracks


def parse_selection(selection: str, max_index: int) -> Set[int]:
    """
    Converte entrada do usuário em conjunto de índices
    Aceita: "1,2,3" ou "1-4" ou "all" ou "*"
    """
    selection = selection.strip().lower()
    
    # Tudo
    if selection in ['all', '*', 'todas', 'todos']:
        return set(range(max_index))
    
    indices = set()
    
    for part in selection.split(','):
        part = part.strip()
        
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                if 0 <= start < max_index and 0 <= end < max_index and start <= end:
                    indices.update(range(start, end + 1))
                else:
                    print(f"[AVISO] Range inválido ignorado: {part}")
            except ValueError:
                print(f"[AVISO] Range inválido ignorado: {part}")
        else:
            try:
                idx = int(part)
                if 0 <= idx < max_index:
                    indices.add(idx)
                else:
                    print(f"[AVISO] Índice fora do range ignorado: {idx}")
            except ValueError:
                print(f"[AVISO] Valor inválido ignorado: {part}")
    
    return indices


def select_video_source(folders: List[Path]) -> str:
    """Permite usuário escolher de qual pasta virá o vídeo"""
    
    folder_tracks = display_track_table(folders, 'video')
    
    while True:
        print("\nDe qual pasta deseja usar a faixa de VÍDEO?")
        print("Digite o número da pasta:")
        
        selection = input("Pasta de vídeo: ").strip()
        
        try:
            idx = int(selection)
            if 0 <= idx < len(folders):
                selected_folder = folders[idx].name
                print(f"\n✓ Vídeo será extraído de: {selected_folder}")
                return selected_folder
            else:
                print(f"[ERRO] Índice inválido! Digite um número entre 0 e {len(folders)-1}")
        except ValueError:
            print("[ERRO] Digite um número válido!")


def select_audio_tracks(folders: List[Path]) -> Dict[str, List[int]]:
    """
    Permite usuário escolher faixas de áudio de cada pasta
    Retorna: {folder_name: [track_indices]}
    """
    folder_tracks = display_track_table(folders, 'audio')
    
    selections = {}
    
    for folder in folders:
        tracks = folder_tracks.get(folder.name, [])
        
        if not tracks:
            print(f"\n⚠ {folder.name}: Sem faixas de áudio")
            selections[folder.name] = []
            continue
        
        while True:
            print(f"\n{'=' * 70}")
            print(f"Escolha faixas de ÁUDIO de: {folder.name}")
            print(f"{'=' * 70}")
            
            for i, track in enumerate(tracks):
                print(f"  [{i}] {track}")
            
            print(f"\nExemplos: '0,1' ou '0-2' ou 'all' (nenhuma: deixe vazio)")
            selection_str = input("Seleção: ").strip()
            
            if not selection_str:
                selections[folder.name] = []
                print(f"✓ Nenhuma faixa de áudio de {folder.name}")
                break
            
            selected = parse_selection(selection_str, len(tracks))
            
            if selected or selection_str.lower() in ['all', '*']:
                selections[folder.name] = sorted(list(selected))
                print(f"\n✓ {len(selected)} faixa(s) selecionada(s) de {folder.name}:")
                for idx in selections[folder.name]:
                    print(f"    [{idx}] {tracks[idx]}")
                
                confirm = input("\nConfirmar? (s/n): ").strip().lower()
                if confirm == 's':
                    break
            else:
                print("[ERRO] Nenhuma faixa válida selecionada!")
    
    return selections


def reorder_tracks(folders: List[Path], selections: Dict[str, List[int]], track_type: str) -> List[int]:
    """
    Permite reordenar as faixas selecionadas
    Retorna: lista de índices globais na ordem desejada
    """
    # Cria lista global de faixas
    global_tracks = []
    for folder in folders:
        folder_name = folder.name
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        videos, audios, subs = get_track_info(episodes[0])
        
        if track_type == 'audio':
            tracks = audios
        else:  # subtitles
            tracks = subs
        
        for idx in selections.get(folder_name, []):
            if idx < len(tracks):
                global_tracks.append((folder_name, idx, tracks[idx]))
    
    if not global_tracks:
        return []
    
    print(f"\n{'=' * 70}")
    print(f"ORDEM ATUAL DAS FAIXAS DE {track_type.upper()}")
    print(f"{'=' * 70}")
    
    for i, (folder_name, local_idx, track) in enumerate(global_tracks):
        print(f"  [{i}] {folder_name} > {track}")
    
    print(f"\n{'=' * 70}")
    print("Deseja alterar a ordem? (s/n): ", end='')
    
    if input().strip().lower() != 's':
        # Mantém ordem atual
        return list(range(len(global_tracks)))
    
    print("\nDigite a nova ordem dos índices (ex: '2,0,1' ou '0-2'):")
    print("Use 'Enter' para manter ordem atual")
    
    while True:
        order_str = input("Nova ordem: ").strip()
        
        if not order_str:
            return list(range(len(global_tracks)))
        
        try:
            # Tenta parsear como lista de números
            if ',' in order_str or '-' in order_str:
                order_indices = []
                for part in order_str.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        order_indices.extend(range(start, end + 1))
                    else:
                        order_indices.append(int(part))
            else:
                # Lista separada por espaço
                order_indices = [int(x) for x in order_str.split()]
            
            # Valida
            if len(order_indices) != len(global_tracks):
                print(f"[ERRO] Você deve especificar todos os {len(global_tracks)} índices!")
                continue
            
            if set(order_indices) != set(range(len(global_tracks))):
                print(f"[ERRO] Índices inválidos! Use números de 0 a {len(global_tracks)-1}")
                continue
            
            # Mostra preview
            print("\nNova ordem:")
            for new_pos, old_idx in enumerate(order_indices):
                folder_name, local_idx, track = global_tracks[old_idx]
                print(f"  [{new_pos}] {folder_name} > {track}")
            
            confirm = input("\nConfirmar? (s/n): ").strip().lower()
            if confirm == 's':
                return order_indices
        
        except ValueError:
            print("[ERRO] Formato inválido! Use números separados por vírgula ou espaço")


def modify_audio_tracks(folders: List[Path], audio_selections: Dict[str, List[int]], audio_order: List[int]) -> Dict[int, AudioModification]:
    """
    Permite modificar nomes e delays das faixas de áudio selecionadas
    Suporta modificação em lote
    Retorna: {global_index: AudioModification}
    """
    print(f"\n{'=' * 70}")
    print("MODIFICAÇÕES NAS FAIXAS DE ÁUDIO")
    print(f"{'=' * 70}")
    
    # Cria lista global de faixas
    global_tracks = []
    for folder in folders:
        folder_name = folder.name
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        _, audios, _ = get_track_info(episodes[0])
        
        for idx in audio_selections.get(folder_name, []):
            if idx < len(audios):
                global_tracks.append((folder_name, idx, audios[idx]))
    
    if not global_tracks:
        print("Nenhuma faixa de áudio selecionada.")
        return {}
    
    # Aplica ordenação
    ordered_tracks = [global_tracks[i] for i in audio_order]
    
    print("\nFaixas selecionadas (na ordem do muxing):")
    for i, (folder_name, local_idx, track) in enumerate(ordered_tracks):
        print(f"  [{i}] {folder_name} > {track}")
    
    print(f"\n{'=' * 70}")
    print("INSTRUÇÕES:")
    print("  - Para modificar múltiplas: '0,2,4' ou '0-3' ou 'all'")
    print("  - Para finalizar: pressione Enter sem digitar nada")
    print(f"{'=' * 70}")
    
    modifications = {}
    
    while True:
        print(f"\n{'-' * 70}")
        print("Digite índice(s) para modificar (ou Enter para finalizar):")
        selection = input("Índice(s): ").strip()
        
        if not selection:
            break
        
        # Parse seleção
        indices = parse_selection(selection, len(ordered_tracks))
        
        if not indices:
            print("[ERRO] Nenhum índice válido!")
            continue
        
        print(f"\nModificando {len(indices)} faixa(s):")
        for idx in sorted(indices):
            folder_name, local_idx, track = ordered_tracks[idx]
            print(f"  [{idx}] {folder_name} > {track}")
        
        # Novo nome (aplicado a todas)
        print(f"\nNovo nome (Enter para manter original, mesmo nome para todas): ", end='')
        new_name = input().strip()
        
        # Delay (aplicado a todas)
        print("Delay em ms (Enter para 0, mesmo delay para todas): ", end='')
        delay_str = input().strip()
        delay_ms = int(delay_str) if delay_str else 0
        
        # Aplica modificações - usa índice da ordem ORIGINAL para mapeamento correto
        for idx in indices:
            # Mapeia índice ordenado de volta para índice original
            original_idx = audio_order[idx]
            
            # Se já existe modificação, faz merge
            if original_idx in modifications:
                existing = modifications[original_idx]
                modifications[original_idx] = AudioModification(
                    new_name=new_name if new_name else existing.new_name,
                    delay_ms=delay_ms if delay_ms != 0 or delay_str else existing.delay_ms
                )
            else:
                modifications[original_idx] = AudioModification(
                    new_name=new_name if new_name else None,
                    delay_ms=delay_ms
                )
        
        print(f"✓ Modificação registrada para {len(indices)} faixa(s)")
    
    return modifications


def select_subtitle_tracks(folders: List[Path]) -> Dict[str, List[int]]:
    """
    Permite usuário escolher faixas de legenda de cada pasta
    Retorna: {folder_name: [track_indices]}
    """
    folder_tracks = display_track_table(folders, 'subtitles')
    
    selections = {}
    
    for folder in folders:
        tracks = folder_tracks.get(folder.name, [])
        
        if not tracks:
            print(f"\n⚠ {folder.name}: Sem faixas de legenda")
            selections[folder.name] = []
            continue
        
        while True:
            print(f"\n{'=' * 70}")
            print(f"Escolha faixas de LEGENDA de: {folder.name}")
            print(f"{'=' * 70}")
            
            for i, track in enumerate(tracks):
                print(f"  [{i}] {track}")
            
            print(f"\nExemplos: '0,1' ou '0-2' ou 'all' (nenhuma: deixe vazio)")
            selection_str = input("Seleção: ").strip()
            
            if not selection_str:
                selections[folder.name] = []
                print(f"✓ Nenhuma faixa de legenda de {folder.name}")
                break
            
            selected = parse_selection(selection_str, len(tracks))
            
            if selected or selection_str.lower() in ['all', '*']:
                selections[folder.name] = sorted(list(selected))
                print(f"\n✓ {len(selected)} faixa(s) selecionada(s) de {folder.name}:")
                for idx in selections[folder.name]:
                    print(f"    [{idx}] {tracks[idx]}")
                
                confirm = input("\nConfirmar? (s/n): ").strip().lower()
                if confirm == 's':
                    break
            else:
                print("[ERRO] Nenhuma faixa válida selecionada!")
    
    return selections


def modify_subtitle_tracks(folders: List[Path], subtitle_selections: Dict[str, List[int]], subtitle_order: List[int]) -> Dict[int, SubtitleModification]:
    """
    Permite modificar nomes, delays e stretch das faixas de legenda selecionadas
    Suporta modificação em lote
    Retorna: {global_index: SubtitleModification}
    """
    print(f"\n{'=' * 70}")
    print("MODIFICAÇÕES NAS FAIXAS DE LEGENDA")
    print(f"{'=' * 70}")
    
    # Cria lista global de faixas
    global_tracks = []
    for folder in folders:
        folder_name = folder.name
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        _, _, subs = get_track_info(episodes[0])
        
        for idx in subtitle_selections.get(folder_name, []):
            if idx < len(subs):
                global_tracks.append((folder_name, idx, subs[idx]))
    
    if not global_tracks:
        print("Nenhuma faixa de legenda selecionada.")
        return {}
    
    # Aplica ordenação
    ordered_tracks = [global_tracks[i] for i in subtitle_order]
    
    print("\nFaixas selecionadas (na ordem do muxing):")
    for i, (folder_name, local_idx, track) in enumerate(ordered_tracks):
        print(f"  [{i}] {folder_name} > {track}")
    
    print(f"\n{'=' * 70}")
    print("INSTRUÇÕES:")
    print("  - Para modificar múltiplas: '0,2,4' ou '0-3' ou 'all'")
    print("  - Para finalizar: pressione Enter sem digitar nada")
    print(f"{'=' * 70}")
    
    modifications = {}
    
    while True:
        print(f"\n{'-' * 70}")
        print("Digite índice(s) para modificar (ou Enter para finalizar):")
        selection = input("Índice(s): ").strip()
        
        if not selection:
            break
        
        # Parse seleção
        indices = parse_selection(selection, len(ordered_tracks))
        
        if not indices:
            print("[ERRO] Nenhum índice válido!")
            continue
        
        print(f"\nModificando {len(indices)} faixa(s):")
        for idx in sorted(indices):
            folder_name, local_idx, track = ordered_tracks[idx]
            print(f"  [{idx}] {folder_name} > {track}")
        
        # Novo nome (aplicado a todas)
        print(f"\nNovo nome (Enter para manter original, mesmo nome para todas): ", end='')
        new_name = input().strip()
        
        # Delay (aplicado a todas)
        print("Delay em ms (Enter para 0, mesmo delay para todas): ", end='')
        delay_str = input().strip()
        delay_ms = int(delay_str) if delay_str else 0
        
        # Stretch (aplicado a todas)
        print("Stretch (Enter para 1.0, mesmo stretch para todas): ", end='')
        stretch_str = input().strip()
        stretch = float(stretch_str) if stretch_str else 1.0
        
        # Aplica modificações - usa índice da ordem ORIGINAL para mapeamento correto
        for idx in indices:
            # Mapeia índice ordenado de volta para índice original
            original_idx = subtitle_order[idx]
            
            # Se já existe modificação, faz merge
            if original_idx in modifications:
                existing = modifications[original_idx]
                modifications[original_idx] = SubtitleModification(
                    new_name=new_name if new_name else existing.new_name,
                    delay_ms=delay_ms if delay_ms != 0 or delay_str else existing.delay_ms,
                    stretch=stretch if stretch != 1.0 or stretch_str else existing.stretch
                )
            else:
                modifications[original_idx] = SubtitleModification(
                    new_name=new_name if new_name else None,
                    delay_ms=delay_ms,
                    stretch=stretch
                )
        
        print(f"✓ Modificação registrada para {len(indices)} faixa(s)")
    
    return modifications


def save_config(config: MuxConfig):
    """Salva configuração em arquivo JSON"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"\n✓ Configuração salva em: {CONFIG_FILE}")
    except Exception as e:
        print(f"\n[AVISO] Não foi possível salvar configuração: {e}")


def load_config() -> Optional[MuxConfig]:
    """Carrega configuração do arquivo JSON"""
    try:
        if not Path(CONFIG_FILE).exists():
            return None
        
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return MuxConfig.from_dict(data)
    except Exception as e:
        print(f"[AVISO] Não foi possível carregar configuração: {e}")
        return None


def process_muxing(folders: List[Path], config: MuxConfig):
    """
    Executa o muxing em massa de todos os episódios
    """
    # Cria pasta de saída
    output_dir = folders[0].parent / "mass_mux_output"
    output_dir.mkdir(exist_ok=True)
    
    print(f"\n{'=' * 70}")
    print("INICIANDO MUXING EM MASSA")
    print(f"{'=' * 70}")
    print(f"Pasta de saída: {output_dir}")
    
    # Mapeia pastas
    folder_map = {f.name: f for f in folders}
    video_folder = folder_map[config.video_source_folder]
    
    # Pega lista de episódios
    video_episodes = get_mkv_files(video_folder)
    total_episodes = len(video_episodes)
    
    # Para rastrear problemas de duração
    audio_duration_issues = []
    
    print(f"\nTotal de episódios: {total_episodes}")
    
    # Cria lista global ordenada de tracks de áudio e legenda
    global_audio_tracks = []
    for folder in folders:
        folder_name = folder.name
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        _, audios, _ = get_track_info(episodes[0])
        
        for idx in config.audio_selections.get(folder_name, []):
            if idx < len(audios):
                global_audio_tracks.append((folder_name, idx, audios[idx]))
    
    # Reordena conforme config
    ordered_audio_tracks = [global_audio_tracks[i] for i in config.audio_order]
    
    global_sub_tracks = []
    for folder in folders:
        folder_name = folder.name
        episodes = get_mkv_files(folder)
        if not episodes:
            continue
        
        _, _, subs = get_track_info(episodes[0])
        
        for idx in config.subtitle_selections.get(folder_name, []):
            if idx < len(subs):
                global_sub_tracks.append((folder_name, idx, subs[idx]))
    
    # Reordena conforme config
    ordered_sub_tracks = [global_sub_tracks[i] for i in config.subtitle_order]
    
    for ep_idx, video_ep in enumerate(video_episodes, 1):
        print(f"\n{'-' * 70}")
        print(f"[{ep_idx}/{total_episodes}] Processando: {video_ep.name}")
        print(f"{'-' * 70}")
        
        # Nome do arquivo de saída
        output_name = f"{video_ep.stem}_muxed.mkv"
        output_path = output_dir / output_name
        
        # Monta comando mkvmerge
        cmd = [MKVMERGE, "-o", str(output_path)]
        
        # === VÍDEO ===
        videos, _, _ = get_track_info(video_ep)
        if videos:
            video_track_id = videos[0].track_id
            cmd.extend(["-d", str(video_track_id)])
            cmd.extend(["-A", "-S"])
            cmd.append(str(video_ep))
            print(f"  ✓ Vídeo: {video_folder.name}/{video_ep.name}")
        
        # === ÁUDIO (na ordem configurada) ===
        for new_idx, (folder_name, local_idx, track_info) in enumerate(ordered_audio_tracks):
            folder = folder_map[folder_name]
            folder_episodes = get_mkv_files(folder)
            
            if ep_idx - 1 >= len(folder_episodes):
                print(f"  ✗ ERRO: Pasta {folder_name} não tem episódio {ep_idx}")
                continue
            
            current_ep = folder_episodes[ep_idx - 1]
            _, audios, _ = get_track_info(current_ep)
            
            if local_idx >= len(audios):
                continue
            
            audio_track = audios[local_idx]
            
            # Seleciona apenas esta faixa de áudio
            cmd.extend(["-a", str(audio_track.track_id)])
            cmd.extend(["-D", "-S"])  # Sem vídeo nem legendas
            
            # Aplica modificações - audio_order[new_idx] dá o índice ORIGINAL
            original_idx = config.audio_order[new_idx]
            if original_idx in config.audio_modifications:
                mod = config.audio_modifications[original_idx]
                
                if mod.new_name:
                    cmd.extend(["--track-name", f"{audio_track.track_id}:{mod.new_name}"])
                
                if mod.delay_ms != 0:
                    cmd.extend(["--sync", f"{audio_track.track_id}:{mod.delay_ms}"])
            
            # Adiciona o arquivo DEPOIS das opções
            cmd.append(str(current_ep))
        
        print(f"  ✓ Áudio: {len(ordered_audio_tracks)} faixas")
        
        # === LEGENDAS (na ordem configurada) ===
        for new_idx, (folder_name, local_idx, track_info) in enumerate(ordered_sub_tracks):
            folder = folder_map[folder_name]
            folder_episodes = get_mkv_files(folder)
            
            if ep_idx - 1 >= len(folder_episodes):
                print(f"  ✗ ERRO: Pasta {folder_name} não tem episódio {ep_idx}")
                continue
            
            current_ep = folder_episodes[ep_idx - 1]
            _, _, subs = get_track_info(current_ep)
            
            if local_idx >= len(subs):
                continue
            
            sub_track = subs[local_idx]
            
            # Seleciona apenas esta faixa de legenda
            cmd.extend(["-s", str(sub_track.track_id)])
            cmd.extend(["-D", "-A"])  # Sem vídeo nem áudio
            
            # Aplica modificações - subtitle_order[new_idx] dá o índice ORIGINAL
            original_idx = config.subtitle_order[new_idx]
            if original_idx in config.subtitle_modifications:
                mod = config.subtitle_modifications[original_idx]
                
                if mod.new_name:
                    cmd.extend(["--track-name", f"{sub_track.track_id}:{mod.new_name}"])
                
                if mod.delay_ms != 0 or mod.stretch != 1.0:
                    sync_param = f"{sub_track.track_id}:{mod.delay_ms}"
                    if mod.stretch != 1.0:
                        sync_param += f",{mod.stretch}"
                    cmd.extend(["--sync", sync_param])
            
            # Adiciona o arquivo DEPOIS das opções
            cmd.append(str(current_ep))
        
        print(f"  ✓ Legendas: {len(ordered_sub_tracks)} faixas")
        
        # Executa mkvmerge
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=True
            )
            
            print(f"  ✓ Muxing concluído: {output_name}")
            
            # Verifica durações
            durations = get_track_durations(output_path)
            video_duration = None
            audio_durations = []
            
            for track_id, duration in durations.items():
                _, audios, _ = get_track_info(output_path)
                audio_ids = [a.track_id for a in audios]
                
                if track_id in audio_ids:
                    audio_durations.append((track_id, duration))
                elif video_duration is None:
                    video_duration = duration
            
            # Verifica se algum áudio é maior que vídeo
            if video_duration:
                for track_id, audio_dur in audio_durations:
                    if audio_dur > video_duration:
                        diff_ms = audio_dur - video_duration
                        audio_duration_issues.append({
                            'file': output_name,
                            'video_duration': video_duration,
                            'audio_duration': audio_dur,
                            'difference_ms': diff_ms
                        })
        
        except subprocess.CalledProcessError as e:
            print(f"  ✗ ERRO no muxing de {video_ep.name}")
            print(f"  Comando: {' '.join(cmd)}")
            print(f"  Erro: {e.stderr}")
            continue
    
    # Relatório final
    print(f"\n{'=' * 70}")
    print("MUXING CONCLUÍDO")
    print(f"{'=' * 70}")
    print(f"✓ {total_episodes} episódios processados")
    print(f"✓ Arquivos salvos em: {output_dir}")
    
    # Relatório de problemas de duração
    if audio_duration_issues:
        print(f"\n{'=' * 70}")
        print("⚠ ATENÇÃO: ÁUDIOS COM DURAÇÃO MAIOR QUE VÍDEO")
        print(f"{'=' * 70}")
        print(f"Total de episódios afetados: {len(audio_duration_issues)}\n")
        
        for issue in audio_duration_issues:
            video_sec = issue['video_duration'] / 1000
            audio_sec = issue['audio_duration'] / 1000
            diff_sec = issue['difference_ms'] / 1000
            
            print(f"📁 {issue['file']}")
            print(f"   Vídeo:  {video_sec:.2f}s ({issue['video_duration']}ms)")
            print(f"   Áudio:  {audio_sec:.2f}s ({issue['audio_duration']}ms)")
            print(f"   Diferença: +{diff_sec:.2f}s (+{issue['difference_ms']}ms)")
            print()
    else:
        print("\n✓ Nenhum problema de duração detectado")
    
    print(f"{'=' * 70}")


def main():
    print("\n" + "=" * 70)
    print(" MASS MUX - Muxing em Massa de Episódios")
    print("=" * 70)
    
    if len(sys.argv) < 2:
        print("\n[ERRO] Nenhuma pasta fornecida!")
        print("\nUso:")
        print("  Arraste PASTAS (ou atalhos) sobre mass_mux.bat")
        print("  Cada pasta deve conter episódios .mkv")
        sys.exit(1)
    
    # Resolve paths (incluindo atalhos)
    folders = []
    for arg in sys.argv[1:]:
        path = resolve_path(arg)
        
        if not path.exists():
            print(f"[AVISO] Caminho não existe: {arg}")
            continue
        
        if not path.is_dir():
            print(f"[AVISO] Não é uma pasta: {arg}")
            continue
        
        folders.append(path)
    
    if not folders:
        print("\n[ERRO] Nenhuma pasta válida fornecida!")
        sys.exit(1)
    
    print(f"\n✓ {len(folders)} pasta(s) recebida(s):")
    for folder in folders:
        print(f"  📁 {folder.name}")
    
    # Validação de estrutura
    if not validate_folder_structure(folders):
        print("\n[ERRO] Estrutura de pastas inválida!")
        sys.exit(1)
    
    # Verifica se existe config anterior
    config = None
    saved_config = load_config()
    
    if saved_config:
        print(f"\n{'=' * 70}")
        print("CONFIGURAÇÃO ANTERIOR DETECTADA")
        print(f"{'=' * 70}")
        print("\nDeseja usar a última configuração? (s/n): ", end='')
        
        if input().strip().lower() == 's':
            config = saved_config
            print("✓ Usando configuração salva")
    
    # Se não tem config, cria interativamente
    if not config:
        print(f"\n{'=' * 70}")
        print("CONFIGURAÇÃO INTERATIVA")
        print(f"{'=' * 70}")
        
        # 1. Escolha de vídeo
        video_source = select_video_source(folders)
        
        # 2. Escolha de áudio
        audio_selections = select_audio_tracks(folders)
        
        # 3. Ordenação de áudio
        audio_order = reorder_tracks(folders, audio_selections, 'audio')
        
        # 4. Modificações de áudio
        audio_modifications = modify_audio_tracks(folders, audio_selections, audio_order)
        
        # 5. Escolha de legendas
        subtitle_selections = select_subtitle_tracks(folders)
        
        # 6. Ordenação de legendas
        subtitle_order = reorder_tracks(folders, subtitle_selections, 'subtitles')
        
        # 7. Modificações de legendas
        subtitle_modifications = modify_subtitle_tracks(folders, subtitle_selections, subtitle_order)
        
        # Cria config
        config = MuxConfig(
            video_source_folder=video_source,
            audio_selections=audio_selections,
            audio_order=audio_order,
            audio_modifications=audio_modifications,
            subtitle_selections=subtitle_selections,
            subtitle_order=subtitle_order,
            subtitle_modifications=subtitle_modifications
        )
        
        # Salva config
        save_config(config)
    
    # Confirmação final
    print(f"\n{'=' * 70}")
    print("RESUMO DA OPERAÇÃO")
    print(f"{'=' * 70}")
    print(f"Vídeo: {config.video_source_folder}")
    print(f"Áudio: {sum(len(v) for v in config.audio_selections.values())} faixas de {len(config.audio_selections)} pastas")
    print(f"Legendas: {sum(len(v) for v in config.subtitle_selections.values())} faixas de {len(config.subtitle_selections)} pastas")
    print(f"{'=' * 70}")
    
    print("\nIniciar muxing? (s/n): ", end='')
    if input().strip().lower() != 's':
        print("Operação cancelada.")
        sys.exit(0)
    
    # Executa muxing
    process_muxing(folders, config)


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