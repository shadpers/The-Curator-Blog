import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

class LinkChecker:
    def __init__(self, db_path='history.json'):
        self.db_path = db_path
        self.history = self.load_history()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

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
            # Normaliza URL para o domínio correto
            original_url = url
            url = url.replace("1024terabox.com", "www.terabox.com")
            
            # Headers completos
            terabox_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=terabox_headers, timeout=15, allow_redirects=True)
            text = response.text
            text_lower = text.lower()
            
            # Detecta OFFLINE
            offline_indicators = [
                "the shared file has expired",
                "share-error-left",
                "file has been deleted",
                "share link does not exist",
                "link has expired",
                "share expired",
                "error-wrap",
                "share-error"
            ]
            
            for indicator in offline_indicators:
                if indicator in text_lower:
                    return "OFFLINE", 0
            
            if "error" in response.url.lower() or "expired" in response.url.lower():
                return "OFFLINE", 0
            
            # Busca por dados no JavaScript/JSON embutido
            # TeraBox coloca dados em window.__INIT_DATA__ ou locals
            patterns = [
                r'window\.__INIT_DATA__\s*=\s*({.*?});',
                r'locals\.mset\((.*?)\);',
                r'"list"\s*:\s*\[(.*?)\]',
            ]
            
            file_count = None
            
            # Tenta extrair JSON de dados
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        json_str = match.group(1)
                        # Conta ocorrências de server_filename (cada arquivo tem um)
                        count = json_str.count('"server_filename"')
                        if count > 0:
                            file_count = count
                            break
                    except:
                        pass
            
            if file_count is not None:
                return "ONLINE", file_count
            
            # Busca contagem numérica explícita
            count_patterns = [
                r'"fileCount"\s*:\s*(\d+)',
                r'"file_count"\s*:\s*(\d+)',
                r'fileCount:\s*(\d+)',
                r'(\d+)\s+files?["\s,}]',
            ]
            
            for pattern in count_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return "ONLINE", int(match.group(1))
            
            # Detecta pasta vazia explicitamente
            if any(x in text_lower for x in ["empty folder", "0 files", "no files"]):
                return "ONLINE", 0
            
            # Se tem indicadores de sucesso mas não conseguiu contar
            if response.status_code == 200 and "terabox" in text_lower:
                return "ONLINE", "Manual"
                
            return "ERROR", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", "Timeout"
        except Exception as e:
            return "ERROR", 0

    def check_pixeldrain(self, url):
        try:
            file_id = url.split('/')[-1]
            is_album = '/l/' in url
            is_file = '/u/' in url
            
            if is_album:
                # Lista/Álbum
                api_url = f"https://pixeldrain.com/api/list/{file_id}"
                response = requests.get(api_url, headers=self.headers, timeout=15)
                
                if response.status_code == 404:
                    return "OFFLINE", 0
                
                data = response.json()
                
                # Verifica se existe campo de erro
                if 'success' in data and not data['success']:
                    return "OFFLINE", 0
                
                count = data.get('file_count', len(data.get('files', [])))
                return "ONLINE", count
                
            elif is_file:
                # Arquivo único
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
            # Links diretos de download de arquivos únicos
            if "/download/" in url and not url.endswith('/'):
                # É um arquivo específico para download direto
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
                else:
                    # Tenta GET se HEAD falhar
                    response = requests.get(url, headers=self.headers, timeout=10, stream=True)
                    if response.status_code == 200:
                        return "ONLINE", 1
                    return "OFFLINE", 0
            
            # Para páginas de detalhes ou outros
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Verifica offline
            if response.status_code == 404:
                return "OFFLINE", 0
            
            text_lower = response.text.lower()
            if "item cannot be found" in text_lower or "not found" in text_lower:
                return "OFFLINE", 0
            
            # Se é página de detalhes
            if "/details/" in url:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Procura link de download com contagem
                files_link = soup.find('a', string=re.compile(r'download.*\d+.*files?', re.IGNORECASE))
                if files_link:
                    match = re.search(r'(\d+)', files_link.text)
                    if match:
                        return "ONLINE", int(match.group(1))
                
                # Busca padrões no texto
                match = re.search(r'(\d+)\s*(?:file|item)s?', response.text, re.IGNORECASE)
                if match:
                    count = int(match.group(1))
                    if count > 0:
                        return "ONLINE", count
                
                return "ONLINE", 1
            
            # Se chegou aqui e status 200
            if response.status_code == 200:
                return "ONLINE", 1
            
            return "UNKNOWN", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", "Timeout"
        except Exception as e:
            return "ERROR", 0

    def check_mediafire(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Verifica se está offline
            offline_indicators = [
                "The file you attempted to download has been removed",
                "File Removed",
                "Invalid or Deleted File",
                "Folder Not Found"
            ]
            
            if response.status_code == 404 or any(ind in response.text for ind in offline_indicators):
                return "OFFLINE", 0
            
            # Se é pasta
            if "/folder/" in url:
                if "This folder is currently empty" in response.text or "0 items" in response.text:
                    return "ONLINE", 0
                
                # Tenta extrair contagem
                soup = BeautifulSoup(response.text, 'html.parser')
                match = re.search(r'(\d+)\s*(?:file|item)s?', response.text, re.IGNORECASE)
                if match:
                    return "ONLINE", int(match.group(1))
                
                return "ONLINE", "Manual"
            
            # Arquivo único
            if "/file/" in url and response.status_code == 200:
                return "ONLINE", 1
            
            return "ONLINE", 1
        except Exception as e:
            return "ERROR", 0

    def check_fileupload(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Verifica sinais de offline
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
        
        # Recupera dados anteriores
        previous_data = self.history.get(url, {})
        prev_status = previous_data.get("status", "N/A")
        prev_count = previous_data.get("count", "N/A")
        prev_date = previous_data.get("last_check", "Nunca")

        try:
            # Determina qual checker usar baseado na URL
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
        
        # Atualiza histórico
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

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"{'NOME':<30} | {'STATUS':<10} | {'ARQUIVOS':<12} | {'ANTERIOR':<12} | {'ÚLTIMA CHECK'}")
        print("-" * 95)

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or ">" not in line:
                continue
            
            parts = line.split('>', 1)
            if len(parts) != 2:
                continue
                
            name, url = parts[0].strip(), parts[1].strip()
            
            # Mostra progresso
            print(f"{name[:30]:<30} | Verificando...", end='\r')
            
            status, count, p_status, p_count, p_date = self.process_link(name, url)
            
            # Formata mudança
            diff = ""
            if p_count != "N/A":
                if str(count) != str(p_count):
                    diff = f" ({p_status}: {p_count})"
            
            count_str = str(count) if count not in ["Manual", "Timeout", "Conexão"] else count
            
            print(f"{name[:30]:<30} | {status:<10} | {count_str:<12} | {str(p_count)[:12]:<12} | {p_date}")

        self.save_history()
        print("\nHistórico salvo em history.json")

if __name__ == "__main__":
    checker = LinkChecker()
    checker.run('links.txt')