"""
Módulo Checker para Google Drive
Suporta verificação de arquivos e pastas do Google Drive
"""

import requests
import re
from module_base import BaseChecker


class GoogleDriveChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Google Drive"
    
    @property
    def domains(self) -> list:
        return ["drive.google.com", "docs.google.com"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do Google Drive"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Verifica indicadores de offline
            if "File not found" in response.text or \
               "Arquivo não encontrado" in response.text or \
               "No preview available" in response.text or \
               response.status_code == 404:
                return "OFFLINE", 0
            
            # Verifica se precisa de permissão
            if "Request access" in response.text or \
               "Solicitar acesso" in response.text:
                return "OFFLINE", 0
            
            # Verifica se é pasta
            if "/folders/" in url or "folder" in url.lower():
                # Tenta contar arquivos (simplificado)
                return "ONLINE", "Check Manual"
            
            # É arquivo individual
            return "ONLINE", 1
            
        except Exception as e:
            return "ERROR", 0


# Instância global para ser importada
checker = GoogleDriveChecker()
