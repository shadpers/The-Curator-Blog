#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import glob
import re
import traceback
import time
import json
from pathlib import Path
from datetime import datetime
try:
    import urllib.request
    import urllib.parse
    import urllib.error
except ImportError:
    print("ERRO: Módulo urllib não disponível")
    sys.exit(1)

# Configurações
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"
GABARITO_FILENAME = "gabarito.txt"
COVER_EXTENSIONS = [".jpg", ".jpeg", ".png"]
WAV_PATTERN = "*.wav"

# Procura metaflac em locais comuns
def find_metaflac():
    """Procura metaflac.exe em vários locais"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Lista de possíveis localizações
    possible_paths = [
        os.path.join(script_dir, "metaflac.exe"),  # Mesma pasta do script
        os.path.join(script_dir, "metaflac", "metaflac.exe"),  # Subpasta metaflac
        r"C:\Program Files\FLAC\metaflac.exe",  # Instalação padrão
        r"C:\Program Files (x86)\FLAC\metaflac.exe",
        "metaflac",  # No PATH do sistema
    ]
    
    for path in possible_paths:
        if path == "metaflac":
            # Testa se está no PATH
            try:
                subprocess.run([path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return path
            except:
                continue
        elif os.path.exists(path):
            return path
    
    return None

METAFLAC_PATH = find_metaflac()

# MusicBrainz API Configuration
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
COVERART_API = "https://coverartarchive.org"
USER_AGENT = "WAV2FLAC-Converter/2.0 (https://github.com/converter)"

def search_musicbrainz_release(artist, album, max_retries=3):
    """Busca um release no MusicBrainz com retry"""
    log_message(f"Buscando '{album}' de '{artist}' no MusicBrainz...")
    
    # Tenta variações na busca
    search_variations = [
        f'artist:"{artist}" AND release:"{album}"',  # Busca exata
        f'artist:{artist} AND release:{album}',       # Sem aspas
        f'release:{album}',                            # Só álbum
    ]
    
    for attempt, query in enumerate(search_variations, 1):
        log_message(f"Tentativa {attempt}: {query}", "DEBUG")
        
        params = urllib.parse.urlencode({
            'query': query,
            'fmt': 'json',
            'limit': 10
        })
        
        url = f"{MUSICBRAINZ_API}/release/?{params}"
        
        for retry in range(max_retries):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
                time.sleep(1.5)  # Rate limit mais conservador
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                if 'releases' in data and len(data['releases']) > 0:
                    log_message(f"Encontrado(s) {len(data['releases'])} resultado(s)")
                    return data['releases']
                
                # Se não encontrou, tenta próxima variação
                break
                
            except urllib.error.URLError as e:
                if retry < max_retries - 1:
                    log_message(f"Erro de conexão (tentativa {retry + 1}/{max_retries}), aguardando...", "WARNING")
                    time.sleep(3)
                else:
                    log_message(f"Erro de conexão após {max_retries} tentativas: {str(e)}", "ERROR")
            except Exception as e:
                log_message(f"Erro ao buscar: {str(e)}", "ERROR")
                break
    
    log_message("Nenhum resultado encontrado em todas as variações", "WARNING")
    return None

def get_release_details(release_id):
    """Obtém detalhes completos de um release incluindo faixas"""
    log_message(f"Buscando detalhes do release {release_id}...")
    
    params = urllib.parse.urlencode({
        'inc': 'recordings+artist-credits',
        'fmt': 'json'
    })
    
    url = f"{MUSICBRAINZ_API}/release/{release_id}?{params}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        time.sleep(1)  # Rate limit - MusicBrainz pede 1 segundo entre requests
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        return data
    
    except Exception as e:
        log_message(f"Erro ao buscar detalhes: {str(e)}", "ERROR")
        return None

def download_cover_art(release_id, output_path):
    """Baixa a capa do álbum do Cover Art Archive"""
    log_message("Baixando capa do álbum...")
    
    url = f"{COVERART_API}/release/{release_id}/front"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req) as response:
            with open(output_path, 'wb') as f:
                f.write(response.read())
        
        log_message(f"Capa baixada: {os.path.basename(output_path)}")
        return True
    
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log_message("Capa não disponível no Cover Art Archive", "WARNING")
        else:
            log_message(f"Erro ao baixar capa: {e}", "WARNING")
        return False
    except Exception as e:
        log_message(f"Erro ao baixar capa: {str(e)}", "WARNING")
        return False

def select_release_interactive(releases):
    """Permite usuário selecionar o release correto"""
    print()
    print("=" * 60)
    print("MÚLTIPLOS RESULTADOS ENCONTRADOS:")
    print("=" * 60)
    print()
    
    for idx, release in enumerate(releases[:10], 1):  # Mostra até 10 resultados
        title = release.get('title', 'Sem título')
        artist = release.get('artist-credit', [{}])[0].get('name', 'Artista desconhecido') if release.get('artist-credit') else 'Artista desconhecido'
        date = release.get('date', 'Data desconhecida')
        country = release.get('country', '??')
        track_count = release.get('track-count', '?')
        
        print(f"{idx}. {title}")
        print(f"   Artista: {artist}")
        print(f"   Data: {date} | País: {country} | Faixas: {track_count}")
        print()
    
    print("=" * 60)
    
    while True:
        choice = input(f"Selecione o release correto (1-{min(10, len(releases))}) ou 0 para cancelar: ").strip()
        try:
            choice_num = int(choice)
            if choice_num == 0:
                return None
            if 1 <= choice_num <= min(10, len(releases)):
                return releases[choice_num - 1]
            print("Opção inválida!")
        except ValueError:
            print("Digite um número válido!")

def parse_folder_name(folder_path):
    """Extrai artista e álbum do nome da pasta
    Formatos suportados:
    - "Artista - Album"
    - "Artista-Album" 
    - "Album" (sem artista, assume Various Artists)
    """
    folder_name = os.path.basename(folder_path)
    
    # Tenta separar por " - " (espaço-hífen-espaço)
    if " - " in folder_name:
        parts = folder_name.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    
    # Tenta separar por "-" simples
    elif "-" in folder_name and not folder_name.startswith("-"):
        parts = folder_name.split("-", 1)
        return parts[0].strip(), parts[1].strip()
    
    # Se não tem separador, assume que é só o nome do álbum
    else:
        return "Various Artists", folder_name.strip()

def confirm_or_edit_metadata(artist, album):
    """Permite usuário confirmar ou editar artista e álbum"""
    print()
    print("=" * 60)
    print("INFORMAÇÕES EXTRAÍDAS DO NOME DA PASTA:")
    print("=" * 60)
    print(f"Artista: {artist}")
    print(f"Álbum: {album}")
    print("=" * 60)
    print()
    
    choice = input("Confirmar? (S/n), 'e' para editar ou cole URL do MusicBrainz: ").strip()
    
    # Verifica se é uma URL do MusicBrainz
    if 'musicbrainz.org' in choice.lower():
        return None, None, choice  # Retorna URL
    
    if choice.lower() == 'e':
        print()
        new_artist = input(f"Digite o ARTISTA [{artist}]: ").strip()
        new_album = input(f"Digite o ÁLBUM [{album}]: ").strip()
        
        artist = new_artist if new_artist else artist
        album = new_album if new_album else album
        print()
    elif choice.lower() == 'n':
        return None, None, None
    
    return artist, album, None

def extract_release_id_from_url(url):
    """Extrai o release ID de uma URL do MusicBrainz
    Exemplos:
    - https://musicbrainz.org/release/e4be1af3-a7ac-481f-ae23-78fcf4d390a2
    - https://musicbrainz.org/release-group/xyz
    """
    import re
    
    # Procura por UUID no formato do MusicBrainz
    match = re.search(r'/release/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', url)
    if match:
        return match.group(1)
    
    return None

def parse_musicbrainz_to_albuminfo(release_data):
    """Converte dados do MusicBrainz para AlbumInfo"""
    info = AlbumInfo()
    
    info.album = release_data.get('title', '')
    
    # Pega o primeiro artista
    if 'artist-credit' in release_data and len(release_data['artist-credit']) > 0:
        info.artist = release_data['artist-credit'][0].get('name', '')
        info.album_artist = info.artist
    
    # Ano
    date = release_data.get('date', '')
    if date:
        info.year = date.split('-')[0]  # Pega só o ano
    
    # Gênero e label não são facilmente acessíveis na API básica do MusicBrainz
    # mas podemos preencher depois se necessário
    
    # Faixas com artistas individuais
    if 'media' in release_data:
        track_index = 0
        for medium in release_data['media']:
            if 'tracks' in medium:
                for track in medium['tracks']:
                    track_title = track.get('title', '')
                    
                    if not track_title:
                        continue
                    
                    track_index += 1
                    
                    # Pega o artista específico da faixa
                    track_artist = None
                    if 'artist-credit' in track and len(track['artist-credit']) > 0:
                        track_artist = track['artist-credit'][0].get('name', '')
                    
                    # Armazena o artista individual se diferente do album artist
                    if track_artist and track_artist != info.artist:
                        info.track_artists[track_index] = track_artist
                        # Adiciona ao título para o nome do arquivo
                        track_with_artist = f"{track_title} - ({track_artist})"
                        info.tracks.append(track_with_artist)
                    else:
                        info.tracks.append(track_title)
    
    log_message(f"Álbum: {info.album}")
    log_message(f"Artista do álbum: {info.album_artist}")
    log_message(f"Ano: {info.year}")
    log_message(f"Faixas encontradas: {len(info.tracks)}")
    
    return info

class AlbumInfo:
    """Armazena informações do álbum lidas do gabarito"""
    def __init__(self):
        self.album = ""
        self.artist = ""
        self.year = ""
        self.genre = ""
        self.tracks = []  # Lista de tuplas (título, artista) ou apenas strings
        self.track_artists = {}  # Dicionário {índice: artista_da_faixa}
        self.album_artist = ""
        self.label = ""
        self.comment = ""

def print_header():
    """Imprime cabeçalho do script"""
    print("=" * 60)
    print("CONVERSOR WAV PARA FLAC - v2.0")
    print("=" * 60)
    print()

def select_conversion_mode():
    """Permite usuário selecionar o modo de conversão"""
    print("=" * 60)
    print("SELECIONE O MODO DE CONVERSÃO:")
    print("=" * 60)
    print()
    print("1. MANUAL")
    print("   - Usa gabarito.txt local")
    print("   - Usa cover.jpg local")
    print()
    print("2. SEMI-AUTOMÁTICO")
    print("   - Busca metadados online (MusicBrainz)")
    print("   - Usa cover.jpg local")
    print()
    print("3. AUTOMÁTICO COMPLETO")
    print("   - Busca metadados online (MusicBrainz)")
    print("   - Baixa capa automaticamente")
    print()
    print("=" * 60)
    
    while True:
        choice = input("Digite sua escolha (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            return int(choice)
        print("Opção inválida! Digite 1, 2 ou 3.")
        print()

def log_message(message, level="INFO"):
    """Imprime mensagem com timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
    sys.stdout.flush()

def sanitize_filename(filename):
    """Remove caracteres inválidos de nomes de arquivo do Windows"""
    # Caracteres proibidos no Windows: < > : " / \ | ? *
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    
    # Remove espaços extras e pontos no final
    filename = filename.strip('. ')
    
    # Limita o tamanho do nome (Windows tem limite de 255 caracteres para o caminho total)
    if len(filename) > 200:
        filename = filename[:200].strip()
    
    return filename

def find_cover_image(folder):
    """Procura por imagem de capa na pasta"""
    log_message("Procurando imagem de capa...")
    
    # Procura por cover.* primeiro
    for ext in COVER_EXTENSIONS:
        cover_path = os.path.join(folder, f"cover{ext}")
        if os.path.exists(cover_path):
            log_message(f"Capa encontrada: {os.path.basename(cover_path)}")
            return cover_path
    
    # Procura por qualquer imagem
    for ext in COVER_EXTENSIONS:
        pattern = os.path.join(folder, f"*{ext}")
        images = glob.glob(pattern)
        if images:
            cover_path = images[0]
            log_message(f"Imagem encontrada: {os.path.basename(cover_path)}")
            return cover_path
    
    log_message("Nenhuma imagem de capa encontrada", "WARNING")
    return None

def parse_gabarito(gabarito_path):
    """Lê e interpreta o arquivo gabarito.txt"""
    log_message(f"Lendo gabarito: {os.path.basename(gabarito_path)}")
    
    if not os.path.exists(gabarito_path):
        log_message(f"ERRO: Arquivo gabarito não encontrado!", "ERROR")
        log_message(f"Caminho esperado: {gabarito_path}", "ERROR")
        return None
    
    info = AlbumInfo()
    
    try:
        # Tenta ler com utf-8, se falhar tenta latin-1 (comum no Windows)
        try:
            with open(gabarito_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(gabarito_path, 'r', encoding='latin-1') as f:
                lines = f.readlines()
        
        track_section = False
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if line.upper().startswith("FAIXAS:") or line.upper().startswith("TRACKS:"):
                track_section = True
                continue
            
            if track_section:
                track_name = re.sub(r'^\d+[\.\)\-\s]+', '', line)
                if track_name:
                    info.tracks.append(track_name)
            else:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().upper()
                    value = value.strip()
                    
                    if key in ["ALBUM", "ÁLBUM", "ALBUM NAME"]:
                        info.album = value
                    elif key in ["ARTIST", "ARTISTA", "ARTIST NAME"]:
                        info.artist = value
                    elif key in ["YEAR", "ANO", "DATE"]:
                        info.year = value
                    elif key in ["GENRE", "GÊNERO", "GENERO"]:
                        info.genre = value
                    elif key in ["ALBUM ARTIST", "ALBUM_ARTIST", "ALBUMARTIST"]:
                        info.album_artist = value
                    elif key in ["LABEL", "GRAVADORA", "SELO"]:
                        info.label = value
                    elif key in ["COMMENT", "COMENTÁRIO", "COMENTARIO", "NOTES"]:
                        info.comment = value
        
        if not info.album_artist:
            info.album_artist = info.artist
        
        log_message(f"Álbum: {info.album}")
        log_message(f"Artista: {info.artist}")
        log_message(f"Faixas encontradas: {len(info.tracks)}")
        
        return info
        
    except Exception as e:
        log_message(f"ERRO ao ler gabarito: {str(e)}", "ERROR")
        return None

def find_wav_files(folder):
    """Lista todos os arquivos WAV na pasta, ordenados alfabeticamente"""
    log_message("Procurando arquivos WAV...")
    wav_pattern = os.path.join(folder, WAV_PATTERN)
    wav_files = glob.glob(wav_pattern)
    wav_files.sort()
    log_message(f"Encontrados {len(wav_files)} arquivos WAV")
    return wav_files

def convert_wav_to_flac(wav_file, output_file, album_info, track_number, total_tracks, cover_image=None):
    """Converte um arquivo WAV para FLAC com metadados usando FFmpeg"""
    track_title = album_info.tracks[track_number - 1] if track_number <= len(album_info.tracks) else f"Track {track_number}"
    log_message(f"Convertendo {track_number}/{total_tracks}: {track_title}")
    
    # PASSO 1: Converter WAV para FLAC com metadados de áudio
    cmd = [FFMPEG_PATH, "-i", wav_file]
    
    # Opções de encoding
    cmd.extend(["-c:a", "flac", "-compression_level", "8"])
    
    # Determina o artista correto para esta faixa
    # Se houver artista específico para esta faixa, usa ele, senão usa o artista do álbum
    track_artist = album_info.track_artists.get(track_number, album_info.artist)
    
    # Prepara metadados
    metadata = {
        "title": track_title,
        "artist": track_artist,  # Artista específico da faixa
        "album": album_info.album,
        "album_artist": album_info.album_artist,  # Mantém o album artist como Various Artists
        "track": f"{track_number}/{total_tracks}",
    }
    
    if album_info.year: metadata["date"] = album_info.year
    if album_info.genre: metadata["genre"] = album_info.genre
    if album_info.label: metadata["label"] = album_info.label
    if album_info.comment: metadata["comment"] = album_info.comment
    
    # Adiciona metadados
    for key, value in metadata.items():
        cmd.extend(["-metadata", f"{key}={value}"])
    
    # Arquivo de saída
    cmd.extend(["-y", output_file])
    
    try:
        # Converte o áudio
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            log_message(f"✗ ERRO FFmpeg: {result.stderr}", "ERROR")
            return False
        
        # PASSO 2: Adiciona capa com metaflac (se disponível e se há capa)
        if cover_image and os.path.exists(cover_image) and os.path.exists(output_file):
            if METAFLAC_PATH:
                try:
                    # Usa metaflac para adicionar a capa (método ideal para FLAC)
                    metaflac_cmd = [
                        METAFLAC_PATH,
                        "--import-picture-from=" + f"3||||{cover_image}",
                        output_file
                    ]
                    metaflac_result = subprocess.run(
                        metaflac_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    if metaflac_result.returncode != 0:
                        log_message(f"metaflac falhou, usando método alternativo: {metaflac_result.stderr}", "WARNING")
                        # Remove arquivo sem capa antes de tentar método alternativo
                        if os.path.exists(output_file):
                            os.remove(output_file)
                        return embed_cover_ffmpeg_alternative(wav_file, output_file, cover_image, metadata)
                    
                    # Sucesso! A capa foi adicionada ao arquivo existente
                    # Não há necessidade de excluir nada pois metaflac modifica o arquivo in-place
                        
                except Exception as e:
                    log_message(f"Erro ao usar metaflac: {str(e)}, usando método alternativo", "WARNING")
                    # Remove arquivo sem capa antes de tentar método alternativo
                    if os.path.exists(output_file):
                        os.remove(output_file)
                    return embed_cover_ffmpeg_alternative(wav_file, output_file, cover_image, metadata)
            else:
                # metaflac não encontrado, usa método alternativo
                # Remove o arquivo sem capa primeiro
                log_message("metaflac não encontrado, recriando com método FFmpeg alternativo", "WARNING")
                if os.path.exists(output_file):
                    os.remove(output_file)
                return embed_cover_ffmpeg_alternative(wav_file, output_file, cover_image, metadata)
        
        return True
            
    except Exception as e:
        log_message(f"✗ EXCEÇÃO: {str(e)}", "ERROR")
        return False

def embed_cover_ffmpeg_alternative(wav_file, output_file, cover_image, metadata):
    """Método alternativo: reconverte usando FFmpeg com capa embutida"""
    try:
        # Remove o arquivo temporário sem capa (se existir)
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except Exception as e:
                log_message(f"Aviso: não foi possível remover arquivo temporário: {str(e)}", "WARNING")
        
        # Converte com capa incluída usando método de stream de vídeo
        cmd = [FFMPEG_PATH, "-i", wav_file, "-i", cover_image]
        cmd.extend(["-c:a", "flac", "-compression_level", "8"])
        
        for key, value in metadata.items():
            cmd.extend(["-metadata", f"{key}={value}"])
        
        # Adiciona stream de vídeo como attached_pic
        cmd.extend([
            "-map", "0:a",
            "-map", "1:v",
            "-c:v", "copy",
            "-disposition:v:0", "attached_pic",
            "-metadata:s:v", "title=Album cover",
            "-metadata:s:v", "comment=Cover (front)",
        ])
        
        cmd.extend(["-y", output_file])
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace')
        
        if result.returncode != 0:
            log_message(f"Método alternativo FFmpeg falhou: {result.stderr}", "ERROR")
            
        return result.returncode == 0
        
    except Exception as e:
        log_message(f"Método alternativo falhou: {str(e)}", "ERROR")
        return False

def main():
    print_header()
    
    if len(sys.argv) < 2:
        log_message("ERRO: Nenhuma pasta fornecida", "ERROR")
        sys.exit(1)
    
    # TRATAMENTO CRÍTICO: O Windows às vezes passa caminhos com aspas extras ou 
    # barras invertidas no final que escapam a aspa de fechamento.
    input_folder = sys.argv[1].strip().strip('"')
    # Remove barra invertida final se existir (evita problemas de escape no Windows)
    if input_folder.endswith('\\'):
        input_folder = input_folder[:-1]
    
    if not os.path.isdir(input_folder):
        log_message(f"ERRO: '{input_folder}' não é uma pasta válida", "ERROR")
        sys.exit(1)
    
    log_message(f"Pasta de entrada: {input_folder}")
    
    if not os.path.exists(FFMPEG_PATH):
        log_message(f"ERRO: FFmpeg não encontrado em: {FFMPEG_PATH}", "ERROR")
        sys.exit(1)
    
    # Informa sobre metaflac
    if METAFLAC_PATH:
        log_message(f"metaflac encontrado: {METAFLAC_PATH}")
    else:
        log_message("metaflac não encontrado - capas serão embutidas via FFmpeg", "WARNING")
    print()
    
    # SELEÇÃO DE MODO
    mode = select_conversion_mode()
    print()
    
    output_folder = os.path.join(input_folder, "FLAC_Output")
    os.makedirs(output_folder, exist_ok=True)
    log_message(f"Pasta de saída: {output_folder}")
    print()
    
    album_info = None
    cover_image = None
    
    # MODO 1: MANUAL
    if mode == 1:
        log_message("Modo MANUAL selecionado")
        print()
        gabarito_path = os.path.join(input_folder, GABARITO_FILENAME)
        album_info = parse_gabarito(gabarito_path)
        
        if not album_info:
            sys.exit(1)
        
        cover_image = find_cover_image(input_folder)
    
    # MODO 2: SEMI-AUTOMÁTICO
    elif mode == 2:
        log_message("Modo SEMI-AUTOMÁTICO selecionado")
        
        # Extrai artista e álbum do nome da pasta
        artist, album = parse_folder_name(input_folder)
        
        # Permite confirmação/edição/URL
        artist, album, url = confirm_or_edit_metadata(artist, album)
        
        if url:
            # Usuário forneceu URL do MusicBrainz
            release_id = extract_release_id_from_url(url)
            if not release_id:
                log_message("ERRO: URL inválida do MusicBrainz", "ERROR")
                sys.exit(1)
            
            log_message(f"Usando release ID da URL: {release_id}")
            release_details = get_release_details(release_id)
            
            if not release_details:
                log_message("ERRO: Não foi possível obter detalhes do release", "ERROR")
                sys.exit(1)
            
            album_info = parse_musicbrainz_to_albuminfo(release_details)
        
        elif not artist or not album:
            log_message("Cancelado pelo usuário", "ERROR")
            sys.exit(1)
        
        else:
            # Busca normal no MusicBrainz
            releases = search_musicbrainz_release(artist, album)
            
            if not releases:
                log_message("Nenhum resultado encontrado. Tente com URL direta do MusicBrainz ou use modo MANUAL.", "ERROR")
                sys.exit(1)
            
            # Se encontrou múltiplos, deixa usuário escolher
            if len(releases) > 1:
                selected_release = select_release_interactive(releases)
                if not selected_release:
                    log_message("Cancelado pelo usuário", "ERROR")
                    sys.exit(1)
            else:
                selected_release = releases[0]
                log_message(f"Release encontrado: {selected_release.get('title', 'N/A')}")
                print()
            
            # Busca detalhes completos
            release_details = get_release_details(selected_release['id'])
            if not release_details:
                log_message("ERRO: Não foi possível obter detalhes do release", "ERROR")
                sys.exit(1)
            
            album_info = parse_musicbrainz_to_albuminfo(release_details)
        
        print()
        
        # Usa capa local
        cover_image = find_cover_image(input_folder)
        if not cover_image:
            log_message("AVISO: Nenhuma capa local encontrada", "WARNING")
    
    # MODO 3: AUTOMÁTICO COMPLETO
    elif mode == 3:
        log_message("Modo AUTOMÁTICO COMPLETO selecionado")
        
        # Extrai artista e álbum do nome da pasta
        artist, album = parse_folder_name(input_folder)
        
        # Permite confirmação/edição/URL
        artist, album, url = confirm_or_edit_metadata(artist, album)
        
        release_id = None
        
        if url:
            # Usuário forneceu URL do MusicBrainz
            release_id = extract_release_id_from_url(url)
            if not release_id:
                log_message("ERRO: URL inválida do MusicBrainz", "ERROR")
                sys.exit(1)
            
            log_message(f"Usando release ID da URL: {release_id}")
        
        elif not artist or not album:
            log_message("Cancelado pelo usuário", "ERROR")
            sys.exit(1)
        
        else:
            # Busca normal no MusicBrainz
            releases = search_musicbrainz_release(artist, album)
            
            if not releases:
                log_message("Nenhum resultado encontrado. Tente com URL direta do MusicBrainz ou use modo MANUAL.", "ERROR")
                sys.exit(1)
            
            # Se encontrou múltiplos, deixa usuário escolher
            if len(releases) > 1:
                selected_release = select_release_interactive(releases)
                if not selected_release:
                    log_message("Cancelado pelo usuário", "ERROR")
                    sys.exit(1)
            else:
                selected_release = releases[0]
                log_message(f"Release encontrado: {selected_release.get('title', 'N/A')}")
                print()
            
            release_id = selected_release['id']
        
        # Busca detalhes completos
        release_details = get_release_details(release_id)
        if not release_details:
            log_message("ERRO: Não foi possível obter detalhes do release", "ERROR")
            sys.exit(1)
        
        album_info = parse_musicbrainz_to_albuminfo(release_details)
        print()
        
        # Baixa capa automaticamente
        cover_path = os.path.join(input_folder, "cover_downloaded.jpg")
        if download_cover_art(release_id, cover_path):
            cover_image = cover_path
        else:
            log_message("Capa não disponível online, tentando local...", "WARNING")
            cover_image = find_cover_image(input_folder)
    
    print()
    
    if not album_info:
        log_message("ERRO: Não foi possível obter informações do álbum", "ERROR")
        sys.exit(1)
    
    # Lista arquivos WAV
    wav_files = find_wav_files(input_folder)
    
    if not wav_files:
        log_message("ERRO: Nenhum arquivo WAV encontrado", "ERROR")
        sys.exit(1)
    
    print()
    
    # Verifica se há faixas suficientes
    if len(album_info.tracks) < len(wav_files):
        log_message(f"AVISO: Banco de dados tem {len(album_info.tracks)} faixas, mas foram encontrados {len(wav_files)} arquivos WAV", "WARNING")
        log_message("Faixas sem nome receberão nomes padrão", "WARNING")
        print()
    
    # Converte cada arquivo
    log_message("Iniciando conversões...")
    print()
    
    total_tracks = len(wav_files)
    successful = 0
    
    for idx, wav_file in enumerate(wav_files, 1):
        # Usa o nome da faixa do gabarito/API para o arquivo de saída
        track_title = album_info.tracks[idx - 1] if idx <= len(album_info.tracks) else f"Track {idx}"
        
        # Sanitiza o nome do arquivo (remove caracteres inválidos)
        safe_filename = sanitize_filename(track_title)
        output_filename = f"{idx:02d} - {safe_filename}.flac"
        output_file = os.path.join(output_folder, output_filename)
        
        if convert_wav_to_flac(wav_file, output_file, album_info, idx, total_tracks, cover_image):
            successful += 1
            print(f"  ✓ OK")
        else:
            print(f"  ✗ FALHA")
    
    print("\n" + "=" * 60)
    log_message(f"CONCLUÍDO: {successful}/{total_tracks} arquivos convertidos.")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)