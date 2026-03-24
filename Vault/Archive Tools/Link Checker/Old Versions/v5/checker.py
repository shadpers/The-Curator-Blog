import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime
import random
import struct
import glob

# Tenta importar cloudscraper para bypass de proteções
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

def parse_lnk(filepath):
    """Função para extrair o caminho alvo de um atalho .lnk sem dependências extras."""
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
                    local_base_path = content[local_base_path_pos:].split(b'\x00\x00', 1)[0].decode('utf-16le', errors='ignore')
                else:
                    local_base_path_pos = pos + local_base_path_offset
                    local_base_path = content[local_base_path_pos:].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')

                # Common path suffix
                if common_path_suffix_unicode_offset is not None and common_path_suffix_unicode_offset > 0:
                    common_path_suffix_pos = pos + common_path_suffix_unicode_offset
                    common_path_suffix = content[common_path_suffix_pos:].split(b'\x00\x00', 1)[0].decode('utf-16le', errors='ignore')
                else:
                    common_path_suffix_pos = pos + common_path_suffix_offset
                    common_path_suffix = content[common_path_suffix_pos:].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')

                target = local_base_path + common_path_suffix
                return target
    except Exception as e:
        print(f"Erro ao parsear {filepath}: {e}")
        return None

    return None

class LinkChecker:
    def __init__(self, db_path='history.json'):
        self.db_path = db_path
        self.history = self.load_history()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        if CLOUDSCRAPER_AVAILABLE:
            self.scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        else:
            self.scraper = None

    def load_history(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_history(self):
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)

    def check_terabox(self, url):
        try:
            url = url.replace("1024terabox.com", "www.terabox.com")
            if self.scraper:
                response = self.scraper.get(url, headers=self.headers, timeout=15)
            else:
                response = requests.get(url, headers=self.headers, timeout=15)
            
            if "The shared file has expired" in response.text or "share-error-left" in response.text or "0 file(s)" in response.text or "expired" in response.url:
                return "OFFLINE", 0
            
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else ""
            
            match = re.search(r'(\d+)\s*file', title, re.IGNORECASE)
            if match:
                return "ONLINE", int(match.group(1))
            
            if "Log in" in response.text and "TeraBox" in response.text:
                return "ONLINE", "Check Manual"
                
            return "ONLINE", 1
        except:
            return "ERROR", 0

    def check_pixeldrain(self, url):
        try:
            file_id = url.split('/')[-1]
            is_album = '/l/' in url
            is_file = '/u/' in url
            
            if is_album:
                api_url = f"https://pixeldrain.com/api/list/{file_id}"
                response = requests.get(api_url, headers=self.headers, timeout=15)
                
                if response.status_code == 404:
                    return "OFFLINE", 0
                
                data = response.json()
                
                if 'success' in data and not data['success']:
                    return "OFFLINE", 0
                
                count = data.get('file_count', len(data.get('files', [])))
                return "ONLINE", count
                
            elif is_file:
                api_url = f"https://pixeldrain.com/api/file/{file_id}/info"
                response = requests.get(api_url, headers=self.headers, timeout=15)
                
                if response.status_code == 404:
                    return "OFFLINE", 0
                
                data = response.json()
                
                if 'success' in data and not data['success']:
                    return "OFFLINE", 0
                
                return "ONLINE", 1
            
            return "UNKNOWN", 0
        except Exception as e:
            return "ERROR", 0

    def check_archive(self, url):
        try:
            if ".archive.org/" in url and "/items/" in url:
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
            
            if "/download/" in url and not url.endswith('/'):
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
                else:
                    try:
                        response = requests.get(url, headers=self.headers, timeout=10, stream=True)
                        response.raise_for_status()
                        return "ONLINE", 1
                    except:
                        return "OFFLINE", 0
            
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            if response.status_code == 404:
                return "OFFLINE", 0
            
            text_lower = response.text.lower()
            
            if "item cannot be found" in text_lower or "not available" in text_lower:
                return "OFFLINE", 0
            
            if "/details/" in url:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                files_link = soup.find('a', string=re.compile(r'download.*\d+.*files?', re.IGNORECASE))
                if files_link:
                    match = re.search(r'(\d+)', files_link.text)
                    if match:
                        return "ONLINE", int(match.group(1))
                
                match = re.search(r'(\d+)\s*(?:file|item)s?', response.text, re.IGNORECASE)
                if match:
                    count = int(match.group(1))
                    if count > 0:
                        return "ONLINE", count
                
                return "ONLINE", 1
            
            if response.status_code == 200:
                return "ONLINE", 1
            
            return "UNKNOWN", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "OFFLINE", 0
            return "ERROR", 0
        except Exception as e:
            return "ERROR", 0

    def check_mediafire_folder(self, folder_key):
        r = random.random()
        api_url = f"https://www.mediafire.com/api/1.5/folder/get_info.php?r={r}&folder_key={folder_key}&response_format=json"
        
        try:
            response = requests.get(api_url, headers=self.headers, timeout=12)
            if response.status_code != 200:
                return "OFFLINE", 0
                
            data = response.json()
            
            if data.get('response', {}).get('result') != 'Success':
                return "OFFLINE", 0
                
            folder_info = data['response']['folder_info']
            
            file_count = int(folder_info.get('file_count', 0))
            folder_count = int(folder_info.get('folder_count', 0))
            
            total_items = file_count + folder_count
            
            if total_items == 0:
                return "ONLINE", 0
            else:
                return "ONLINE", total_items
                
        except:
            return "ERROR", 0

    def check_mediafire(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            text = response.text
            text_lower = text.lower()
            
            offline_indicators = [
                "the file you attempted to download has been removed",
                "file removed",
                "invalid or deleted file",
                "folder not found",
                "the key you provided for file download was invalid",
                "oops!",
                "unavailable",
            ]
            
            if response.status_code == 404:
                return "OFFLINE", 0
            
            for indicator in offline_indicators:
                if indicator in text_lower:
                    return "OFFLINE", 0
            
            if "/folder/" in url:
                match = re.search(r'/folder/([a-zA-Z0-9]+)', url)
                if match:
                    folder_key = match.group(1)
                    return self.check_mediafire_folder(folder_key)
                
                if "folder not found" in text_lower or "invalid" in text_lower:
                    return "OFFLINE", 0
                
                if "this folder is currently empty" in text_lower or "0 items" in text_lower:
                    return "ONLINE", 0
                
                patterns = [
                    r'(\d+)\s+files?(?:\s+and\s+\d+\s+folders?)?',
                    r'(\d+)\s+items?',
                    r'Showing\s+\d+\s+to\s+\d+\s+of\s+(\d+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        count = int(match.group(1))
                        if count > 0:
                            return "ONLINE", count
                        elif count == 0:
                            return "ONLINE", 0
                
                if 'data-perm' in text or 'file-type' in text or 'folder-type' in text:
                    return "ONLINE", "Manual"
                
                return "ONLINE", 0
            
            if "/file/" in url:
                if response.status_code == 200 and "download" in text_lower:
                    return "ONLINE", 1
                else:
                    return "OFFLINE", 0
            
            return "ONLINE", 1
            
        except Exception as e:
            return "ERROR", 0

    def check_fileupload(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            offline_indicators = [
                "File Not Found",
                "File has been deleted",
                "404",
                "not found"
            ]
            
            if response.status_code == 404 or any(ind in response.text for ind in offline_indicators):
                return "OFFLINE", 0
            
            if response.status_code == 200:
                return "ONLINE", 1
            
            return "UNKNOWN", 0
        except Exception as e:
            return "ERROR", 0

    def process_link(self, name, url):
        status = "UNKNOWN"
        count = 0
        
        previous_data = self.history.get(url, {})
        prev_status = previous_data.get("status", "N/A")
        prev_count = previous_data.get("count", "N/A")
        prev_date = previous_data.get("last_check", "Nunca")

        try:
            if "terabox" in url.lower():
                status, count = self.check_terabox(url)
            elif "pixeldrain" in url.lower():
                status, count = self.check_pixeldrain(url)
            elif "archive.org" in url.lower():
                status, count = self.check_archive(url)
            elif "mediafire" in url.lower():
                status, count = self.check_mediafire(url)
            elif "file-upload" in url.lower():
                status, count = self.check_fileupload(url)
            else:
                status = "UNSUPPORTED"
                count = 0
        except Exception as e:
            status = "ERROR"
            count = 0
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.history[url] = {
            "name": name,
            "status": status,
            "count": count,
            "last_check": current_time,
            "prev_status": prev_status,
            "prev_count": prev_count,
            "prev_date": prev_date
        }
        
        return status, count, prev_status, prev_count, prev_date

    def parse_txt(self, file_path):
        """Parseia o TXT ignorando emails e linhas vazias, coletando nome e links (incluindo multi-partes)."""
        entries = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
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
        return entries

    def run(self):
        if not CLOUDSCRAPER_AVAILABLE:
            print("\033[93m" + "AVISO: cloudscraper não instalado. Alguns sites (TeraBox) podem falhar." + "\033[0m")
            print("\033[93m" + "Instale com: pip install cloudscraper\n" + "\033[0m")

        # Cores ANSI
        RESET   = "\033[0m"
        CYAN    = "\033[96m"
        GREEN   = "\033[92m"
        YELLOW  = "\033[93m"
        RED     = "\033[91m"
        WHITE   = "\033[97m"
        GRAY    = "\033[90m"
        BOLD    = "\033[1m"

        # Encontra todos os .lnk na pasta atual
        lnk_files = glob.glob('*.lnk')
        if not lnk_files:
            print(f"{RED}Nenhum atalho .lnk encontrado na pasta.{RESET}")
            return

        for lnk in sorted(lnk_files):
            target = parse_lnk(lnk)
            if not target or not os.path.exists(target):
                print(f"{RED}Erro: Não foi possível resolver ou acessar o TXT de {lnk}{RESET}")
                continue

            entries = self.parse_txt(target)
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

            for name, url in entries:
                print(f"{GRAY}{name[:35]:<35} | Verificando...{RESET}", end='\r')

                status, count, p_status, p_count, p_date = self.process_link(name, url)

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
                if (str(count).isdigit() and str(p_count).isdigit() and 
                    count != p_count and p_count != "N/A" and count != "Check Manual"):
                    count_display = f"{YELLOW}{count_str}{RESET}"
                    changed_mark = f" {YELLOW}← mudou{RESET}"

                print(f"{WHITE}{name[:35]:<35}{RESET} | "
                      f"{status_color}{symbol} {status:<12}{RESET} | "
                      f"{count_display:<12} | "
                      f"{str(p_count)[:12]:<12} | "
                      f"{GRAY}{p_date}{RESET}{changed_mark}")

        print(f"\n{GRAY}Histórico salvo em {WHITE}history.json{RESET}")
        print(f"{CYAN}{BOLD}{'═' * 100}{RESET}\n")

        self.save_history()

if __name__ == "__main__":
    checker = LinkChecker()
    checker.run()