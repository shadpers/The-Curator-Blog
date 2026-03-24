"""
Módulo Checker para File-Upload
Suporta verificação de links do File-Upload.com
"""

import requests
from module_base import BaseChecker


class FileUploadChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "File-Upload"
    
    @property
    def domains(self) -> list:
        return ["file-upload.org", "file-upload.net"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do File-Upload"""
        try:
            # Primeiro tenta HEAD request
            head_response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
            
            # Se retornou 200, muito provável que está online
            if head_response.status_code == 200:
                return "ONLINE", 1
            
            # Se não foi 200, faz GET completo para verificar
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            offline_indicators = [
                "File Not Found",
                "File has been deleted",
                "404",
                "not found",
                "doesn't exist",
                "removed"
            ]
            
            # 404 definitivo
            if response.status_code == 404:
                return "OFFLINE", 0
            
            # Verifica conteúdo apenas se não for 200
            if response.status_code != 200:
                text_lower = response.text.lower()
                if any(ind.lower() in text_lower for ind in offline_indicators):
                    return "OFFLINE", 0
            
            # Se chegou aqui e status é 200, está online
            if response.status_code == 200:
                return "ONLINE", 1
            
            return "UNKNOWN", 0
            
        except Exception as e:
            return "ERROR", 0


# Instância global para ser importada
checker = FileUploadChecker()
