"""
Módulo Checker para TeraBox
Suporta verificação de links do TeraBox e 1024terabox
"""

import requests
from bs4 import BeautifulSoup
import re
from module_base import BaseChecker

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False


class TeraBoxChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "TeraBox"
    
    @property
    def domains(self) -> list:
        return ["terabox.com", "1024terabox.com"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        if CLOUDSCRAPER_AVAILABLE:
            self.scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        else:
            self.scraper = None
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do TeraBox"""
        try:
            # Normaliza URL
            url = url.replace("1024terabox.com", "www.terabox.com")
            
            # Faz requisição
            if self.scraper:
                response = self.scraper.get(url, headers=self.headers, timeout=15)
            else:
                response = requests.get(url, headers=self.headers, timeout=15)
            
            # Verifica indicadores de offline
            if "The shared file has expired" in response.text or \
               "share-error-left" in response.text or \
               "0 file(s)" in response.text or \
               "expired" in response.url:
                return "OFFLINE", 0
            
            # Tenta extrair número de arquivos do título
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else ""
            
            match = re.search(r'(\d+)\s*file', title, re.IGNORECASE)
            if match:
                return "ONLINE", int(match.group(1))
            
            # Verifica se precisa de login manual
            if "Log in" in response.text and "TeraBox" in response.text:
                return "ONLINE", "Check Manual"
            
            return "ONLINE", 1
            
        except Exception as e:
            return "ERROR", 0


# Instância global para ser importada
checker = TeraBoxChecker()
