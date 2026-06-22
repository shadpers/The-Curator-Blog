import subprocess
import sys
import os
import ctypes
import tempfile
import struct
import random

# Habilita ANSI no terminal Windows
try:
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

# Caminhos comuns de instalação do MKVToolNix (em ordem de prioridade)
# O script tenta cada um; se nenhum funcionar, tenta direto pelo PATH do sistema.
_MKVTOOLNIX_CANDIDATES = [
    r"C:\MKVToolNix",
    r"C:\Program Files\MKVToolNix",
    r"C:\Program Files (x86)\MKVToolNix",
]

def _find_tool(name):
    import shutil
    for folder in _MKVTOOLNIX_CANDIDATES:
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    # Tenta pelo PATH do sistema (funciona se MKVToolNix estiver no PATH)
    found = shutil.which(name)
    if found:
        return found
    # Fallback: deixa o subprocess tentar e vai falhar com mensagem clara
    return name

MKVEXTRACT_PATH = _find_tool("mkvextract.exe")
MKVMERGE_PATH   = _find_tool("mkvmerge.exe")

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

CHAPTERS_EXT    = ".chapters.txt"
FILE_HEADER_PRE = "### "

# ─────────────────────────────────────────────
# Helpers visuais
# ─────────────────────────────────────────────

def colored(text, color):
    return f"{color}{text}{RESET}{WHITE}"

def bold(text):
    return f"{BOLD}{WHITE}{text}{RESET}{WHITE}"

def dim(text):
    return f"{DIM}{text}{RESET}{WHITE}"

# ─────────────────────────────────────────────
# Contagem de capítulos numa string OGM
# ─────────────────────────────────────────────

def count_chapters(ogm_text):
    return sum(
        1 for line in ogm_text.splitlines()
        if line.upper().startswith("CHAPTER") and "NAME" not in line.upper()
    )

# ─────────────────────────────────────────────
# MODO EXTRAÇÃO
# ─────────────────────────────────────────────

def extract_chapters_raw(mkv_file):
    """
    Usa mkvextract para extrair capítulos em formato OGM (--simple).
    Retorna a string com conteúdo ou None em caso de falha.
    Retorna "" se o arquivo não tiver capítulos.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    os.close(tmp_fd)
    try:
        cmd = [MKVEXTRACT_PATH, mkv_file, "chapters", "--simple", tmp_path]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Log de diagnóstico
        print(f"{WHITE}  {dim('[DEBUG] returncode: ' + str(result.returncode))}{RESET}")
        if result.stdout.strip():
            print(f"{WHITE}  {dim('[DEBUG] stdout: ' + result.stdout.strip()[:400])}{RESET}")
        if result.stderr.strip():
            print(f"{WHITE}  {dim('[DEBUG] stderr: ' + result.stderr.strip()[:400])}{RESET}")

        # mkvextract: 0 = ok, 1 = avisos (chapters extraídos mesmo assim), 2 = erro fatal
        if result.returncode == 2:
            return None

        tmp_size = os.path.getsize(tmp_path)
        print(f"{WHITE}  {dim('[DEBUG] tmp file: ' + str(tmp_size) + ' bytes')}{RESET}")
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"{WHITE}  {dim('[DEBUG] content preview: ' + repr(content[:120]))}{RESET}")
        return content
    except FileNotFoundError:
        print(f"{WHITE}  {colored('✘ mkvextract não encontrado.', RED)}{RESET}")
        print(f"{WHITE}  {dim('Caminho tentado: ' + MKVEXTRACT_PATH)}{RESET}")
        print(f"{WHITE}  {dim('Instale o MKVToolNix ou adicione-o ao PATH do sistema.')}{RESET}")
        return None
    except Exception as e:
        print(f"{WHITE}  {dim('[DEBUG] exception: ' + str(e))}{RESET}")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def extract_mode(mkv_files):
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('MODO: EXTRAÇÃO DE CAPÍTULOS', CYAN))}{RESET}")
    print(f"{WHITE}  {dim(str(len(mkv_files)) + ' arquivo(s) na fila')}{RESET}")
    print(SEP2)

    entries  = []   # (basename, content_or_None, status)
    ok_count = 0
    no_ch    = 0
    err      = 0

    for i, f in enumerate(mkv_files, 1):
        name = os.path.basename(f)
        print(f"\n{SEP}")
        print(f"{WHITE}  {bold('[' + str(i) + '/' + str(len(mkv_files)) + ']')} {name}{RESET}")
        print(SEP)

        raw = extract_chapters_raw(f)

        if raw is None:
            print(f"{WHITE}  {colored('✘ Falha na extração (mkvextract retornou erro)', RED)}{RESET}")
            entries.append((name, None, "error"))
            err += 1

        elif raw == "":
            print(f"{WHITE}  {colored('⚠ Nenhum capítulo encontrado neste arquivo', YELLOW)}{RESET}")
            entries.append((name, "", "empty"))
            no_ch += 1

        else:
            n = count_chapters(raw)
            print(f"{WHITE}  {colored('✔ ' + str(n) + ' capítulo(s) extraído(s)', GREEN)}{RESET}")
            entries.append((name, raw, "ok"))
            ok_count += 1

    # ── Monta o arquivo de saída ──────────────────────────────────────────
    header_lines = [
        "# ══════════════════════════════════════════════════════",
        "# Arquivo de capítulos — chapters_mkv",
        "# ──────────────────────────────────────────────────────",
        "# COMO USAR:",
        "#   1. Edite os nomes dos capítulos abaixo",
        "#      (apenas as linhas CHAPTERxxNAME=...)",
        "#   2. NÃO altere as linhas de timestamp (CHAPTERxx=...)",
        "#   3. NÃO altere as linhas ### nome_do_arquivo.mkv",
        "#   4. Salve o arquivo",
        "#   5. Arraste este arquivo + os MKVs originais no .bat",
        "# ══════════════════════════════════════════════════════",
        "",
    ]

    body_lines = []
    for name, content, status in entries:
        body_lines.append(f"{FILE_HEADER_PRE}{name}")
        if status == "ok":
            body_lines.append(content)
        elif status == "empty":
            body_lines.append("# (sem capítulos — arquivo ignorado na aplicação)")
        else:
            body_lines.append("# (erro na leitura — arquivo ignorado na aplicação)")
        body_lines.append("")

    out_dir  = os.path.dirname(mkv_files[0])
    out_path = os.path.join(out_dir, "capitulos_extraidos" + CHAPTERS_EXT)

    with open(out_path, "w", encoding="utf-8") as fout:
        fout.write("\n".join(header_lines + body_lines))

    # ── Resumo ────────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('ARQUIVO GERADO:', CYAN))}")
    print(f"  {colored(os.path.basename(out_path), WHITE)}")
    print(f"  {dim(out_path)}")
    print()
    ok_s  = colored(f"{ok_count} com capítulos", GREEN)
    no_s  = colored(f"{no_ch} sem capítulos", YELLOW)
    err_s = colored(f"{err} erro(s)", RED) if err else dim("0 erro(s)")
    print(f"  {ok_s}  |  {no_s}  |  {err_s}{RESET}")
    print(f"{SEP2}\n")

# ─────────────────────────────────────────────
# MODO APLICAÇÃO
# ─────────────────────────────────────────────

def parse_chapters_file(chapters_file):
    """
    Lê o .chapters.txt e retorna dict { basename_mkv: ogm_content }.
    Ignora entradas marcadas como sem capítulos ou com erro.
    """
    with open(chapters_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    result       = {}
    current_name = None
    current_buf  = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if line.startswith(FILE_HEADER_PRE):
            # Fecha entrada anterior
            if current_name is not None:
                content = "\n".join(current_buf).strip()
                if content and not content.startswith("#"):
                    result[current_name] = content
            current_name = line[len(FILE_HEADER_PRE):].strip()
            current_buf  = []

        elif current_name is not None:
            # Pula linhas de comentário dentro de uma seção
            stripped = line.strip()
            if not stripped.startswith("#"):
                current_buf.append(line)

    # Fecha última entrada
    if current_name is not None:
        content = "\n".join(current_buf).strip()
        if content and not content.startswith("#"):
            result[current_name] = content

    return result


def apply_to_file(mkv_file, ogm_content, index, total):
    name = os.path.basename(mkv_file)
    print(f"\n{SEP}")
    print(f"{WHITE}  {bold('[' + str(index) + '/' + str(total) + ']')} {name}{RESET}")
    print(SEP)

    base, ext = os.path.splitext(mkv_file)
    out_file  = f"{base} (chapters){ext}"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8-sig") as tmp:  # BOM necessário para mkvmerge no Windows reconhecer UTF-8
            tmp.write(ogm_content)

        cmd = [
            MKVMERGE_PATH,
            "-o", out_file,
            "--chapters", tmp_path,
            "--no-chapters", mkv_file
        ]

        print(f"{WHITE}  {dim('Saída: ' + os.path.basename(out_file))}\n{RESET}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # mkvmerge retorna 1 para avisos (não erros fatais)
        if result.returncode in (0, 1):
            print(f"{WHITE}  {colored('✔ Concluído', GREEN)}{RESET}")
            return True
        else:
            print(f"{WHITE}  {colored('✘ Erro (código ' + str(result.returncode) + ')', RED)}{RESET}")
            stderr_preview = result.stderr.strip()[:300]
            if stderr_preview:
                print(f"{WHITE}  {dim(stderr_preview)}{RESET}")
            return False

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def apply_mode(mkv_files, chapters_file):
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('MODO: APLICAÇÃO DE CAPÍTULOS', CYAN))}{RESET}")
    print(f"{WHITE}  {dim('Guia: ' + os.path.basename(chapters_file))}{RESET}")
    print(SEP2)

    chapters_map = parse_chapters_file(chapters_file)

    if not chapters_map:
        print(f"\n{WHITE}  {colored('✘ Nenhuma entrada válida no arquivo de capítulos.', RED)}{RESET}\n")
        return

    # ── Mostra o que foi carregado ────────────────────────────────────────
    print(f"\n{WHITE}  Capítulos carregados:{RESET}")
    for name, content in chapters_map.items():
        n = count_chapters(content)
        print(f"{WHITE}    {dim('•')} {name}  {dim('(' + str(n) + ' capítulo(s))')}{RESET}")

    # ── Cruza MKVs com o mapa ─────────────────────────────────────────────
    to_process = []
    skipped    = []

    for f in mkv_files:
        name = os.path.basename(f)
        if name in chapters_map:
            to_process.append((f, chapters_map[name]))
        else:
            skipped.append(name)

    if skipped:
        print(f"\n{WHITE}  {colored('⚠ Sem entrada no arquivo de capítulos (ignorados):', YELLOW)}{RESET}")
        for s in skipped:
            print(f"{WHITE}    {dim('•')} {s}{RESET}")

    if not to_process:
        print(f"\n{WHITE}  {colored('✘ Nenhum MKV corresponde ao arquivo de capítulos.', RED)}{RESET}\n")
        return

    # ── Processamento ─────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('PROCESSANDO ' + str(len(to_process)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)

    success = 0
    failed  = 0

    for i, (f, content) in enumerate(to_process, 1):
        ok = apply_to_file(f, content, i, len(to_process))
        if ok:
            success += 1
        else:
            failed += 1

    # ── Resumo ────────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    ok_s   = colored(f"{success} OK", GREEN)
    err_s  = colored(f"{failed} erro(s)", RED) if failed else dim("0 erro(s)")
    skip_s = colored(f"{len(skipped)} ignorado(s)", YELLOW) if skipped else dim("0 ignorado(s)")
    print(f"{WHITE}  {bold('CONCLUÍDO:')}  {ok_s}  |  {err_s}  |  {skip_s}{RESET}")
    print(f"{SEP2}\n")

# ─────────────────────────────────────────────
# MODO GERAÇÃO (chapters-only MKV)
# ─────────────────────────────────────────────

def _vint(n):
    """Codifica n como EBML vint (campo de tamanho). Suporta até ~256 MB."""
    if n <= 0x7E:
        return bytes([0x80 | n])
    elif n <= 0x3FFE:
        return struct.pack('>H', 0x4000 | n)
    elif n <= 0x1FFFFE:
        b = struct.pack('>I', 0x200000 | n)
        return b[1:]
    elif n <= 0x0FFFFFFE:
        return struct.pack('>I', 0x10000000 | n)
    else:
        return struct.pack('>Q', 0x0100000000000000 | n)


def _el(eid: bytes, data: bytes) -> bytes:
    """Envolve data em um elemento EBML com o ID dado."""
    return eid + _vint(len(data)) + data


def _uint_bytes(n: int) -> bytes:
    """Codifica inteiro sem sinal com o mínimo de bytes necessários."""
    if n == 0:
        return b'\x00'
    size = (n.bit_length() + 7) // 8
    return n.to_bytes(size, 'big')


def _parse_ogm_ts_ns(ts: str) -> int:
    """Converte timestamp OGM (HH:MM:SS.mmm) em nanosegundos."""
    h, m, rest = ts.split(':')
    if '.' in rest:
        s, frac = rest.split('.', 1)
        # OGM usa 3 casas decimais (ms); preenche até 9 para ns
        frac_ns = int(frac.ljust(9, '0')[:9])
    else:
        s, frac_ns = rest, 0
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1_000_000_000 + frac_ns


def _parse_ogm_to_chapters(ogm_text: str):
    """
    Parseia texto OGM → lista de (time_ns: int, name: str).
    Preserva a ordem original dos capítulos.
    """
    times = {}
    names = {}
    for line in ogm_text.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key_up = key.strip().upper()
        val    = val.strip()
        if not key_up.startswith('CHAPTER'):
            continue
        rest = key_up[7:]           # remove o prefixo "CHAPTER"
        if rest.endswith('NAME'):
            idx = rest[:-4]         # índice numérico, ex: "01"
            names[idx] = val
        else:
            times[rest] = val

    # Ordena pelo número do capítulo
    def sort_key(idx):
        try:
            return int(idx)
        except ValueError:
            return idx

    result = []
    for idx in sorted(times.keys(), key=sort_key):
        if idx in names:
            result.append((_parse_ogm_ts_ns(times[idx]), names[idx]))
    return result


def _build_chapters_mkv(ogm_text: str) -> bytes:
    """
    Constrói um MKV Matroska mínimo contendo apenas os capítulos,
    sem nenhuma faixa de vídeo/áudio/legenda.
    Escrito diretamente em binário EBML — sem dependência do mkvmerge.
    """
    chapters = _parse_ogm_to_chapters(ogm_text)

    # ── ChapterAtom para cada capítulo ────────────────────────────────────
    atoms = b''
    for ts_ns, name in chapters:
        uid = random.randint(1, 0xFFFF_FFFF_FFFF_FFFF)
        display = _el(
            b'\x80',                                        # ChapterDisplay
            _el(b'\x85', name.encode('utf-8'))         +   # ChapterString
            _el(b'\x43\x7C', b'und')                       # ChapterLanguage
        )
        atom = _el(
            b'\xB6',                                        # ChapterAtom
            _el(b'\x73\xC4', uid.to_bytes(8, 'big'))   +  # ChapterUID
            _el(b'\x91', _uint_bytes(ts_ns))            +  # ChapterTimeStart
            _el(b'\x98', b'\x00')                       +  # ChapterFlagHidden = 0
            _el(b'\x45\x98', b'\x01')                   +  # ChapterFlagEnabled = 1
            display
        )
        atoms += atom

    chapters_el = _el(
        b'\x10\x43\xA7\x70',                               # Chapters
        _el(b'\x45\xB9', atoms)                            # EditionEntry
    )

    # ── Info (obrigatório no Segment) ─────────────────────────────────────
    info = _el(
        b'\x15\x49\xA9\x66',                               # Info
        _el(b'\x2A\xD7\xB1', (1_000_000).to_bytes(3, 'big'))  +  # TimestampScale = 1 ms
        _el(b'\x4D\x80', b'chapters_mkv')                  +  # MuxingApp
        _el(b'\x57\x41', b'chapters_mkv')                     # WritingApp
    )

    # ── Segment (tamanho desconhecido = 0x01FFFFFFFFFFFFFF) ───────────────
    segment_data = info + chapters_el
    segment = b'\x18\x53\x80\x67' + b'\x01\xFF\xFF\xFF\xFF\xFF\xFF\xFF' + segment_data

    # ── EBML Header ───────────────────────────────────────────────────────
    hdr_data = (
        _el(b'\x42\x86', b'\x01')      +  # EBMLVersion = 1
        _el(b'\x42\xF7', b'\x01')      +  # EBMLReadVersion = 1
        _el(b'\x42\xF2', b'\x04')      +  # EBMLMaxIDLength = 4
        _el(b'\x42\xF3', b'\x08')      +  # EBMLMaxSizeLength = 8
        _el(b'\x42\x82', b'matroska')  +  # DocType = "matroska"
        _el(b'\x42\x87', b'\x04')      +  # DocTypeVersion = 4
        _el(b'\x42\x85', b'\x02')          # DocTypeReadVersion = 2
    )
    ebml_hdr = b'\x1A\x45\xDF\xA3' + _vint(len(hdr_data)) + hdr_data

    return ebml_hdr + segment


def generate_mode(chapter_files):
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('MODO: GERAÇÃO DE MKV DE CAPÍTULOS', CYAN))}{RESET}")
    print(f"{WHITE}  {dim(str(len(chapter_files)) + ' arquivo(s) de capítulos')}{RESET}")
    print(SEP2)

    total_ok  = 0
    total_err = 0

    for chapters_file in chapter_files:
        chapters_map = parse_chapters_file(chapters_file)
        out_dir      = os.path.dirname(chapters_file)

        if not chapters_map:
            print(f"\n{WHITE}  {colored('✘ Nenhuma entrada válida em: ' + os.path.basename(chapters_file), RED)}{RESET}")
            total_err += 1
            continue

        for mkv_name, ogm_content in chapters_map.items():
            # Nome de saída: "Arquivo.mkv" → "Arquivo_chapters.mkv"
            base     = mkv_name[:-4] if mkv_name.lower().endswith('.mkv') else mkv_name
            out_name = base + "_chapters.mkv"
            out_path = os.path.join(out_dir, out_name)

            print(f"\n{SEP}")
            print(f"{WHITE}  {bold(out_name)}{RESET}")
            print(SEP)

            n = count_chapters(ogm_content)
            print(f"{WHITE}  {dim(str(n) + ' capítulo(s) encontrado(s)')}{RESET}")

            try:
                mkv_bytes = _build_chapters_mkv(ogm_content)
                with open(out_path, 'wb') as f:
                    f.write(mkv_bytes)
                size_kb = len(mkv_bytes) / 1024
                print(f"{WHITE}  {colored('✔ Gerado', GREEN)}  {dim('(' + f'{size_kb:.1f} KB)')}{RESET}")
                total_ok += 1
            except Exception as e:
                print(f"{WHITE}  {colored('✘ Erro: ' + str(e), RED)}{RESET}")
                total_err += 1

    # ── Resumo ────────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    ok_s  = colored(f"{total_ok} gerado(s)", GREEN)
    err_s = colored(f"{total_err} erro(s)", RED) if total_err else dim("0 erro(s)")
    print(f"{WHITE}  {bold('CONCLUÍDO:')}  {ok_s}  |  {err_s}{RESET}")
    print(f"{SEP2}\n")

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(f"\n{WHITE}  Uso:")
        print(f"    {dim('Extração:')}  arraste um ou mais MKVs para o .bat")
        print(f"    {dim('Aplicação:')} arraste MKVs + arquivo .chapters.txt para o .bat")
        print(f"    {dim('Geração:')}   arraste apenas o arquivo .chapters.txt para o .bat{RESET}\n")
        return

    args = sys.argv[1:]

    mkv_files     = [f for f in args if f.lower().endswith(".mkv")        and os.path.isfile(f)]
    chapter_files = [f for f in args if f.lower().endswith(CHAPTERS_EXT) and os.path.isfile(f)]
    unknown       = [f for f in args if f not in mkv_files and f not in chapter_files]

    # ── Fila ─────────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print(f"{WHITE}  {bold(colored('FILA: ' + str(len(args)) + ' arquivo(s)', CYAN))}{RESET}")
    print(SEP2)
    for i, f in enumerate(args, 1):
        tag = ""
        if f in chapter_files:
            tag = f"  {colored('[guia de capítulos]', CYAN)}"
        elif f not in mkv_files:
            tag = f"  {colored('[ignorado]', YELLOW)}"
        print(f"{WHITE}  {dim('[' + str(i) + ']')} {os.path.basename(f)}{tag}{RESET}")

    if unknown:
        print(f"\n{WHITE}  {colored('⚠ Arquivo(s) não reconhecido(s) serão ignorados.', YELLOW)}{RESET}")

    # ── Despacha o modo ───────────────────────────────────────────────────
    if chapter_files and not mkv_files:
        # Apenas .chapters.txt → gera MKV de capítulos
        generate_mode(chapter_files)

    elif mkv_files and chapter_files:
        # MKVs + .chapters.txt → aplica capítulos
        chapters_file = chapter_files[0]
        if len(chapter_files) > 1:
            print(f"\n{WHITE}  {colored('⚠ Múltiplos arquivos .chapters.txt — usando:', YELLOW)} "
                  f"{os.path.basename(chapters_file)}{RESET}")
        apply_mode(mkv_files, chapters_file)

    elif mkv_files:
        # Apenas MKVs → extrai capítulos
        extract_mode(mkv_files)

    else:
        print(f"\n{WHITE}  {colored('✘ Nenhum arquivo .mkv ou .chapters.txt encontrado.', RED)}{RESET}\n")


if __name__ == "__main__":
    main()
