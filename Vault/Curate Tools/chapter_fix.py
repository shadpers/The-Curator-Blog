#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chapter Fix Tool - Detecta e corrige capítulos irregulares em arquivos MKV
O número correto de capítulos é detectado automaticamente pela moda do lote,
ou pode ser informado manualmente via -e / --expected.
"""

import subprocess
import sys
import json
import os
import xml.etree.ElementTree as ET
import tempfile
import shutil
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Optional

# Configurações - ajuste conforme necessário
MKVMERGE   = r"C:\Program Files\MKVToolNix\mkvmerge.exe"
MKVEXTRACT = r"C:\Program Files\MKVToolNix\mkvextract.exe"

BACKUP_ORIGINALS = True  # renomeia o original para .bak antes de sobrescrever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Executa um subprocesso com encoding UTF-8."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


def get_chapter_count(mkv_path: str) -> Optional[int]:
    """Retorna o número de capítulos do arquivo, ou None em caso de erro.

    mkvmerge -J retorna chapters como lista de EditionEntry, cada uma com
    num_entries = ChapterAtoms dentro. Somamos tudo para o total real.
    len() apenas contaria edições (quase sempre 1), não capítulos individuais.
    """
    result = run([MKVMERGE, "-J", mkv_path])
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        editions = data.get("chapters", [])
        if not editions:
            return 0
        return sum(e.get("num_entries", 0) for e in editions)
    except (json.JSONDecodeError, KeyError):
        return None

def get_chapter_titles(mkv_path: str) -> List[str]:
    """Extrai os títulos dos capítulos via mkvextract (XML temporário)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
            xml_path = tf.name
        result = run([MKVEXTRACT, mkv_path, "chapters", xml_path])
        if result.returncode != 0 or not Path(xml_path).exists():
            return []
        tree = ET.parse(xml_path)
        root = tree.getroot()
        titles = []
        for atom in root.iter("ChapterAtom"):
            display = atom.find("ChapterDisplay")
            if display is not None:
                string = display.find("ChapterString")
                if string is not None and string.text:
                    titles.append(string.text.strip())
        return titles
    except Exception:
        return []
    finally:
        try:
            Path(xml_path).unlink(missing_ok=True)
        except Exception:
            pass


def ask_expected_chapters(mkv_files: List[Path]) -> int:
    """
    Escaneia todos os MKVs, exibe a distribuição de capítulos encontrada
    e pede ao usuário que escolha o número correto.
    """
    print("[INFO] Escaneando capítulos de todos os arquivos...")
    counts = []
    titles_by_count: dict = {}  # count -> example title list
    for mkv in mkv_files:
        c = get_chapter_count(str(mkv))
        if c is not None and c > 0:
            counts.append(c)
            if c not in titles_by_count:
                titles = get_chapter_titles(str(mkv))
                titles_by_count[c] = titles

    if not counts:
        print("[ERRO] Nenhum arquivo com capítulos encontrado.")
        sys.exit(1)

    counter = Counter(counts)

    print()
    print("=" * 65)
    print("  DISTRIBUIÇÃO DE CAPÍTULOS ENCONTRADA")
    print("=" * 65)
    for val, freq in sorted(counter.items()):
        bar = "█" * freq
        titles = titles_by_count.get(val, [])
        titles_str = "(" + ", ".join(titles) + ")" if titles else ""
        print(f"  {val:3d} capítulos  →  {freq:3d} arquivo(s)  {bar}")
        if titles_str:
            print(f"       {titles_str}")
    print("=" * 65)

    while True:
        try:
            raw = input("\nQual é o número CORRETO de capítulos? ").strip()
            expected = int(raw)
            if expected <= 0:
                print("[ERRO] Digite um número maior que zero.")
                continue
            # Confirma se o valor faz sentido
            irregular = sum(1 for c in counts if c != expected)
            print(f"\n✓ Padrão definido: {expected} capítulos")
            print(f"  {len(counts) - irregular} arquivo(s) já corretos, {irregular} serão corrigidos.")
            confirm = input("Confirmar? (s/n): ").strip().lower()
            if confirm == "s":
                return expected
        except ValueError:
            print("[ERRO] Digite apenas um número inteiro.")


def extract_chapters_xml(mkv_path: str, xml_path: str) -> bool:
    """Extrai os capítulos do MKV como XML para xml_path."""
    result = run([MKVEXTRACT, mkv_path, "chapters", xml_path])
    return result.returncode == 0 and Path(xml_path).exists()


def trim_chapters_xml(xml_path: str, keep: int) -> bool:
    """
    Remove da árvore XML todos os ChapterAtom além dos primeiros `keep`.
    Retorna True se modificou algo.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as exc:
        print(f"    [ERRO] Falha ao parsear XML de capítulos: {exc}")
        return False

    # O formato do mkvextract é:
    #   <Chapters>
    #     <EditionEntry>
    #       <ChapterAtom>...</ChapterAtom>
    #       ...
    #     </EditionEntry>
    #   </Chapters>
    modified = False
    for edition in root.iter("EditionEntry"):
        atoms = edition.findall("ChapterAtom")
        if len(atoms) > keep:
            for atom in atoms[keep:]:
                edition.remove(atom)
            modified = True

    if modified:
        ET.indent(tree, space="  ")   # Python 3.9+
        tree.write(xml_path, encoding="unicode", xml_declaration=True)

    return modified


def apply_chapters(mkv_path: str, xml_path: str, backup: bool) -> bool:
    """
    Reescreve os capítulos do MKV in-place usando mkvpropedit.
    Se mkvpropedit não estiver disponível, faz muxing com mkvmerge.
    Retorna True em caso de sucesso.
    """
    mkvpropedit = str(Path(MKVMERGE).parent / "mkvpropedit.exe")

    if Path(mkvpropedit).exists():
        return _apply_via_propedit(mkv_path, xml_path, mkvpropedit, backup)
    else:
        return _apply_via_merge(mkv_path, xml_path, backup)


def _apply_via_propedit(mkv_path: str, xml_path: str, mkvpropedit: str, backup: bool) -> bool:
    """Usa mkvpropedit (sem remuxing, muito mais rápido)."""
    if backup:
        bak = mkv_path + ".bak"
        if not Path(bak).exists():
            shutil.copy2(mkv_path, bak)

    result = run([mkvpropedit, mkv_path, "--chapters", xml_path])
    if result.returncode != 0:
        print(f"    [ERRO mkvpropedit] {result.stderr.strip()}")
        return False
    return True


def _apply_via_merge(mkv_path: str, xml_path: str, backup: bool) -> bool:
    """Fallback: remux completo com mkvmerge (mais lento, mas funciona sempre)."""
    input_path = Path(mkv_path)
    tmp_path   = input_path.with_suffix(".tmp_fix.mkv")

    cmd = [
        MKVMERGE,
        "-o", str(tmp_path),
        "--chapters", xml_path,
        str(input_path),
    ]
    result = run(cmd)
    if result.returncode not in (0, 1):   # 1 = warnings (ok)
        print(f"    [ERRO mkvmerge] {result.stderr.strip()}")
        tmp_path.unlink(missing_ok=True)
        return False

    if backup:
        bak = str(input_path) + ".bak"
        if not Path(bak).exists():
            shutil.copy2(str(input_path), bak)

    tmp_path.replace(input_path)
    return True


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def scan_and_fix(directory: str, expected: Optional[int], dry_run: bool, save_expected: Optional[str] = None) -> None:
    folder = Path(directory)
    mkv_files = sorted(folder.rglob("*.mkv"))

    if not mkv_files:
        print("[AVISO] Nenhum arquivo MKV encontrado na pasta.")
        return

    print(f"\n[INFO] {len(mkv_files)} arquivo(s) encontrado(s) em: {folder}")

    if expected is None:
        expected = ask_expected_chapters(mkv_files)
    else:
        print(f"[INFO] Capítulos esperados: {expected} (definido via -e)")

    # Salva o valor escolhido para o .bat reutilizar na etapa de aplicação
    if save_expected:
        try:
            Path(save_expected).write_text(str(expected), encoding="utf-8")
        except Exception as exc:
            print(f"[AVISO] Não foi possível salvar --save-expected: {exc}")

    if dry_run:
        print("[INFO] MODO DRY-RUN — nenhum arquivo será modificado.\n")
    else:
        print()

    ok_list:      List[str] = []
    fixed_list:   List[Tuple[str, int]] = []
    error_list:   List[Tuple[str, str]] = []
    no_chap_list: List[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for mkv in mkv_files:
            name = mkv.name
            count = get_chapter_count(str(mkv))

            if count is None:
                error_list.append((name, "Falha ao ler metadados"))
                print(f"  ✗ {name}  →  erro ao ler")
                continue

            if count == 0:
                no_chap_list.append(name)
                print(f"  - {name}  →  sem capítulos")
                continue

            if count == expected:
                ok_list.append(name)
                titles = get_chapter_titles(str(mkv))
                titles_str = " (" + ", ".join(titles) + ")" if titles else ""
                print(f"  ✓ {name}  →  {count} capítulos (OK){titles_str}")
                continue

            # Capítulos irregulares
            extra = count - expected
            tag = f"+{extra} extra" if extra > 0 else f"{extra} faltando"
            titles = get_chapter_titles(str(mkv))
            titles_str = " (" + ", ".join(titles) + ")" if titles else ""
            print(f"  ► {name}  →  {count} capítulos ({tag}){titles_str}")

            if dry_run:
                fixed_list.append((name, count))
                continue

            # Extrai XML
            xml_path = os.path.join(tmpdir, mkv.stem + "_chapters.xml")
            if not extract_chapters_xml(str(mkv), xml_path):
                error_list.append((name, "Falha ao extrair capítulos"))
                print(f"    [ERRO] Não foi possível extrair capítulos.")
                continue

            # Trunca para `expected` capítulos (remove extras)
            if count > expected:
                modified = trim_chapters_xml(xml_path, expected)
                if not modified:
                    error_list.append((name, "XML não foi modificado"))
                    continue

            # Aplica de volta
            success = apply_chapters(str(mkv), xml_path, BACKUP_ORIGINALS)
            if success:
                fixed_list.append((name, count))
                print(f"    ✓ Corrigido! {count} → {expected} capítulos")
            else:
                error_list.append((name, "Falha ao aplicar capítulos corrigidos"))

    # ---------------------------------------------------------------------------
    # Relatório final
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  RELATÓRIO FINAL")
    print("=" * 65)

    print(f"\n  ✓ OK ({len(ok_list)} arquivo(s)):")
    for f in ok_list:
        print(f"      {f}")

    if fixed_list:
        verb = "Seriam corrigidos" if dry_run else "Corrigidos"
        print(f"\n  ► {verb} ({len(fixed_list)} arquivo(s)):")
        for f, old in fixed_list:
            print(f"      {f}  [{old} → {expected} capítulos]")

    if no_chap_list:
        print(f"\n  - Sem capítulos ({len(no_chap_list)} arquivo(s)):")
        for f in no_chap_list:
            print(f"      {f}")

    if error_list:
        print(f"\n  ✗ Erros ({len(error_list)} arquivo(s)):")
        for f, reason in error_list:
            print(f"      {f}  —  {reason}")

    print("\n" + "=" * 65)
    if not dry_run and fixed_list:
        if BACKUP_ORIGINALS:
            print("  Originais preservados como .bak na mesma pasta.")
        print(f"  {len(fixed_list)} arquivo(s) corrigido(s) com sucesso.")
    print("=" * 65 + "\n")


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main():
    import argparse

    # O Windows pode partir caminhos com espacos quando a barra invertida final
    # escapa a aspa de fechamento: "C:\pasta com espacos\" vira multiplos argv.
    # Reunimos todos os tokens nao-flag num unico caminho e removemos aspas extras.
    raw_args = sys.argv[1:]
    flags = []
    path_parts = []

    i = 0
    while i < len(raw_args):
        tok = raw_args[i]
        if tok == "--dry-run":
            flags.append(tok)
        elif tok in ("-e", "--expected", "--save-expected"):
            flags.append(tok)
            i += 1
            if i < len(raw_args):
                flags.append(raw_args[i])
        elif tok.startswith("-"):
            flags.append(tok)
        else:
            path_parts.append(tok)
        i += 1

    if path_parts:
        directory = " ".join(path_parts).strip('"').strip("'")
    else:
        directory = "."

    parser = argparse.ArgumentParser(
        description="Detecta e corrige capitulos irregulares em arquivos MKV."
    )
    parser.add_argument(
        "-e", "--expected",
        type=int,
        default=None,
        help="Numero correto de capitulos (padrao: detectado automaticamente pela moda do lote)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas analisa, sem modificar arquivos",
    )
    parser.add_argument(
        "--save-expected",
        default=None,
        metavar="FILE",
        help="Salva o numero de capitulos escolhido num arquivo (uso interno do .bat)",
    )
    args = parser.parse_args(flags)

    scan_and_fix(directory, args.expected, args.dry_run, args.save_expected)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Cancelado pelo usuário.")
        sys.exit(0)
    except Exception as exc:
        import traceback
        print(f"\n[ERRO CRÍTICO] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
