import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

# Tenta importar cloudscraper para bypass de proteções
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

class LinkChecker:
    def __init__(self, db_path='history.json'):
        self.db_path = db_path
        self.history = self.load_history()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Cria scraper se disponível
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
            # TeraBox often requires a redirect or specific domain
            url = url.replace("1024terabox.com", "www.terabox.com")
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if "The shared file has expired" in response.text or "share-error-left" in response.text or "0 file(s)" in response.text or "expired" in response.url:
                return "OFFLINE", 0
            
            # TeraBox renders content via JS, but sometimes the count is in the title or initial state
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else ""
            
            match = re.search(r'(\d+)\s*file', title, re.IGNORECASE)
            if match:
                return "ONLINE", int(match.group(1))
            
            if "Log in" in response.text and "TeraBox" in response.text:
                return "ONLINE", "Check Manual" # Link is up but count is hidden
                
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
            # Links diretos de download de arquivos hospedados
            if ".archive.org/" in url and "/items/" in url:
                # Arquivo direto hospedado (ex: dn720807.ca.archive.org)
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
            
            # Links /download/ com arquivo específico
            if "/download/" in url and not url.endswith('/'):
                # Verifica se o arquivo existe
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
                else:
                    # Se HEAD falhar, tenta GET
                    try:
                        response = requests.get(url, headers=self.headers, timeout=10, stream=True)
                        response.raise_for_status()
                        return "ONLINE", 1
                    except:
                        return "OFFLINE", 0
            
            # Páginas de detalhes ou download de pastas
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            if response.status_code == 404:
                return "OFFLINE", 0
            
            text_lower = response.text.lower()
            
            # Verifica se não encontrado
            if "item cannot be found" in text_lower or "not available" in text_lower:
                return "OFFLINE", 0
            
            # Se é página de detalhes
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
            
            # Se chegou aqui com status 200
            if response.status_code == 200:
                return "ONLINE", 1
            
            return "UNKNOWN", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", "Timeout"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "OFFLINE", 0
            return "ERROR", 0
        except Exception as e:
            return "ERROR", 0

    def check_mediafire(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            text = response.text
            text_lower = text.lower()
            
            # Indicadores de OFFLINE (arquivo ou pasta)
            offline_indicators = [
                "the file you attempted to download has been removed",
                "file removed",
                "invalid or deleted file",
                "folder not found",
                "the key you provided for file download was invalid",
                "oops!",
                "unavailable",
            ]
            
            # Verifica se está offline
            if response.status_code == 404:
                return "OFFLINE", 0
            
            for indicator in offline_indicators:
                if indicator in text_lower:
                    return "OFFLINE", 0
            
            # Se é pasta/folder
            if "/folder/" in url:
                # Verifica se pasta não existe ou está vazia
                if "folder not found" in text_lower or "invalid" in text_lower:
                    return "OFFLINE", 0
                
                # Pasta vazia
                if "this folder is currently empty" in text_lower or "0 items" in text_lower:
                    return "ONLINE", 0
                
                # Tenta extrair contagem de arquivos/pastas
                # MediaFire mostra "X files" ou "X items" no HTML
                patterns = [
                    r'(\d+)\s+files?(?:\s+and\s+\d+\s+folders?)?',  # "2 files and 1 folder"
                    r'(\d+)\s+items?',  # "2 items"
                    r'Showing\s+\d+\s+to\s+\d+\s+of\s+(\d+)',  # "Showing 1 to 2 of 2"
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        count = int(match.group(1))
                        if count > 0:
                            return "ONLINE", count
                        elif count == 0:
                            return "ONLINE", 0
                
                # Se não encontrou contagem mas página carregou com conteúdo
                # Verifica se tem elementos de arquivo na página
                if 'data-perm' in text or 'file-type' in text or 'folder-type' in text:
                    # Tem arquivos mas não conseguiu contar
                    return "ONLINE", "Manual"
                
                # Se nada funcionou, assume que pode estar vazia ou offline
                return "ONLINE", 0
            
            # Se é arquivo único
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

    def run(self, input_file):
        if not os.path.exists(input_file):
            print(f"Erro: Arquivo {input_file} não encontrado.")
            return
        
        # Verifica cloudscraper
        if not CLOUDSCRAPER_AVAILABLE:
            print("AVISO: cloudscraper não instalado. TeraBox pode retornar 'Bot Blocked'.")
            print("Instale com: pip install cloudscraper")
            print()

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"{'NOME':<30} | {'STATUS':<12} | {'ARQUIVOS':<12} | {'ANTERIOR':<12} | {'ÚLTIMA CHECK'}")
        print("-" * 100)

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or ">" not in line:
                continue
            
            parts = line.split('>', 1)
            if len(parts) != 2:
                continue
                
            name, url = parts[0].strip(), parts[1].strip()
            
            print(f"{name[:30]:<30} | Verificando...", end='\r')
            
            status, count, p_status, p_count, p_date = self.process_link(name, url)
            
            count_str = str(count)
            
            print(f"{name[:30]:<30} | {status:<12} | {count_str:<12} | {str(p_count)[:12]:<12} | {p_date}")

        self.save_history()
        print("\nHistórico salvo em history.json")

if __name__ == "__main__":
    checker = LinkChecker()
    checker.run('links.txt')