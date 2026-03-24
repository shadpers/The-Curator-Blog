import os
import subprocess
from pathlib import Path
from datetime import datetime
import json
from tqdm import tqdm
import re

# ===== CONFIGURAÇÕES =====
PASTA_ALVO = Path(__file__).parent
TAMANHO_MAXIMO_PARTE = 4_194_304_000  # 4 GB
CAMINHO_7ZIP = r"C:\Program Files\7-Zip\7z.exe"
CAMINHO_FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"
MODO_COMPRESSAO = "store"  # 'store' = sem compressão
BARRA_TAMANHO = 50  # blocos na barra
# =========================

def verificar_arquivo(caminho_inicial, nome_programa):
    caminho = Path(caminho_inicial.strip('"'))
    if not caminho.is_file():
        print(f"Erro: {nome_programa} não encontrado em '{caminho_inicial}'")
        novo_caminho = input(f"Digite o caminho correto para {nome_programa} (ou Enter para sair): ").strip('"')
        if not novo_caminho:
            exit()
        caminho = Path(novo_caminho)
        if not caminho.is_file():
            print(f"Caminho inválido. Encerrando.")
            exit()
    return caminho

def get_media_info(file_path):
    try:
        result = subprocess.run(
            [str(ffprobe_path), "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        info = json.loads(result.stdout)
        duration = None
        creation = None
        if "duration" in info.get("format", {}):
            try:
                duration = float(info["format"]["duration"])
            except:
                pass
        tags = info["format"].get("tags", {})
        date_str = tags.get("creation_time")
        if date_str:
            try:
                creation = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                pass
        return duration, creation
    except Exception:
        return None, None

def dividir_em_partes(arquivos):
    partes = []
    parte_atual = []
    tamanho_atual = 0
    inicio_idx = 1

    for idx, arquivo in enumerate(arquivos, start=1):
        tamanho_arq = arquivo.stat().st_size
        if parte_atual and (tamanho_atual + tamanho_arq > TAMANHO_MAXIMO_PARTE):
            partes.append((inicio_idx, idx - 1, parte_atual))
            parte_atual = []
            tamanho_atual = 0
            inicio_idx = idx
        parte_atual.append(arquivo)
        tamanho_atual += tamanho_arq

    if parte_atual:
        partes.append((inicio_idx, len(arquivos), parte_atual))
    return partes

def gerar_barra(perc):
    blocos = "█" * (perc * BARRA_TAMANHO // 100) + "-" * (BARRA_TAMANHO - perc * BARRA_TAMANHO // 100)
    return f"[{blocos}]"

def main():
    global sevenzip_path, ffprobe_path
    sevenzip_path = verificar_arquivo(CAMINHO_7ZIP, "7z.exe")
    ffprobe_path = verificar_arquivo(CAMINHO_FFPROBE, "ffprobe.exe")

    arquivos = [f for f in PASTA_ALVO.iterdir() if f.is_file() and f.suffix.lower() != ".bat" and f.name != Path(__file__).name]
    if not arquivos:
        print("Nenhum arquivo encontrado.")
        return

    print("Escolha a forma de ordenar os arquivos:")
    print("1 - Por tamanho")
    print("2 - Alfabeticamente")
    print("3 - Por duração (mídia)")
    print("4 - Por data de criação (mídia)")
    escolha = input("Opção: ").strip()

    duracoes = {}
    criacoes = {}

    if escolha in ("3", "4"):
        print("\nColetando informações de mídia...\n")
        for arq in tqdm(arquivos, desc="Lendo arquivos", unit="arq"):
            dur, cri = get_media_info(arq)
            duracoes[arq] = dur
            criacoes[arq] = cri

    # Ordenação
    if escolha == "1":
        arquivos.sort(key=lambda f: f.stat().st_size, reverse=True)
    elif escolha == "2":
        arquivos.sort(key=lambda f: f.name.lower())
    elif escolha == "3":
        arquivos.sort(key=lambda f: duracoes.get(f) or 0)
    elif escolha == "4":
        arquivos.sort(key=lambda f: (criacoes.get(f) or datetime.min).replace(tzinfo=None))
    else:
        print("Opção inválida!")
        return

    partes = dividir_em_partes(arquivos)
    total_partes = len(partes)

    print("\nIniciando compactação das partes...\n")
    padrao_percent = re.compile(r"^\s*(\d+)%\s+(\d+)\s+\+\s+(.+)$")

    for num_parte, (idx_ini, idx_fim, lista_arqs) in enumerate(partes, start=1):
        # >>> ÚNICA ALTERAÇÃO DE NOME <<<
        nome_zip = f"part_{num_parte:03d} ({idx_ini}-{idx_fim}).zip"
        caminho_zip = PASTA_ALVO / nome_zip
        print(f"Compactando {nome_zip} ({len(lista_arqs)} arquivos)...\n")

        # Criar listfile para o 7-Zip
        listfile = PASTA_ALVO / f"lista_{num_parte:03d}.txt"
        with open(listfile, "w", encoding="utf-8") as f:
            for arq in lista_arqs:
                f.write(f'"{arq}"\n')

        cmd = [
            str(sevenzip_path), "a",
            "-mx=0" if MODO_COMPRESSAO == "store" else "",
            "-bsp1",  # Força progresso em tempo real
            str(caminho_zip),
            f"@{listfile}"   # lista de arquivos aqui
        ]
        cmd = [c for c in cmd if c]

        processo = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        ultimo_perc = -1

        for linha in processo.stdout:
            linha = linha.rstrip()
            if (not linha 
                or re.match(r'^\s*\d+%\s*$', linha) 
                or linha.startswith("Scanning the drive:") 
                or re.match(r'^\s*\d+M Scan', linha)
                or re.match(r'^\s*\d+%\s*\+\s*.+$', linha)
               ):
                continue

            match = padrao_percent.match(linha)
            if match:
                perc = int(match.group(1))
                if perc != ultimo_perc:
                    ultimo_perc = perc
                    barra = gerar_barra(perc)
                    print(f"{barra} {linha}", end="\r", flush=True)
            else:
                print(linha)

        processo.wait()
        print(f"\n[{'█'*BARRA_TAMANHO}] 100% | Parte {num_parte}/{total_partes} concluída: {nome_zip}\n")

    print("✅ Todas as partes foram compactadas com sucesso!")

if __name__ == "__main__":
    main()