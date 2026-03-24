"""
Link Checker - Sistema Modular
Verifica status de links de diversos serviços de armazenamento

Adicione novos módulos criando arquivos module_*.py na mesma pasta
"""

import json
import os
import glob
import struct
import re
from datetime import datetime
from typing import List, Tuple, Dict, Optional
import importlib.util
import sys

# Cores ANSI
RESET = "\033[0m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
WHITE = "\033[97m"
GRAY = "\033[90m"
BOLD = "\033[1m"


class ModuleLoader:
    """Gerencia o carregamento dinâmico dos módulos de checkers"""
    
    def __init__(self):
        self.checkers = []
        self.load_modules()
    
    def load_modules(self):
        """Carrega automaticamente todos os módulos module_*.py"""
        # Procura por arquivos module_*.py no diretório atual
        module_files = glob.glob("module_*.py")
        
        # Remove module_base.py da lista
        module_files = [f for f in module_files if f != "module_base.py"]
        
        print(f"{GRAY}Carregando módulos...{RESET}")
        
        for module_file in sorted(module_files):
            try:
                # Nome do módulo sem extensão
                module_name = module_file[:-3]
                
                # Carrega o módulo dinamicamente
                spec = importlib.util.spec_from_file_location(module_name, module_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # Pega a instância do checker
                    if hasattr(module, 'checker'):
                        checker = module.checker
                        self.checkers.append(checker)
                        
                        # Mostra serviços suportados
                        domains_str = ", ".join(checker.domains[:3])
                        if len(checker.domains) > 3:
                            domains_str += "..."
                        print(f"  {GREEN}✓{RESET} {checker.service_name} ({domains_str})")
                    
            except Exception as e:
                print(f"  {RED}✗{RESET} Erro ao carregar {module_file}: {e}")
        
        print(f"{GRAY}Total: {len(self.checkers)} módulo(s) carregado(s){RESET}\n")
    
    def find_checker(self, url: str):
        """Encontra o checker apropriado para uma URL"""
        for checker in self.checkers:
            if checker.supports_url(url):
                return checker
        return None


def parse_lnk(filepath):
    """Extrai o caminho alvo de um atalho .lnk"""
    try:
        with open(filepath, 'rb') as f:
            content = f.read()

        # Verifica assinatura do .lnk
        if content[:4] != b'L\x00\x00\x00':
            return None

        # Flags do header (offset 0x14)
        flags = content[0x14]

        has_target_id_list = flags & 0x01
        has_link_info = flags & 0x02

        # Início após header fixo (76 bytes)
        pos = 76

        # Pula o LinkTargetIDList se presente
        if has_target_id_list:
            id_list_size = struct.unpack_from('<H', content, pos)[0]
            pos += 2 + id_list_size

        # Processa LinkInfo se presente
        if has_link_info:
            link_info_size = struct.unpack_from('<I', content, pos)[0]
            link_info_header_size = struct.unpack_from('<I', content, pos + 4)[0]
            link_info_flags = struct.unpack_from('<I', content, pos + 8)[0]
            local_base_path_offset = struct.unpack_from('<I', content, pos + 16)[0]
            common_path_suffix_offset = struct.unpack_from('<I', content, pos + 24)[0]

            # Offsets unicode se header maior
            if link_info_header_size >= 36:
                local_base_path_unicode_offset = struct.unpack_from('<I', content, pos + 28)[0]
                common_path_suffix_unicode_offset = struct.unpack_from('<I', content, pos + 32)[0]
            else:
                local_base_path_unicode_offset = None
                common_path_suffix_unicode_offset = None

            # Local base path
            if link_info_flags & 0x01:  # VolumeIDAndLocalBasePath
                if local_base_path_unicode_offset is not None and local_base_path_unicode_offset > 0:
                    local_base_path_pos = pos + local_base_path_unicode_offset
                    local_base_path = content[local_base_path_pos:].split(b'\x00\x00', 1)[0].decode('utf-16le', errors='replace')
                else:
                    local_base_path_pos = pos + local_base_path_offset
                    local_base_path = content[local_base_path_pos:].split(b'\x00', 1)[0].decode('cp1252', errors='replace')

                # Common path suffix
                if common_path_suffix_unicode_offset is not None and common_path_suffix_unicode_offset > 0:
                    common_path_suffix_pos = pos + common_path_suffix_unicode_offset
                    common_path_suffix = content[common_path_suffix_pos:].split(b'\x00\x00', 1)[0].decode('utf-16le', errors='replace')
                else:
                    common_path_suffix_pos = pos + common_path_suffix_offset
                    common_path_suffix = content[common_path_suffix_pos:].split(b'\x00', 1)[0].decode('cp1252', errors='replace')

                target = local_base_path + common_path_suffix
                target = os.path.normpath(target)
                
                return target
    except Exception as e:
        print(f"{RED}Erro ao parsear {filepath}: {e}{RESET}")
        return None

    return None


class LinkChecker:
    """Gerenciador principal do sistema de verificação de links"""
    
    def __init__(self, db_path='history.json', scans_path='scans_history.json'):
        self.db_path = db_path
        self.scans_path = scans_path
        self.history = self.load_history()
        self.module_loader = ModuleLoader()

    def load_history(self) -> dict:
        """Carrega histórico de verificações"""
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_history(self):
        """Salva histórico de verificações"""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)

    def load_scans_history(self) -> list:
        """Carrega histórico de scans"""
        if os.path.exists(self.scans_path):
            with open(self.scans_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('scans', [])
        return []

    def save_scans_history(self, scans: list):
        """Salva histórico de scans (mantém últimos 10)"""
        scans = scans[-10:]
        with open(self.scans_path, 'w', encoding='utf-8') as f:
            json.dump({'scans': scans}, f, indent=4, ensure_ascii=False)

    def parse_txt(self, filepath: str) -> List[Tuple[str, str]]:
        """
        Parseia o TXT ignorando emails e linhas vazias, coletando nome e links (incluindo multi-partes).
        Formato esperado:
        Nome do Item
        https://url1.com
        
        Outro Item
        PART 1 - https://url2.com
        PART 2 - https://url3.com
        """
        entries = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f.readlines()]

            i = 0
            while i < len(lines):
                line = lines[i]
                if not line or '@' in line:  # Ignora vazias e emails
                    i += 1
                    continue

                # Assume que a linha é o nome se não for URL ou PART
                if not re.match(r'https?://|PART', line, re.IGNORECASE):
                    name = re.sub(r'[\[\]]', '', line)  # Remove [] se necessário
                    i += 1
                    parts = []
                    part_num = 1
                    while i < len(lines) and lines[i]:
                        part_line = lines[i]
                        if '@' in part_line:  # Ignora emails
                            i += 1
                            continue
                        # Extrai URL da linha (pode ser "PART X - url" ou só url)
                        url_match = re.search(r'https?://\S+', part_line)
                        if url_match:
                            url = url_match.group(0)
                            part_name = f"{name} (Part {part_num})" if 'PART' in part_line.upper() else name
                            parts.append((part_name, url))
                            part_num += 1
                        i += 1
                    if parts:
                        if len(parts) == 1:
                            entries.append(parts[0])  # Nome simples se único
                        else:
                            entries.extend(parts)  # Adiciona cada part
                    continue
                i += 1
                
        except Exception as e:
            print(f"{RED}Erro ao ler {filepath}: {e}{RESET}")
        
        return entries

    def process_link(self, name: str, url: str) -> Tuple:
        """Processa um link e retorna informações"""
        # Busca no histórico
        key = f"{name}|{url}"
        prev_data = self.history.get(key, {})
        prev_status = prev_data.get('status', 'N/A')
        prev_count = prev_data.get('count', 'N/A')
        prev_date = prev_data.get('last_check', 'N/A')
        
        # Encontra checker apropriado
        checker = self.module_loader.find_checker(url)
        
        if checker:
            status, count = checker.check_link(url)
        else:
            status, count = "UNKNOWN", 0
        
        # Atualiza histórico
        self.history[key] = {
            'name': name,
            'url': url,
            'status': status,
            'count': count,
            'last_check': datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        
        return status, count, prev_status, prev_count, prev_date

    def show_offline_links(self, results: List[dict]):
        """Exibe apenas os links offline"""
        offline = [r for r in results if r['status'] == 'OFFLINE']
        
        if not offline:
            print(f"\n{GREEN}Nenhum link offline encontrado!{RESET}")
            return
        
        print(f"\n{RED}{BOLD}{'═' * 100}{RESET}")
        print(f"{RED}{BOLD}Links OFFLINE ({len(offline)}){RESET}")
        print(f"{RED}{BOLD}{'═' * 100}{RESET}\n")
        
        for entry in offline:
            print(f"{WHITE}{entry['name']}{RESET}")
            print(f"{GRAY}  TXT: {entry['txt_name']}{RESET}")
            print(f"{GRAY}  URL: {entry['url']}{RESET}")
            print(f"{GRAY}  Arquivos anteriores: {entry['prev_count']}{RESET}")
            print()

    def run_scan(self):
        """Executa scan completo dos arquivos TXT"""
        # Busca arquivos TXT e LNK
        txt_files = glob.glob("*.txt")
        lnk_files = glob.glob("*.lnk")
        
        targets = []
        
        # Adiciona TXTs diretos
        for txt in txt_files:
            targets.append(txt)
        
        # Resolve LNKs que apontam para TXTs
        for lnk in lnk_files:
            target = parse_lnk(lnk)
            if target and target.lower().endswith('.txt') and os.path.exists(target):
                targets.append(target)
        
        if not targets:
            print(f"{YELLOW}Nenhum arquivo .txt ou .lnk (apontando para .txt) encontrado.{RESET}")
            return
        
        # Remove duplicatas
        targets = list(set(targets))
        
        print(f"{CYAN}Arquivos encontrados: {len(targets)}{RESET}\n")
        
        all_results = []
        
        # Processa cada arquivo
        for target in targets:
            try:
                entries = self.parse_txt(target)
            except Exception as e:
                print(f"{RED}Erro ao ler {target}: {e}{RESET}")
                continue
                
            if not entries:
                print(f"{YELLOW}Aviso: Nenhum link válido encontrado em {os.path.basename(target)}{RESET}")
                continue

            # Cabeçalho para cada TXT
            txt_name = os.path.basename(target).upper()
            print(f"\n{CYAN}{BOLD}{'═' * 100}{RESET}")
            print(f"      {CYAN}{BOLD}{txt_name}{RESET}      ".center(100))
            print(f"{CYAN}{BOLD}{'═' * 100}{RESET}\n")

            header = f"{WHITE}{'NOME':<35} | {'STATUS':<15} | {'ARQUIVOS':<12} | {'ANTERIOR':<12} | {'ÚLTIMA CHECK'}{RESET}"
            print(header)
            print(f"{GRAY}{'─' * 105}{RESET}")

            # Processa cada link
            for name, url in entries:
                print(f"{GRAY}{name[:35]:<35} | Verificando...{RESET}", end='\r')

                status, count, p_status, p_count, p_date = self.process_link(name, url)

                # Define cor e símbolo
                if status == "ONLINE":
                    status_color = GREEN
                    symbol = "✓"
                elif status == "OFFLINE":
                    status_color = RED
                    symbol = "✗"
                elif status == "ERROR":
                    status_color = RED
                    symbol = "!"
                else:
                    status_color = YELLOW
                    symbol = "?"

                count_str = str(count)
                changed_mark = ""
                count_display = count_str
                
                # Verifica mudança na quantidade
                if (str(count).isdigit() and str(p_count).isdigit() and 
                    count != p_count and p_count != "N/A" and count != "Check Manual"):
                    count_display = f"{YELLOW}{count_str}{RESET}"
                    if count < p_count:
                        changed_mark = f" {YELLOW}↓ diminuiu{RESET}"
                    else:
                        changed_mark = f" {YELLOW}↑ aumentou{RESET}"

                # Exibe resultado
                print(f"{WHITE}{name[:35]:<35}{RESET} | "
                      f"{status_color}{symbol} {status:<12}{RESET} | "
                      f"{count_display:<12} | "
                      f"{str(p_count)[:12]:<12} | "
                      f"{GRAY}{p_date}{RESET}{changed_mark}")

                all_results.append({
                    "txt_name": txt_name,
                    "name": name,
                    "url": url,
                    "status": status,
                    "count": count,
                    "prev_count": p_count,
                    "prev_date": p_date
                })

        print(f"\n{GRAY}Histórico salvo em {WHITE}history.json{RESET}")
        print(f"{CYAN}{BOLD}{'═' * 100}{RESET}\n")

        # Salva snapshot do scan
        scans = self.load_scans_history()
        now = datetime.now()
        scan = {
            "timestamp": now.isoformat(),
            "date_str": now.strftime("%d-%m-%Y %H:%M"),
            "entries": all_results
        }
        scans.append(scan)
        self.save_scans_history(scans)
        print(f"{GRAY}Scan salvo no histórico (total: {len(scans)}){RESET}")

        self.save_history()

        # Pergunta se quer ver links offline
        if all_results:
            print()
            resposta = input(f"{CYAN}Deseja ver todos os links offline? (s/n): {RESET}").strip().lower()
            if resposta in ['s', 'sim', 'y', 'yes']:
                self.show_offline_links(all_results)

    def show_history_menu(self):
        """Exibe menu de histórico de scans"""
        scans = self.load_scans_history()
        if not scans:
            print(f"{YELLOW}Nenhum scan salvo ainda.{RESET}")
            return

        print("\nScans disponíveis (mais recentes primeiro):")
        for i, scan in enumerate(reversed(scans), 1):
            print(f" {i:2d} - {scan['date_str']}   ({len(scan['entries'])} links)")

        try:
            num = int(input("\nDigite o número do scan para ver (0 para cancelar): "))
            if num == 0:
                return
            selected = scans[-num]
        except:
            print(f"{RED}Entrada inválida.{RESET}")
            return

        print(f"\n\n{CYAN}{BOLD}SCAN DE {selected['date_str'].upper()}{RESET}\n")

        current_txt = None
        for entry in selected['entries']:
            if entry['txt_name'] != current_txt:
                current_txt = entry['txt_name']
                
                # Cabeçalho para cada TXT
                print(f"\n{CYAN}{BOLD}{'═' * 100}{RESET}")
                print(f"      {CYAN}{BOLD}{current_txt}{RESET}      ".center(100))
                print(f"{CYAN}{BOLD}{'═' * 100}{RESET}\n")
                
                header = f"{WHITE}{'NOME':<35} | {'STATUS':<15} | {'ARQUIVOS':<12} | {'ANTERIOR':<12} | {'ÚLTIMA CHECK'}{RESET}"
                print(header)
                print(f"{GRAY}{'─' * 105}{RESET}")

            status = entry['status']
            count = entry['count']
            p_count = entry['prev_count']
            p_date = entry['prev_date']

            # Define cor e símbolo
            if status == "ONLINE":
                status_color = GREEN
                symbol = "✓"
            elif status == "OFFLINE":
                status_color = RED
                symbol = "✗"
            elif status == "ERROR":
                status_color = RED
                symbol = "!"
            else:
                status_color = YELLOW
                symbol = "?"

            count_str = str(count)
            changed_mark = ""
            count_display = count_str
            
            # Verifica mudança
            if (str(count).isdigit() and str(p_count).isdigit() and 
                count != p_count and p_count != "N/A" and count != "Check Manual"):
                count_display = f"{YELLOW}{count_str}{RESET}"
                if count < p_count:
                    changed_mark = f" {YELLOW}↓ diminuiu{RESET}"
                else:
                    changed_mark = f" {YELLOW}↑ aumentou{RESET}"

            print(f"{WHITE}{entry['name'][:35]:<35}{RESET} | "
                  f"{status_color}{symbol} {status:<12}{RESET} | "
                  f"{count_display:<12} | "
                  f"{str(p_count)[:12]:<12} | "
                  f"{GRAY}{p_date}{RESET}{changed_mark}")

        # Pergunta se quer ver links offline
        print()
        resposta = input(f"{CYAN}Deseja ver os links offline deste scan? (s/n): {RESET}").strip().lower()
        if resposta in ['s', 'sim', 'y', 'yes']:
            self.show_offline_links(selected['entries'])


def main():
    """Função principal"""
    checker = LinkChecker()

    while True:
        print("\n" + "═" * 50)
        print("           VERIFICADOR DE LINKS")
        print("═" * 50)
        print(" 1. Realizar novo scan")
        print(" 2. Ver scans anteriores (últimos 10)")
        print(" 3. Sair")
        print("═" * 50)

        escolha = input("Escolha uma opção: ").strip()

        if escolha == "1":
            print("\nIniciando verificação...\n")
            checker.run_scan()
        elif escolha == "2":
            checker.show_history_menu()
        elif escolha == "3":
            print("\nAté a próxima!\n")
            break
        else:
            print(f"{YELLOW}Opção inválida. Tente novamente.{RESET}")


if __name__ == "__main__":
    main()