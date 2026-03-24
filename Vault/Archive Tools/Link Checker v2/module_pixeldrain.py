"""
Módulo Checker para Pixeldrain
Suporta verificação de arquivos e álbuns do Pixeldrain
"""

import requests
import json
from module_base import BaseChecker


class PixeldrainChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Pixeldrain"
    
    @property
    def domains(self) -> list:
        return ["pixeldrain.com"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do Pixeldrain"""
        try:
            file_id = url.split('/')[-1]
            is_album = '/l/' in url
            is_file = '/u/' in url
            
            # Verifica álbum
            if is_album:
                return self._check_album(file_id)
            
            # Verifica arquivo
            elif is_file:
                return self._check_file(file_id, url)
            
            return "UNKNOWN", 0
            
        except Exception as e:
            return "ERROR", 0
    
    def _check_album(self, file_id: str) -> tuple:
        """Verifica álbum do Pixeldrain"""
        try:
            api_url = f"https://pixeldrain.com/api/list/{file_id}"
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            if response.status_code == 404:
                return "OFFLINE", 0
            
            data = response.json()
            
            if 'success' in data and not data['success']:
                return "OFFLINE", 0
            
            count = data.get('file_count', len(data.get('files', [])))
            return "ONLINE", count
            
        except Exception:
            return "ERROR", 0
    
    def _check_file(self, file_id: str, url: str) -> tuple:
        """Verifica arquivo do Pixeldrain"""
        try:
            api_url = f"https://pixeldrain.com/api/file/{file_id}/info"
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            if response.status_code == 404:
                return "OFFLINE", 0
            
            # Tenta parsear resposta JSON
            try:
                data = response.json()
                
                # Verifica campo success
                if 'success' in data and not data['success']:
                    return "OFFLINE", 0
                
                # Se tem ID, arquivo existe
                if 'id' in data:
                    return "ONLINE", 1
                
                # Fallback: status 200
                return "ONLINE", 1
                
            except json.JSONDecodeError:
                # Se não conseguiu parsear mas retornou 200, tenta HEAD
                head_response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if head_response.status_code == 200:
                    return "ONLINE", 1
                return "OFFLINE", 0
                
        except Exception:
            return "ERROR", 0


# Instância global para ser importada
checker = PixeldrainChecker()
