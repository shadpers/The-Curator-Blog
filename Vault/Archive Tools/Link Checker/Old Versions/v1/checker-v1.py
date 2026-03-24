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
            # Pixeldrain API endpoint for lists is /list/{id}
            api_url = f"https://pixeldrain.com/api/{'list' if is_album else 'file'}/{file_id}"
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                return "OFFLINE", 0
            
            data = response.json()
            if is_album:
                # In Pixeldrain API, lists have a 'file_count' field or we can count 'files'
                count = data.get('file_count', len(data.get('files', [])))
                return "ONLINE", count
            else:
                return "ONLINE", 1
        except:
            return "ERROR", 0

    def check_archive(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code == 404 or "Items cannot be found" in response.text:
                return "OFFLINE", 0
            
            if "/details/" in url:
                # É uma página de detalhes, procurar por contagem de arquivos
                soup = BeautifulSoup(response.text, 'html.parser')
                files_link = soup.find('a', string=re.compile(r'download \d+ Files'))
                if files_link:
                    count = int(re.search(r'(\d+)', files_link.text).group(1))
                    return "ONLINE", count
                return "ONLINE", 1
            return "ONLINE", 1
        except:
            return "ERROR", 0

    def check_mediafire(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if "The file you attempted to download has been removed" in response.text or response.status_code == 404:
                return "OFFLINE", 0
            
            if "/folder/" in url:
                # Mediafire folders são complexos via requests simples, mas podemos tentar achar padrões
                if "This folder is currently empty" in response.text:
                    return "ONLINE", 0
                # Tenta achar contagem no texto
                match = re.search(r'(\d+)\s*items', response.text, re.IGNORECASE)
                count = int(match.group(1)) if match else "Check Manual"
                return "ONLINE", count
            return "ONLINE", 1
        except:
            return "ERROR", 0

    def check_fileupload(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if "File Not Found" in response.text or response.status_code == 404:
                return "OFFLINE", 0
            return "ONLINE", 1
        except:
            return "ERROR", 0

    def process_link(self, name, url):
        status = "UNKNOWN"
        count = 0
        
        # Recupera dados anteriores para comparação
        previous_data = self.history.get(url, {})
        prev_status = previous_data.get("status", "N/A")
        prev_count = previous_data.get("count", "N/A")
        prev_date = previous_data.get("last_check", "Nunca")

        if "terabox" in url:
            status, count = self.check_terabox(url)
        elif "pixeldrain" in url:
            status, count = self.check_pixeldrain(url)
        elif "archive.org" in url:
            status, count = self.check_archive(url)
        elif "mediafire" in url:
            status, count = self.check_mediafire(url)
        elif "file-upload" in url:
            status, count = self.check_fileupload(url)
        
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

        print(f"{'NOME':<30} | {'STATUS':<10} | {'ARQUIVOS':<10} | {'ULTIMA CHECAGEM'}")
        print("-" * 80)

        for line in lines:
            line = line.strip()
            if not line or ">" not in line:
                continue
            
            name, url = line.split('>', 1)
            status, count, p_status, p_count, p_date = self.process_link(name.strip(), url.strip())
            
            diff = ""
            if p_count != "N/A" and str(count) != str(p_count):
                diff = f" (Era: {p_count})"
            
            print(f"{name[:30]:<30} | {status:<10} | {str(count) + diff:<15} | {p_date}")

        self.save_history()

if __name__ == "__main__":
    checker = LinkChecker()
    checker.run('links.txt')
