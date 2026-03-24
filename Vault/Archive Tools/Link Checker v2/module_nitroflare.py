"""
Módulo Checker para NitroFlare
Usa a API pública v2 para verificação de links
"""

import requests
import re
from module_base import BaseChecker


class NitroFlareChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "NitroFlare"
    
    @property
    def domains(self) -> list:
        return ["nitroflare.com"]
    
    def __init__(self):
        self.api_url = "https://nitroflare.com/api/v2/getFileInfo"
        self.ajax_folder_url = "https://nitroflare.com/ajax/folder.php"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    # ──────────────────────────────────────────────────────────
    # Extração de IDs
    # ──────────────────────────────────────────────────────────

    def extract_file_id(self, url: str) -> str:
        """
        Extrai o ID do arquivo da URL do NitroFlare

        Formato: https://nitroflare.com/view/FILE_ID/FILENAME
        """
        match = re.search(r'/view/([A-F0-9]+)', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def extract_folder_params(self, url: str) -> tuple:
        """
        Extrai userId e folder (base64) da URL da pasta.

        Formato: https://nitroflare.com/folder/USER_ID/BASE64_NAME
        Retorna (userId, folder) ou (None, None).
        """
        match = re.search(r'/folder/(\d+)/([A-Za-z0-9_=-]+)', url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def is_folder_link(self, url: str) -> bool:
        """Retorna True se a URL for um link de pasta"""
        return '/folder/' in url

    # ──────────────────────────────────────────────────────────
    # Verificação de pastas
    # ──────────────────────────────────────────────────────────

    def _get_folder_file_ids(self, url: str) -> list:
        """
        Busca o conteúdo da pasta via POST ajax/folder.php e extrai
        os FILE_IDs dos arquivos retornados.

        A resposta da API tem o formato:
          online:  {"name": "...", "files": [{"url": "view/FILE_ID/...", ...}, ...], "total": N}
          offline: {"name": "",    "files": [],                                      "total": 0}

        Retorna lista de FILE_IDs, ou lista vazia se a pasta não existe.
        """
        user_id, folder = self.extract_folder_params(url)
        if not user_id or not folder:
            return []

        payload = {
            "userId": user_id,
            "folder": folder,
            "page": "1",
            "perPage": "100",
        }

        response = requests.post(
            self.ajax_folder_url,
            data=payload,
            headers={
                **self.headers,
                'Referer': url,
                'X-Requested-With': 'XMLHttpRequest',
            },
            timeout=15
        )

        if response.status_code != 200:
            return []

        data = response.json()
        files = data.get("files", [])

        # Extrai FILE_ID de cada URL retornada (formato: "view/FILE_ID/...")
        file_ids = []
        for f in files:
            file_url = f.get("url", "")
            match = re.search(r'view/([A-F0-9]+)', file_url, re.IGNORECASE)
            if match:
                file_ids.append(match.group(1))

        return file_ids

    def check_folder_link(self, url: str) -> tuple:
        """
        Verifica status de um link de pasta do NitroFlare.

        Fluxo:
          1. POST ajax/folder.php -> lista de arquivos na pasta
          2. Se a lista estiver vazia -> OFFLINE
          3. Senão, manda todos os FILE_IDs para getFileInfo em batch
          4. Conta quantos voltaram como "online"

        Retorna ("ONLINE", N) ou ("OFFLINE", 0).
        """
        try:
            file_ids = self._get_folder_file_ids(url)

            # Pasta não existe ou está vazia
            if not file_ids:
                return "OFFLINE", 0

            # Verifica todos os arquivos em batch via getFileInfo
            params = {"files": ",".join(file_ids)}
            response = requests.get(
                self.api_url,
                params=params,
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                return "ERROR", 0

            data = response.json()

            if data.get("type") != "success":
                return "ERROR", 0

            # Conta arquivos online
            result = data.get("result", {})
            files = result.get("files", {})

            online_count = sum(
                1 for info in files.values()
                if info.get("status", "").lower() == "online"
            )

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

    def check_link(self, url: str) -> tuple:
        """Verifica status de um link do NitroFlare (arquivo ou pasta)"""

        if self.is_folder_link(url):
            return self.check_folder_link(url)

        try:
            file_id = self.extract_file_id(url)
            if not file_id:
                return "ERROR", 0

            params = {"files": file_id}
            response = requests.get(
                self.api_url,
                params=params,
                headers=self.headers,
                timeout=15
            )

            if response.status_code != 200:
                return "ERROR", 0

            data = response.json()

            if data.get("type") != "success":
                return "ERROR", 0

            result = data.get("result", {})
            files = result.get("files", {})
            file_info = files.get(file_id, {})

            status = file_info.get("status", "").lower()

            if status == "online":
                return "ONLINE", 1
            elif status == "offline":
                return "OFFLINE", 0
            else:
                return "ERROR", 0

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return "ERROR", 0
        except requests.exceptions.RequestException:
            return "ERROR", 0
        except (ValueError, KeyError):
            return "ERROR", 0
        except Exception:
            return "ERROR", 0

    # ──────────────────────────────────────────────────────────
    # Verificação em batch
    # ──────────────────────────────────────────────────────────

    def check_multiple_links(self, urls: list) -> dict:
        """
        Verifica múltiplos links de uma vez.

        Arquivos são processados em batch via getFileInfo.
        Pastas são processadas individualmente via check_folder_link
        (que internamente também usa batch para os arquivos dentro dela).

        Args:
            urls: Lista de URLs do NitroFlare (arquivos e/ou pastas)

        Returns:
            Dicionário {url: (status, count)}
        """
        results = {}

        folder_urls = []
        file_urls = []

        for url in urls:
            if self.is_folder_link(url):
                folder_urls.append(url)
            else:
                file_urls.append(url)

        # Processa pastas individualmente
        for url in folder_urls:
            results[url] = self.check_folder_link(url)

        # Processa arquivos em batch
        if file_urls:
            file_ids = []
            id_to_url = {}

            for url in file_urls:
                file_id = self.extract_file_id(url)
                if file_id:
                    file_ids.append(file_id)
                    id_to_url[file_id] = url
                else:
                    results[url] = ("ERROR", 0)

            if file_ids:
                try:
                    params = {"files": ",".join(file_ids)}
                    response = requests.get(
                        self.api_url,
                        params=params,
                        headers=self.headers,
                        timeout=30
                    )

                    if response.status_code != 200:
                        for url in file_urls:
                            if url not in results:
                                results[url] = ("ERROR", 0)
                    else:
                        data = response.json()

                        if data.get("type") != "success":
                            for url in file_urls:
                                if url not in results:
                                    results[url] = ("ERROR", 0)
                        else:
                            result = data.get("result", {})
                            files = result.get("files", {})

                            for file_id, url in id_to_url.items():
                                file_info = files.get(file_id, {})
                                status = file_info.get("status", "").lower()

                                if status == "online":
                                    results[url] = ("ONLINE", 1)
                                elif status == "offline":
                                    results[url] = ("OFFLINE", 0)
                                else:
                                    results[url] = ("ERROR", 0)

                except Exception:
                    for url in file_urls:
                        if url not in results:
                            results[url] = ("ERROR", 0)

        return results


# Instância global para ser importada
checker = NitroFlareChecker()