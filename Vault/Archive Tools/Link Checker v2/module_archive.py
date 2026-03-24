"""
Módulo Checker para Archive.org
Suporta verificação de links do Internet Archive
"""

import requests
import re
from bs4 import BeautifulSoup
from module_base import BaseChecker


class ArchiveChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Archive.org"
    
    @property
    def domains(self) -> list:
        return ["archive.org"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def check_link(self, url: str) -> tuple:
        """
        Verifica status de link do Archive.org
        
        Implementação copiada do checker completo funcional
        """
        try:
            # Verifica links diretos de items (exemplo: archive.org/items/...)
            if ".archive.org/" in url and "/items/" in url:
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
            
            # Verifica links de download direto
            if "/download/" in url and not url.endswith('/'):
                response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return "ONLINE", 1
                elif response.status_code == 404:
                    return "OFFLINE", 0
                else:
                    # Tenta GET se HEAD não funcionar
                    try:
                        response = requests.get(url, headers=self.headers, timeout=10, stream=True)
                        response.raise_for_status()
                        return "ONLINE", 1
                    except:
                        return "OFFLINE", 0
            
            # Para outros tipos de links, faz GET completo
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Verifica 404
            if response.status_code == 404:
                return "OFFLINE", 0
            
            text_lower = response.text.lower()
            
            # Verifica indicadores de item não disponível
            if "item cannot be found" in text_lower or "not available" in text_lower:
                return "OFFLINE", 0
            
            # Se for link de detalhes (/details/), tenta contar arquivos
            if "/details/" in url:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Procura pelo link de download que mostra quantidade de arquivos
                files_link = soup.find('a', string=re.compile(r'download.*\d+.*files?', re.IGNORECASE))
                if files_link:
                    match = re.search(r'(\d+)', files_link.text)
                    if match:
                        return "ONLINE", int(match.group(1))
                
                # Fallback: procura padrão "X file(s)" ou "X item(s)" no HTML
                match = re.search(r'(\d+)\s*(?:file|item)s?', response.text, re.IGNORECASE)
                if match:
                    count = int(match.group(1))
                    if count > 0:
                        return "ONLINE", count
                
                # Se chegou aqui e status é 200, está online mas sem contagem
                return "ONLINE", 1
            
            # Se status é 200 e não caiu em nenhum caso anterior
            if response.status_code == 200:
                return "ONLINE", 1
            
            # Caso não identificado
            return "UNKNOWN", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "OFFLINE", 0
            return "ERROR", 0
        except Exception as e:
            return "ERROR", 0


# Instância global para ser importada
checker = ArchiveChecker()