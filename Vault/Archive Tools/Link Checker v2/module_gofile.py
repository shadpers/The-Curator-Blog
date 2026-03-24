"""
Módulo Checker para Gofile
Suporta verificação de links do Gofile usando a API v2
"""

import requests
from module_base import BaseChecker


class GofileChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Gofile"
    
    @property
    def domains(self) -> list:
        return ["gofile.io"]
    
    def __init__(self):
        self.api_base = "https://api.gofile.io"
        self.website_token = "4fd6sg89d7s6"  # Hardcoded no config.js do site
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Website-Token': self.website_token,
        }
        self._guest_token = None
    
    def _get_guest_token(self) -> str:
        """
        Cria uma conta guest e retorna o token.
        Tokens guest são gratuitos e criados sob demanda.
        """
        if self._guest_token:
            return self._guest_token
        
        try:
            response = requests.post(
                f"{self.api_base}/accounts",
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self._guest_token = data.get("data", {}).get("token")
                    return self._guest_token
        except Exception:
            pass
        
        return None
    
    def extract_content_id(self, url: str) -> str:
        """
        Extrai o content ID da URL do Gofile.
        Formato: gofile.io/d/CONTENT_ID
        """
        content_id = url.split('/')[-1].split('?')[0]
        return content_id if content_id else None
    
    def check_link(self, url: str) -> tuple:
        """Verifica status de link do Gofile (arquivo ou pasta)"""
        try:
            content_id = self.extract_content_id(url)
            if not content_id:
                return "ERROR", 0
            
            # Obtém token guest
            token = self._get_guest_token()
            if not token:
                return "ERROR", 0
            
            # Monta headers com Authorization
            headers = self.headers.copy()
            headers['Authorization'] = f'Bearer {token}'
            
            # Chama a API /contents/{contentId}
            api_url = f"{self.api_base}/contents/{content_id}"
            response = requests.get(api_url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                return "ERROR", 0
            
            data = response.json()
            
            # Verifica status da resposta
            status = data.get('status')
            
            if status == 'error-notFound':
                return "OFFLINE", 0
            
            if status != 'ok':
                return "ERROR", 0
            
            # Conteúdo existe e está online
            content_data = data.get('data', {})
            
            # Verifica se podemos acessar
            if not content_data.get('canAccess', False):
                return "OFFLINE", 0
            
            # Conta arquivos dependendo do tipo
            content_type = content_data.get('type')
            
            if content_type == 'folder':
                # Para pastas, conta os arquivos dentro
                children = content_data.get('children', {})
                file_count = sum(
                    1 for child in children.values()
                    if child.get('type') == 'file'
                )
                return "ONLINE", file_count
            
            elif content_type == 'file':
                # Para arquivo individual
                return "ONLINE", 1
            
            else:
                # Tipo desconhecido, mas está online
                return "ONLINE", 1
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.ConnectionError:
            return "ERROR", 0
        except requests.exceptions.RequestException:
            return "ERROR", 0
        except (ValueError, KeyError):
            return "ERROR", 0
        except Exception:
            return "ERROR", 0


# Instância global para ser importada
checker = GofileChecker()