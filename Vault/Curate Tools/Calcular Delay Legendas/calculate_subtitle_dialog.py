# calculate_subtitle_dialog.py
import sys
import json
import subprocess
import os
import re
try:
    import win32com.client  # Para resolver arquivos .lnk
except ImportError:
    print("Erro: A biblioteca 'pywin32' é necessária para suportar arquivos .lnk. Instale com 'pip install pywin32'.")
    print("Erro: A biblioteca 'pywin32' é necessária para suportar arquivos .lnk. Instale com 'pip install pywin32'.", file=sys.stderr)
    sys.exit(1)
try:
    import pysrt  # Para ler arquivos .srt
except ImportError:
    print("Erro: A biblioteca 'pysrt' é necessária para ler arquivos .srt. Instale com 'pip install pysrt'.")
    print("Erro: A biblioteca 'pysrt' é necessária para ler arquivos .srt. Instale com 'pip install pysrt'.", file=sys.stderr)
    sys.exit(1)

# Força saída sem buffering
sys.stdout.reconfigure(line_buffering=True)

FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"  # Caminho fixo do ffprobe
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"    # Caminho fixo do ffmpeg para extrair legendas

# Ordem de prioridade de idiomas (com códigos alternativos)
LANGUAGE_PRIORITY = {
    'en': ['en', 'eng', 'english'],
    'es': ['es', 'spa', 'spanish'],
    'pt': ['pt', 'por', 'portuguese'],
    'fr': ['fr', 'fre', 'french'],
    'de': ['de', 'ger', 'german'],
    'it': ['it', 'ita', 'italian'],
    'ja': ['ja', 'jpn', 'japanese'],
    'ar': ['ar', 'ara', 'arabic'],
    'ru': ['ru', 'rus', 'russian'],
    'th': ['th', 'tha', 'thai'],
    'vi': ['vi', 'vie', 'vietnamese'],
    'ms': ['ms', 'may', 'malay'],
    'id': ['id', 'ind', 'indonesian']
}

def resolve_lnk_path(file_path):
    """Resolve o caminho real de um arquivo .lnk ou retorna o caminho original se não for um .lnk."""
    try:
        if file_path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            resolved_path = shortcut.TargetPath
            if not os.path.exists(resolved_path):
                error_msg = f"Erro: O arquivo referenciado pelo atalho {file_path} não existe: {resolved_path}"
                print(error_msg)
                print(error_msg, file=sys.stderr)
                sys.exit(1)
            return resolved_path
        return file_path
    except Exception as e:
        error_msg = f"Erro ao resolver o atalho {file_path}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def ffprobe_json(file_path):
    """Obtém informações do arquivo de vídeo usando ffprobe."""
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            error_msg = f"Erro ao executar ffprobe para {file_path}: {result.stderr}"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        return json.loads(result.stdout)
    except Exception as e:
        error_msg = f"Erro ao processar ffprobe para {file_path}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def get_subtitle_streams(data):
    """Obtém informações das streams de legendas do arquivo."""
    try:
        subtitles = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "subtitle":
                lang = stream.get("tags", {}).get("language", "unknown").lower()
                duration_str = stream.get("tags", {}).get("DURATION", None)
                if duration_str:
                    h, m, s = duration_str.split(":")
                    duration = int(h) * 3600 + int(m) * 60 + float(s)
                else:
                    duration = float(stream.get("duration", 0))
                subtitles.append({
                    "index": stream["index"],
                    "lang": lang,
                    "duration": duration,
                    "title": stream.get("tags", {}).get("title", "Sem título"),
                    "codec": stream.get("codec_name", "unknown")
                })
        return subtitles
    except Exception as e:
        error_msg = f"Erro ao processar streams de legendas: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def get_subtitle_stream_indices(data):
    """Obtém uma lista de índices de streams de legenda."""
    return [stream["index"] for stream in data.get("streams", []) if stream.get("codec_type") == "subtitle"]

def extract_subtitle(file_path, subtitle_index, output_srt):
    """Extrai a legenda do arquivo de vídeo para um arquivo .srt."""
    try:
        # Obtém informações do arquivo para mapear índices
        data = ffprobe_json(file_path)
        subtitle_indices = get_subtitle_stream_indices(data)
        if subtitle_index not in subtitle_indices:
            error_msg = f"Erro: Índice de legenda {subtitle_index} não encontrado no arquivo {file_path}."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        # Calcula o índice relativo da legenda
        relative_index = subtitle_indices.index(subtitle_index)
        # Verifica o codec da legenda
        subtitle_stream = next(s for s in data.get("streams", []) if s["index"] == subtitle_index)
        codec = subtitle_stream.get("codec_name", "unknown")
        supported_codecs = ["srt", "subrip", "ass", "ssa"]
        if codec not in supported_codecs:
            error_msg = f"Erro: Codec de legenda '{codec}' não suportado para extração em {file_path}. Codecs suportados: {', '.join(supported_codecs)}."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        cmd = [
            FFMPEG_PATH,
            "-y",  # Sobrescreve o arquivo de saída se existir
            "-i", file_path,
            "-map", f"0:s:{relative_index}",
            "-c:s", "srt",
            output_srt
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            error_msg = f"Erro ao extrair legenda de {file_path}: {result.stderr}"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(output_srt):
            error_msg = f"Erro: Arquivo de legenda {output_srt} não foi criado."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        # Verifica se o arquivo .srt é válido
        try:
            with open(output_srt, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                error_msg = f"Erro: Arquivo de legenda {output_srt} está vazio."
                print(error_msg)
                print(error_msg, file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            error_msg = f"Erro: Arquivo de legenda {output_srt} não é um arquivo .srt válido: {str(e)}"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        return output_srt
    except Exception as e:
        error_msg = f"Erro ao extrair legenda de {file_path}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def clean_text(text):
    """Remove ASS/SSA tags e HTML-like styling do texto da legenda."""
    # Remove ASS tags como {\an8} ou {\q2}
    text = re.sub(r'\{[^}]*}', '', text)
    # Remove tags <font>, <b>, etc.
    text = re.sub(r'<[^>]*>', '', text)
    # Remove espaços extras
    return ' '.join(text.split()).strip()

def read_srt_dialogues(srt_file):
    """Lê as 3 primeiras e 3 últimas linhas de diálogo válidas de um arquivo .srt, evitando duplicatas."""
    try:
        # Tenta abrir com diferentes codificações
        encodings = ['utf-8', 'latin-1', 'cp1252']
        subs = None
        for encoding in encodings:
            try:
                subs = pysrt.open(srt_file, encoding=encoding)
                break
            except Exception:
                continue
        if subs is None:
            error_msg = f"Erro: Não foi possível ler o arquivo .srt {srt_file} com as codificações {', '.join(encodings)}."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        if not subs:
            error_msg = f"Erro: Nenhuma legenda encontrada em {srt_file}."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        # Converte tempos para segundos e obtém texto
        dialogues = []
        seen = set()  # Para rastrear entradas únicas (texto, start_time, end_time)
        for sub in subs:
            raw_text = sub.text.replace('\n', ' ')
            cleaned = clean_text(raw_text)
            if len(cleaned) > 10 and len(cleaned.split()) > 1:  # Ignora linhas curtas ou tags-only
                start_time = sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds + sub.start.milliseconds / 1000
                end_time = sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds + sub.end.milliseconds / 1000
                key = (cleaned, start_time, end_time)  # Chave para verificar duplicatas
                if key not in seen:
                    seen.add(key)
                    dialogues.append({
                        "index": sub.index,
                        "text": cleaned,
                        "start_time": start_time,
                        "end_time": end_time
                    })
        if not dialogues:
            error_msg = f"Erro: Nenhuma legenda válida encontrada em {srt_file} após limpeza."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)
        # Retorna as 3 primeiras e 3 últimas válidas
        first_three = dialogues[:3]
        last_three = dialogues[-3:] if len(dialogues) >= 3 else dialogues
        return first_three, last_three
    except Exception as e:
        error_msg = f"Erro ao ler arquivo .srt {srt_file}: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def list_subtitles(subtitles, file_type):
    """Lista as legendas disponíveis e retorna a lista."""
    print(f"\nLegendas disponíveis no {file_type}:")
    for i, sub in enumerate(subtitles, 1):
        print(f"{i}. Lang={sub['lang']}, Title=\"{sub['title']}\", Duração={sub['duration']:.3f} s, Codec={sub['codec']}")
    return subtitles

def select_subtitle(subtitles, file_type):
    """Permite ao usuário selecionar uma legenda manualmente."""
    while True:
        try:
            choice = input(f"\nDigite o número da legenda para o {file_type}: ")
            choice = int(choice)
            if 1 <= choice <= len(subtitles):
                return subtitles[choice - 1]
            else:
                print(f"Por favor, escolha um número entre 1 e {len(subtitles)}.")
        except ValueError:
            print("Entrada inválida. Digite um número.")
        except Exception as e:
            error_msg = f"Erro ao selecionar legenda para {file_type}: {str(e)}"
            print(error_msg)
            print(error_msg, file=sys.stderr)

def auto_select_subtitle(subtitles, file_type):
    """Seleciona automaticamente uma legenda com base na ordem de prioridade de idiomas."""
    print(f"\nDepuração: Idiomas disponíveis em {file_type}: {[sub['lang'] for sub in subtitles]}")
    for lang_key, lang_codes in LANGUAGE_PRIORITY.items():
        matching_subs = [sub for sub in subtitles if sub['lang'] in lang_codes]
        # Prefere faixas que não sejam "Songs" ou "Full Subtitles"
        dialogue_only = [sub for sub in matching_subs if 'song' not in sub['title'].lower() and 'full' not in sub['title'].lower()]
        if dialogue_only:
            matching_subs = dialogue_only[:1]  # Escolhe a primeira faixa "limpa"
        if len(matching_subs) == 1:
            print(f"\nLegenda selecionada automaticamente para {file_type}: Lang={matching_subs[0]['lang']}, Title=\"{matching_subs[0]['title']}\", Duração={matching_subs[0]['duration']:.3f} s")
            return matching_subs[0]
        elif len(matching_subs) > 1:
            print(f"\nMúltiplas legendas encontradas para o idioma '{lang_key}' em {file_type}. Seleção manual necessária.")
            matching_subs = list_subtitles(matching_subs, f"{file_type} (idioma {lang_key})")
            return select_subtitle(matching_subs, f"{file_type} (idioma {lang_key})")
    print(f"\nNenhuma legenda com idioma prioritário ({', '.join(LANGUAGE_PRIORITY.keys())}) encontrada para {file_type}. Seleção manual necessária.")
    return select_subtitle(subtitles, file_type)

def compare_subtitles(bd_file, web_file):
    """Compara as legendas dos arquivos BD e WEB-DL."""
    try:
        # Resolve caminhos de atalhos .lnk
        bd_file = resolve_lnk_path(bd_file)
        web_file = resolve_lnk_path(web_file)

        # Obtém informações dos arquivos
        bd_data = ffprobe_json(bd_file)
        web_data = ffprobe_json(web_file)

        # Obtém streams de legendas
        bd_subs = get_subtitle_streams(bd_data)
        web_subs = get_subtitle_streams(web_data)

        if not bd_subs or not web_subs:
            error_msg = "Erro: Não encontrou legendas em um dos arquivos."
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)

        # Lista legendas disponíveis
        bd_subs = list_subtitles(bd_subs, "BD")
        web_subs = list_subtitles(web_subs, "WEB-DL")

        # Seleciona legendas automaticamente ou manualmente
        bd_selected_sub = auto_select_subtitle(bd_subs, "BD")
        web_selected_sub = auto_select_subtitle(web_subs, "WEB-DL")

        # Extrai legendas para arquivos temporários
        bd_srt = "temp_bd_sub.srt"
        web_srt = "temp_web_sub.srt"
        extract_subtitle(bd_file, bd_selected_sub["index"], bd_srt)
        extract_subtitle(web_file, web_selected_sub["index"], web_srt)

        # Lê as 3 primeiras e 3 últimas linhas de diálogo
        bd_first, bd_last = read_srt_dialogues(bd_srt)
        web_first, web_last = read_srt_dialogues(web_srt)

        # Exibe resultados
        print("\n===== RESULTADOS =====")
        print(f"\nLegenda selecionada BD: Lang={bd_selected_sub['lang']}, Title=\"{bd_selected_sub['title']}\", Duração={bd_selected_sub['duration']:.3f} s")
        print(f"Legenda selecionada WEB: Lang={web_selected_sub['lang']}, Title=\"{web_selected_sub['title']}\", Duração={web_selected_sub['duration']:.3f} s")
        print(f"\nBD TEM {len(bd_subs)} LEGENDAS")
        print(f"WEB-DL TEM {len(web_subs)} LEGENDAS\n")

        print("=== BD: 3 Primeiras Linhas de Diálogo ===")
        for d in bd_first:
            print(f"Índice: {d['index']}, Tempo: {d['start_time']:.3f}s - {d['end_time']:.3f}s, Texto: {d['text']}")
        print("\n=== BD: 3 Últimas Linhas de Diálogo ===")
        for d in bd_last:
            print(f"Índice: {d['index']}, Tempo: {d['start_time']:.3f}s - {d['end_time']:.3f}s, Texto: {d['text']}")

        print("\n=== WEB-DL: 3 Primeiras Linhas de Diálogo ===")
        for d in web_first:
            print(f"Índice: {d['index']}, Tempo: {d['start_time']:.3f}s - {d['end_time']:.3f}s, Texto: {d['text']}")
        print("\n=== WEB-DL: 3 Últimas Linhas de Diálogo ===")
        for d in web_last:
            print(f"Índice: {d['index']}, Tempo: {d['start_time']:.3f}s - {d['end_time']:.3f}s, Texto: {d['text']}")

        # Compara tempos
        print("\n=== Comparação de Tempos ===")
        print("Primeiras Linhas (BD vs WEB-DL):")
        for i in range(min(len(bd_first), len(web_first))):
            bd_start = bd_first[i]['start_time']
            web_start = web_first[i]['start_time']
            diff_start = bd_start - web_start
            print(f"Diálogo {i+1}: Início BD={bd_start:.3f}s, Início WEB={web_start:.3f}s, Diferença={diff_start:.3f}s")

        print("\nÚltimas Linhas (BD vs WEB-DL):")
        for i in range(min(len(bd_last), len(web_last))):
            bd_start = bd_last[i]['start_time']
            web_start = web_last[i]['start_time']
            diff_start = bd_start - web_start
            print(f"Diálogo {i+1}: Início BD={bd_start:.3f}s, Início WEB={web_start:.3f}s, Diferença={diff_start:.3f}s")

        # Calcula fator de expansão total
        bd_sub_dur = bd_selected_sub["duration"]
        web_sub_dur = web_selected_sub["duration"]
        sub_factor = bd_sub_dur / web_sub_dur if web_sub_dur != 0 else 0
        sub_diff = bd_sub_dur - web_sub_dur
        print(f"\nDiferença de duração total (legendas): {sub_diff:.3f} s")
        print(f"Fator de expansão exato (legendas): {sub_factor:.6f}")
        print("======================\n")

        # Limpa arquivos temporários
        os.remove(bd_srt)
        os.remove(web_srt)
    except Exception as e:
        error_msg = f"Erro ao comparar legendas: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

def main():
    try:
        if len(sys.argv) < 3:
            error_msg = "Uso: python calculate_subtitle_dialog.py <arquivo_BD> <arquivo_WEB>"
            print(error_msg)
            print(error_msg, file=sys.stderr)
            sys.exit(1)

        bd_path = sys.argv[1]
        web_path = sys.argv[2]

        print(f"BD original: {bd_path}")
        print(f"WEB original: {web_path}")

        compare_subtitles(bd_path, web_path)
    except Exception as e:
        error_msg = f"Erro no script: {str(e)}"
        print(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()