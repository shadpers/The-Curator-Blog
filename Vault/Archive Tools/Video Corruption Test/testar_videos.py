import subprocess
import sys
import csv
import json
from pathlib import Path
import time
from datetime import datetime
import argparse
from tqdm import tqdm
from colorama import init, Fore, Style
from tabulate import tabulate
import winsound
import os
from multiprocessing import Pool, Manager

init()

VLC_PATH = r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
FFMPEG_PATH = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"

def verificar_dependencias():
    for path, name in [(VLC_PATH, "VLC"), (FFMPEG_PATH, "FFmpeg"), (FFPROBE_PATH, "FFprobe")]:
        if not os.path.exists(path):
            print(f"{Fore.RED}Erro: {name} não encontrado em {path}. Verifique a instalação.{Style.RESET_ALL}")
            return False
    return True

def obter_duracao(video_path):
    try:
        result = subprocess.run([
            FFPROBE_PATH,
            "-v", "error",
            "-read_intervals", "%+#1",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=10,
           creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return None
    except Exception:
        return None

def testar_ffmpeg(video_path):
    try:
        result = subprocess.run([
            FFMPEG_PATH,
            "-v", "error",
            "-err_detect", "aggressive",
            "-i", str(video_path),
            "-f", "null", "-"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=300,
           creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0 and not result.stderr.strip():
            return True, ""
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout (ffmpeg demorou demais)"
    except Exception as e:
        return False, str(e)

def extrair_erro_relevante(stderr):
    if not stderr:
        return "Não conseguiu reproduzir o vídeo"
    for line in stderr.splitlines():
        if any(keyword in line.lower() for keyword in [
            "moov atom not found",
            "could not open",
            "no valid stream",
            "failed to decode",
            "cannot open",
            "error: ",
            "failed to play",
            "invalid data",
            "decoding error",
            "corrupted frame"
        ]):
            return line.strip()[:200]
    return stderr.splitlines()[0].strip()[:200] if stderr.splitlines() else "Erro desconhecido"

def testar_vlc_abertura(video_path):
    try:
        result = subprocess.run([
            VLC_PATH,
            "--intf", "dummy",
            "--play-and-exit",
            "--no-audio",
            "--vout", "dummy",
            "--no-loop",
            "--no-repeat",
            "--no-interact",
            "--no-video-title-show",
            "--no-sub-autodetect-file",
            "--run-time=30",
            "--file-caching=50",
            "--demux=avformat",
            "--verbose=2",
            str(video_path),
            "vlc://quit"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35, encoding='utf-8', errors='ignore',
           creationflags=subprocess.CREATE_NO_WINDOW)

        error_keywords = [
            "moov atom not found",
            "could not open",
            "no valid stream",
            "failed to decode",
            "cannot open",
            "error: ",
            "failed to play",
            "invalid data",
            "decoding error",
            "corrupted frame"
        ]
        stderr = result.stderr.lower()
        if result.returncode == 0 and not any(keyword in stderr for keyword in error_keywords):
            return True, ""
        return False, extrair_erro_relevante(result.stderr)
    except subprocess.TimeoutExpired:
        return False, "Não conseguiu reproduzir os primeiros 30 segundos (timeout)"
    except Exception as e:
        return False, str(e)

def testar_vlc(video_path):
    try:
        result = subprocess.run([
            VLC_PATH,
            "--intf", "dummy",
            "--play-and-exit",
            "--no-audio",
            "--vout", "dummy",
            "--no-interact",
            "--no-video-title-show",
            "--no-sub-autodetect-file",
            "--rate=50",
            str(video_path)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, encoding='utf-8', errors='ignore',
           creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0:
            return True, ""
        return False, extrair_erro_relevante(result.stderr)
    except subprocess.TimeoutExpired:
        return False, "Timeout (VLC demorou demais)"
    except Exception as e:
        return False, str(e)

def processar_video(args):
    video_path, log_lines = args
    video = Path(video_path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resultado = {"arquivo": video.name, "duracao": "??", "status": "ERRO", "detalhes": ""}

    output_lines = []

    if not video.exists():
        output_lines.append(f"{Fore.RED}[ERRO] {video.name} (arquivo não encontrado){Style.RESET_ALL}\n")
        log_lines.append(f"[{timestamp}] [ERRO] {video} (arquivo não encontrado)\n")
        resultado["detalhes"] = "Arquivo não encontrado"
        return resultado, output_lines, {"OK": 0, "AVISO": 0, "FALHA": 0, "ERRO": 1, "TIMEOUT_VLC": 0}

    output_lines.append(f"{Fore.YELLOW}Analisando: {video.name}{Style.RESET_ALL}")
    log_lines.append(f"[{timestamp}] Analisando: {video}\n")
    
    duracao = obter_duracao(video)
    resultado["duracao"] = f"{duracao:.2f}" if duracao else "??"
    output_lines.append(f"  Duração: {duracao:.2f}s" if duracao else "  Duração: Não detectada")
    log_lines.append(f"[{timestamp}] Duração: {duracao:.2f}s\n" if duracao else f"[{timestamp}] Duração: Não detectada\n")

    stats = {"OK": 0, "AVISO": 0, "FALHA": 0, "ERRO": 0, "TIMEOUT_VLC": 0}
    ok_ff, msg_ff = testar_ffmpeg(video)
    if ok_ff:
        resultado["status"] = "OK"
        resultado["detalhes"] = "Sem erros"
        output_lines.append(f"{Fore.GREEN}  FFmpeg: OK{Style.RESET_ALL}")
        log_lines.append(f"[{timestamp}] FFmpeg: OK\n")
        stats["OK"] = 1
    else:
        output_lines.append(f"{Fore.YELLOW}  FFmpeg: Erro detectado, testando com VLC...{Style.RESET_ALL}")
        log_lines.append(f"[{timestamp}] FFmpeg: Erro ({msg_ff})\n")
        ok_vlc_abertura, msg_vlc_abertura = testar_vlc_abertura(video)
        if not ok_vlc_abertura:
            resultado["status"] = "FALHA"
            resultado["detalhes"] = msg_vlc_abertura
            output_lines.append(f"{Fore.RED}  VLC: Falha ({resultado['detalhes']}){Style.RESET_ALL}")
            log_lines.append(f"[{timestamp}] VLC: Falha ({resultado['detalhes']})\n")
            stats["FALHA"] = 1
        else:
            ok_vlc, msg_vlc = testar_vlc(video)
            if ok_vlc:
                resultado["status"] = "AVISO"
                resultado["detalhes"] = "FFmpeg reportou erro, mas VLC reproduziu"
                output_lines.append(f"{Fore.YELLOW}  VLC: OK{Style.RESET_ALL}")
                log_lines.append(f"[{timestamp}] VLC: OK\n")
                stats["AVISO"] = 1
            else:
                resultado["status"] = "FALHA"
                resultado["detalhes"] = msg_vlc
                output_lines.append(f"{Fore.RED}  VLC: Falha ({resultado['detalhes']}){Style.RESET_ALL}")
                log_lines.append(f"[{timestamp}] VLC: Falha ({resultado['detalhes']})\n")
                if "Timeout" in msg_vlc:
                    stats["TIMEOUT_VLC"] = 1

    output_lines.append("")
    return resultado, output_lines, stats

def main():
    parser = argparse.ArgumentParser(description="Testar integridade de vídeos.")
    parser.add_argument("filelist", help="Arquivo com a lista de vídeos")
    parser.add_argument("--only-failures", action="store_true", help="Mostra apenas vídeos com FALHA ou ERRO na tabela")
    parser.add_argument("--workers", type=int, default=1, help="Número de processos paralelos (padrão: 1)")
    args = parser.parse_args()

    if not verificar_dependencias():
        return

    filelist = Path(args.filelist)
    if not filelist.exists():
        print(f"{Fore.RED}Arquivo de lista não encontrado: {filelist}{Style.RESET_ALL}")
        return

    relatorio_txt = Path("relatorio.txt")
    relatorio_csv = Path("relatorio.csv")
    relatorio_json = Path("relatorio.json")
    log_detalhado_path = Path("log_detalhado.txt")

    videos = []
    seen = set()
    with open(filelist, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            video = line.strip()
            if video and video not in seen:
                videos.append(video)
                seen.add(video)
    total_videos = len(videos)

    print(f"\n{Fore.CYAN}Iniciando análise de {total_videos} vídeos com {args.workers} processos...{Style.RESET_ALL}\n")

    manager = Manager()
    log_lines = manager.list()
    global_stats = {"OK": 0, "AVISO": 0, "FALHA": 0, "ERRO": 0, "TIMEOUT_VLC": 0}

    with open(relatorio_txt, "w", encoding="utf-8") as txt, \
         open(relatorio_csv, "w", newline="", encoding="utf-8") as csvfile, \
         open(log_detalhado_path, "w", encoding="utf-8") as log:

        writer = csv.writer(csvfile)
        writer.writerow(["Arquivo", "Duração (s)", "Status", "Detalhes"])

        with Pool(processes=args.workers) as pool:
            results = []
            with tqdm(total=total_videos, desc="Processando vídeos", unit="vídeo",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                futures = [pool.apply_async(processar_video, ((video, log_lines),)) for video in videos]
                for i, future in enumerate(futures):
                    resultado, output_lines, local_stats = future.get()
                    results.append(resultado)
                    for key in global_stats:
                        global_stats[key] += local_stats[key]
                    for line in output_lines:
                        pbar.write(line)   # Usa pbar.write em vez de print
                    txt.write(f"[{resultado['status']}] {resultado['arquivo']} | duração: {resultado['duracao']} s -> {resultado['detalhes']}\n")
                    writer.writerow([resultado["arquivo"], resultado["duracao"], resultado["status"], resultado["detalhes"]])
                    pbar.update(1)
                    time.sleep(0.1)

        log_lines_sorted = sorted(log_lines, key=lambda x: x[1:20])
        for log_line in log_lines_sorted:
            log.write(log_line)

    tabela_resultados = [[r["arquivo"], r["duracao"], r["status"], r["detalhes"][:100] + "..." if len(r["detalhes"]) > 100 else r["detalhes"]] for r in results]
    if args.only_failures:
        tabela_resultados = [r for r in tabela_resultados if r[2] in ["FALHA", "ERRO"]]

    print(f"\n{Fore.CYAN}Tabela de Resultados:{Style.RESET_ALL}")
    print(tabulate(tabela_resultados, headers=["Arquivo", "Duração (s)", "Status", "Detalhes"], tablefmt="grid", maxcolwidths=[30, 10, 10, 50]))

    with open(relatorio_json, "w", encoding="utf-8") as json_file:
        json.dump({"stats": global_stats, "resultados": results}, json_file, ensure_ascii=False, indent=2)

    print(f"\n{Fore.GREEN}Análise concluída!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Resumo final: OK={global_stats['OK']}, AVISO={global_stats['AVISO']}, FALHA={global_stats['FALHA']}, ERRO={global_stats['ERRO']}, TIMEOUT_VLC={global_stats['TIMEOUT_VLC']}{Style.RESET_ALL}")
    print(f"Relatórios gerados: relatorio.txt, relatorio.csv, relatorio.json, log_detalhado.txt")
    winsound.Beep(1000, 500)

if __name__ == "__main__":
    main()
