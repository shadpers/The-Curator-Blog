import os
import subprocess
import sys
from colorama import init, Fore, Style

init(autoreset=True)

# Caminho do 7-Zip
SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"

# 1GB exato em bytes
BYTES_PER_GB = 1048576000

# --- Pergunta o tamanho ---
raw_input = input(Fore.CYAN + "Digite o tamanho de cada parte em GB (ex: 1,5 ou 2): ")
raw_input = raw_input.replace(",", ".")
try:
    gigas = float(raw_input)
except ValueError:
    print(Fore.RED + "Valor inválido.")
    sys.exit(1)

split_size = int(gigas * BYTES_PER_GB)
print(Fore.YELLOW + f"\nCada parte terá {split_size} bytes ({gigas} GB).")

# --- Pergunta o nível de compressão ---
comp_input = input(Fore.CYAN + "Digite o nível de compressão (0 a 9, 0=sem compressão, 5=padrão, 9=máximo): ")
try:
    nivel_comp = int(comp_input)
    if not (0 <= nivel_comp <= 9):
        raise ValueError
except ValueError:
    print(Fore.RED + "Nível inválido, usando 5 (padrão).")
    nivel_comp = 5

print(Fore.YELLOW + f"Usando nível de compressão: {nivel_comp}\n")

# --- Vasculha a pasta atual ---
cwd = os.getcwd()
arquivos = [f for f in os.listdir(cwd) if os.path.isfile(f)]

# Remove scripts da lista
arquivos = [f for f in arquivos if not (f.endswith(".bat") or f.endswith(".py"))]

if not arquivos:
    print(Fore.RED + "Nenhum arquivo válido encontrado na pasta.")
    sys.exit(1)

# --- Função para barra de progresso ---
def barra_progresso(pct: int, largura: int = 40) -> str:
    pct = max(0, min(100, pct))
    blocos = int((pct / 100) * largura)
    return "[" + "#" * blocos + "-" * (largura - blocos) + f"] {pct}%"

# --- Compacta em sequência ---
for arquivo in arquivos:
    nome_base = os.path.splitext(arquivo)[0]
    saida = f"{nome_base}.zip"

    print(Fore.GREEN + f"\nCompactando: {arquivo}")
    print(Fore.MAGENTA + f"Saída: {saida}\n")

    cmd = [
        SEVEN_ZIP,
        "a",
        "-tzip",
        saida,
        arquivo,
        f"-v{split_size}b",
        f"-mx={nivel_comp}",
        "-bsp1"
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    for line in process.stdout:
        line = line.strip()

        if "%" in line:
            # Pega número antes do símbolo de porcentagem
            try:
                pct = int(line.split("%")[0].split()[-1])
                sys.stdout.write("\r" + Fore.CYAN + barra_progresso(pct))
                sys.stdout.flush()
            except ValueError:
                pass
        elif line:
            print(Style.DIM + line)

    process.wait()
    sys.stdout.write("\n")  # quebra linha após a barra

    if process.returncode == 0:
        print(Fore.GREEN + f"✅ Concluído: {saida}")
    else:
        print(Fore.RED + f"❌ Erro ao compactar {arquivo}")
