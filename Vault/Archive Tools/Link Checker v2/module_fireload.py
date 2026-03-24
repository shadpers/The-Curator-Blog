"""
Módulo Checker para FireLoad
Usa a API v2 com API key (se disponível) ou scraping como fallback.
Pastas são resolvidas via AJAX endpoint interno do site.
"""

import requests
import re
from bs4 import BeautifulSoup
from module_base import BaseChecker
import os

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False


class FireLoadChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "FireLoad"
    
    @property
    def domains(self) -> list:
        return ["fireload.com", "www.fireload.com"]
    
    def __init__(self):
        self.api_key = self._load_api_key()
        self.api_url = "https://api.fireload.com/v2/link/checker"
        self.ajax_folder_url = "https://www.fireload.com/ajax/_view_folder_v2_file_listing.ajax.php"
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        
        if CLOUDSCRAPER_AVAILABLE:
            self.scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        else:
            self.scraper = None
    
    def _load_api_key(self) -> str:
        """
        Carrega API key do FireLoad
        """
        # ============================================================
        # COLOQUE SUA API KEY AQUI (entre aspas):
        # ============================================================
        API_KEY = "ngwua2YSanAgfqLhKXcimTOeKbOaIQTlykdcO8wvLZ485AHJKVQE42AYjWqu87Yt"
        
        if API_KEY and API_KEY != "SUA_API_KEY_AQUI":
            return API_KEY
        
        # Tenta variável de ambiente como fallback
        api_key = os.environ.get('FIRELOAD_API_KEY')
        if api_key:
            return api_key.strip()
        
        return None

    # ──────────────────────────────────────────────────────────
    # Extração de IDs
    # ──────────────────────────────────────────────────────────

    def extract_file_id(self, url: str) -> str:
        """
        Extrai o ID do arquivo da URL do FireLoad.
        Formato: fireload.com/FILE_ID ou fireload.com/FILE_ID/filename
        """
        url = url.replace('www.fireload.com', 'fireload.com')
        match = re.search(r'fireload\.com/([a-z0-9]+)', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def extract_folder_hash(self, url: str) -> str:
        """
        Extrai o url_hash da URL de pasta do FireLoad.
        Formato: fireload.com/folder/URL_HASH/FolderName
        """
        match = re.search(r'/folder/([A-Za-z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None

    def is_folder_link(self, url: str) -> bool:
        """Retorna True se a URL for um link de pasta"""
        return '/folder/' in url

    # ──────────────────────────────────────────────────────────
    # Verificação de pastas
    # ──────────────────────────────────────────────────────────

    def _get_folder_file_urls(self, url: str) -> list:
        """
        Busca o conteúdo da pasta via POST ajax/_view_folder_v2_file_listing.ajax.php
        e extrai as URLs dos arquivos do atributo dturlkey de cada <li>.

        O endpoint retorna HTML com uma estrutura assim por arquivo:
          <li ... dturlkey="fe1796e55962a9b2" dtfullurl="https://www.fireload.com/fe1796e55962a9b2/..." ...>

        Retorna lista de URLs completas dos arquivos, ou lista vazia se a pasta
        não existe ou está vazia (rspTotalResults == 0).
        """
        url_hash = self.extract_folder_hash(url)
        if not url_hash:
            return []

        try:
            response = requests.post(
                self.ajax_folder_url,
                data={
                    "url_hash": url_hash,
                    "nodeId": "-1",
                    "filterText": "",
                    "filterUploadedDateRange": "",
                    "filterOrderBy": "",
                    "pageStart": "0",
                    "perPage": "100",
                },
                headers={
                    **self.headers,
                    'Referer': url,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                timeout=15
            )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, 'html.parser')

            # Verifica se há arquivos via hidden input rspTotalResults
            total_input = soup.find('input', id='rspTotalResults')
            if total_input and total_input.get('value', '0') == '0':
                return []

            # Extrai dtfullurl de cada <li> que tem esse atributo
            file_urls = []
            for li in soup.find_all('li', attrs={'dtfullurl': True}):
                file_urls.append(li['dtfullurl'])

            return file_urls

        except Exception:
            return []

    def check_folder_link(self, url: str) -> tuple:
        """
        Verifica status de uma pasta do FireLoad.

        Fluxo:
          1. POST ajax/_view_folder_v2_file_listing.ajax.php -> lista de arquivos
          2. Se não tiver arquivos -> OFFLINE
          3. Senão, manda cada URL pelo check_link_api em batch
          4. Conta quantos voltaram como online

        Retorna ("ONLINE", N) ou ("OFFLINE", 0).
        """
        try:
            file_urls = self._get_folder_file_urls(url)

            if not file_urls:
                return "OFFLINE", 0

            # Verifica todos os arquivos via API em batch
            # A API aceita múltiplas URLs separadas por vírgula no parâmetro 'data'
            params = {
                "data": ",".join(file_urls),
                "access_token": self.api_key
            }

            response = requests.get(
                self.api_url,
                params=params,
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                return "ERROR", 0

            data = response.json()

            if data.get("_status") != "success":
                return "ERROR", 0

            # Conta arquivos online nos resultados
            results = data.get("data", {})
            online_count = 0

            for file_url, file_info in results.items():
                # file_info pode ser False (API não reconheceu) ou um dict com status
                if isinstance(file_info, dict):
                    status = file_info.get("file_status", file_info.get("status", "")).lower()
                    if status == "active":
                        online_count += 1

            if online_count > 0:
                return "ONLINE", online_count

            return "OFFLINE", 0

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return "ERROR", 0
        except requests.exceptions.RequestException:
            return "ERROR", 0
        except (ValueError, KeyError):
            return "ERROR", 0
        except Exception:
            return "ERROR", 0

    # ──────────────────────────────────────────────────────────
    # Verificação de arquivos
    # ──────────────────────────────────────────────────────────

    def check_link_api(self, url: str) -> tuple:
        """Verifica usando a API do FireLoad (requer API key)"""
        if not self.api_key:
            return None
        
        try:
            params = {
                "data": url,
                "access_token": self.api_key
            }
            
            response = requests.get(
                self.api_url,
                params=params,
                headers={'Accept': 'application/json'},
                timeout=15
            )
            
            if response.status_code != 200:
                return None
            
            try:
                data = response.json()
            except ValueError:
                return None
            
            if data.get("_status") != "success":
                return None
            
            results_dict = data.get("data", {})
            if not results_dict:
                return "OFFLINE", 0
            
            # A API retorna um dicionário onde a chave é a URL enviada
            file_info = None
            for key in results_dict:
                if url in key or key in url:
                    file_info = results_dict[key]
                    break
            
            if not file_info and len(results_dict) > 0:
                file_info = list(results_dict.values())[0]
                
            if not file_info:
                return "OFFLINE", 0
                
            status = file_info.get("file_status", file_info.get("status", "")).lower()
            
            if status == "active":
                return "ONLINE", 1
            elif status in ["deleted", "removed", "expired"]:
                return "OFFLINE", 0
            else:
                if not status:
                    return "OFFLINE", 0
                return None
        
        except Exception:
            return None
    
    def check_link_scraping(self, url: str) -> tuple:
        """Verifica fazendo scraping da página (fallback)"""
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            
            if self.scraper:
                response = self.scraper.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            else:
                response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Se redirecionar para a página de erro, é offline
            if "fireload.com/error" in response.url:
                return "OFFLINE", 0
                
            if response.status_code == 404:
                return "OFFLINE", 0
            elif response.status_code >= 500:
                return "ERROR", 0
            elif response.status_code != 200:
                return "OFFLINE", 0
            
            html_lower = response.text.lower()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Indicadores de arquivo removido/offline
            offline_indicators = [
                "file not found",
                "file has been removed",
                "file has been deleted",
                "file doesn't exist",
                "invalid file",
                "removed for violation",
                "this file is no longer available",
                "invalid file key"
            ]
            
            if any(indicator in html_lower for indicator in offline_indicators):
                return "OFFLINE", 0
            
            download_button = soup.find('a', id='downloadButton')
            
            if download_button:
                href = download_button.get('href', '')
                if href == '/' or not href:
                    return "OFFLINE", 0
                return "ONLINE", 1
            
            if "download file" in html_lower and "file size" in html_lower:
                return "ONLINE", 1
                
            return "OFFLINE", 0
            
        except Exception:
            return "ERROR", 0

    # ──────────────────────────────────────────────────────────
    # Entrada principal
    # ──────────────────────────────────────────────────────────

    def check_link(self, url: str) -> tuple:
        """Verifica status de um link do FireLoad (arquivo ou pasta)"""

        # Pastas seguem caminho próprio
        if self.is_folder_link(url):
            return self.check_folder_link(url)

        # Arquivos: API primeiro, scraping como fallback
        if self.api_key:
            result = self.check_link_api(url)
            if result is not None:
                return result
        
        return self.check_link_scraping(url)


# Instância global para ser importada
checker = FireLoadChecker()