"""
Módulo Checker para MediaFire
Suporta verificação de arquivos e pastas do MediaFire
"""

import requests
from bs4 import BeautifulSoup
import re
from module_base import BaseChecker


class MediaFireChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "MediaFire"
    
    @property
    def domains(self) -> list:
        return ["mediafire.com"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do MediaFire"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            
            # Verifica indicadores de offline
            if "File Not Found" in response.text or \
               "Invalid or Deleted File" in response.text or \
               "unavailable" in response.text.lower():
                return "OFFLINE", 0
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Verifica se é pasta
            if "/folder/" in url:
                # Tenta encontrar contador de arquivos
                file_count_elem = soup.find('span', class_='folderInfo')
                if file_count_elem:
                    match = re.search(r'(\d+)\s*file', file_count_elem.text, re.IGNORECASE)
                    if match:
                        return "ONLINE", int(match.group(1))
                return "ONLINE", 1
            
            # É arquivo individual
            else:
                # Verifica se tem botão de download
                download_button = soup.find('a', {'id': 'downloadButton'})
                if download_button:
                    return "ONLINE", 1
                
                # Fallback: verifica título
                title = soup.title.string if soup.title else ""
                if "MediaFire" in title and "Not Found" not in title:
                    return "ONLINE", 1
            
            return "UNKNOWN", 0
            
        except Exception as e:
            return "ERROR", 0


# Instância global para ser importada
checker = MediaFireChecker()
