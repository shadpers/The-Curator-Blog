"""
Módulo Checker para Akirabox
Usa a API pública para verificação de arquivos.

FUNCIONAMENTO ESPECIAL:
Este módulo suporta verificação de múltiplas URLs separadas por vírgula.
Formato do TXT:
    Nome do Item
    https://url1,https://url2,https://url3

Verifica cada URL e retorna a contagem total de arquivos online.
"""

import requests
from module_base import BaseChecker


class AkiraboxChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Akirabox"
    
    @property
    def domains(self) -> list:
        return ["akirabox.to", "akirabox.com"]
    
    def __init__(self):
        # A API usa akirabox.com (não .to)
        self.api_url = "https://akirabox.com/api/files"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def normalize_url(self, url: str) -> str:
        """
        Normaliza a URL substituindo .to por .com para a API.
        A API só funciona com URLs .com, mas os links compartilhados usam .to
        """
        return url.replace('akirabox.to', 'akirabox.com')
    
    def is_folder_link(self, url: str) -> bool:
        """Verifica se a URL é de uma pasta"""
        return '/folder' in url
    
    def check_single_file(self, url: str) -> tuple:
        """
        Verifica um único arquivo via API.
        Retorna (status, count) onde count é 1 se online, 0 caso contrário.
        """
        try:
            # Normaliza a URL para .com
            normalized_url = self.normalize_url(url)
            
            # Adiciona https:// se não tiver protocolo
            if not normalized_url.startswith('http'):
                normalized_url = 'https://' + normalized_url
            
            # Chama a API
            params = {'url': normalized_url}
            response = requests.get(
                self.api_url,
                params=params,
                headers=self.headers,
                timeout=15
            )
            
            # Tenta parsear JSON
            try:
                data = response.json()
            except ValueError:
                return "ERROR", 0
            
            # Verifica o status code da resposta
            status = data.get('status')
            
            if status == 200:
                return "ONLINE", 1
            elif status == 404:
                return "OFFLINE", 0
            elif status == 400:
                return "ERROR", 0
            else:
                return "ERROR", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.ConnectionError:
            return "ERROR", 0
        except requests.exceptions.RequestException:
            return "ERROR", 0
        except Exception:
            return "ERROR", 0
    
    def check_link(self, url: str) -> tuple:
        """
        Verifica status de link(s) do Akirabox.
        
        FORMATO ESPECIAL:
        Suporta múltiplas URLs separadas por vírgula na mesma linha:
            https://url1,https://url2,https://url3
        
        Verifica cada URL e retorna:
            ("ONLINE", N) - onde N é o número de arquivos online
            ("OFFLINE", 0) - se todos os arquivos estão offline
            ("ERROR", -1) - se for pasta ou houver erro em todos
        """
        # Remove espaços em branco extras
        url = url.strip()
        
        # Separa por vírgula
        urls = [u.strip() for u in url.split(',') if u.strip()]
        
        # Se tiver apenas uma URL e for pasta, retorna ERROR
        if len(urls) == 1 and self.is_folder_link(urls[0]):
            return "ERROR", -1
        
        # Verifica cada URL
        online_count = 0
        offline_count = 0
        error_count = 0
        
        for single_url in urls:
            # Pula URLs vazias ou de pastas
            if not single_url or self.is_folder_link(single_url):
                error_count += 1
                continue
            
            status, count = self.check_single_file(single_url)
            
            if status == "ONLINE":
                online_count += count
            elif status == "OFFLINE":
                offline_count += 1
            else:
                error_count += 1
        
        # Determina status geral
        if online_count > 0:
            # Pelo menos um arquivo está online
            return "ONLINE", online_count
        elif offline_count > 0:
            # Todos verificados estão offline
            return "OFFLINE", 0
        else:
            # Todos deram erro
            return "ERROR", 0


# Instância global para ser importada
checker = AkiraboxChecker()