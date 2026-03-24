"""
Módulo Checker para 1fichier
Verifica status de links do 1fichier.com
"""

import requests
from module_base import BaseChecker


class OneFichierChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "1fichier"
    
    @property
    def domains(self) -> list:
        return ["1fichier.com"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do 1fichier"""
        try:
            # Adiciona https:// se não tiver protocolo
            if not url.startswith('http'):
                url = 'https://' + url
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=15,
                allow_redirects=True
            )
            
            # 1fichier retorna HTTP 404 para arquivos removidos/não encontrados
            if response.status_code == 404:
                return "OFFLINE", 0
            
            # HTTP 200 normalmente indica arquivo online
            if response.status_code == 200:
                html_lower = response.text.lower()
                
                # Indicadores de arquivo removido/offline
                offline_indicators = [
                    "file not found",
                    "fichier introuvable",
                    "deleted",
                    "supprimé",
                    "supprime",
                    "removed",
                    "the file you are looking for does not exist",
                ]
                
                if any(indicator in html_lower for indicator in offline_indicators):
                    return "OFFLINE", 0
                
                # Indicadores de arquivo online
                online_indicators = [
                    "download",
                    "télécharger",
                    "telecharger",
                    "file name",
                    "filename",
                ]
                
                if any(indicator in html_lower for indicator in online_indicators):
                    return "ONLINE", 1
                
                # Se não encontrou indicadores claros mas HTTP é 200, assume online
                return "ONLINE", 1
            
            # Outros status codes (500, 503, etc.)
            if response.status_code >= 500:
                return "ERROR", 0
            
            # Status desconhecido
            return "ERROR", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.ConnectionError:
            return "ERROR", 0
        except requests.exceptions.RequestException:
            return "ERROR", 0
        except Exception:
            return "ERROR", 0


# Instância global para ser importada
checker = OneFichierChecker()