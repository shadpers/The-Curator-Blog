"""
Módulo Checker para Transfer.it (MEGA)
Sistema de expiração baseado em 90 dias a partir do primeiro scan
"""

import requests
from datetime import datetime, timedelta
from module_base import BaseChecker

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False


class TransferItChecker(BaseChecker):
    
    @property
    def service_name(self) -> str:
        return "Transfer.it"
    
    @property
    def domains(self) -> list:
        return ["transfer.it"]
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        if CLOUDSCRAPER_AVAILABLE:
            self.scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        else:
            self.scraper = None
        
        # Limite de expiração: 90 dias
        self.expiration_days = 90
    
    def check_link(self, url: str) -> tuple:
        """
        Verifica status de link do Transfer.it
        
        Transfer.it mantém arquivos por apenas 90 dias.
        Como não há forma confiável de detectar via scraping se o link está ativo,
        usamos a data do primeiro scan como referência.
        
        O histórico é gerenciado pelo checker principal, então aqui apenas:
        1. Verificamos se o link responde (não dá erro de rede)
        2. Retornamos dados para o sistema de histórico calcular os dias
        """
        try:
            # Normaliza URL
            if not url.startswith('http'):
                url = 'https://' + url
            
            # Tenta acessar o link para verificar se responde
            if self.scraper:
                response = self.scraper.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            else:
                response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Se respondeu (qualquer código 2xx ou 3xx), consideramos que existe
            if response.status_code < 400:
                # Retorna "ONLINE" mas com marcador especial
                # O count será "90d" para indicar sistema de dias
                return "ONLINE", "90d"
            else:
                # Códigos 4xx/5xx indicam problema
                return "OFFLINE", 0
            
        except requests.exceptions.Timeout:
            return "ERROR", 0
        except requests.exceptions.ConnectionError:
            return "ERROR", 0
        except Exception as e:
            return "ERROR", 0
    
    def calculate_days_remaining(self, first_scan_date: str) -> int:
        """
        Calcula quantos dias restam até expiração
        
        Args:
            first_scan_date: Data do primeiro scan no formato "DD/MM/YYYY HH:MM"
        
        Returns:
            Número de dias restantes (negativo se já expirou)
        """
        try:
            # Parse da data do primeiro scan
            scan_date = datetime.strptime(first_scan_date, "%d/%m/%Y %H:%M")
            
            # Data de expiração = primeiro scan + 90 dias
            expiration_date = scan_date + timedelta(days=self.expiration_days)
            
            # Calcula diferença
            today = datetime.now()
            days_remaining = (expiration_date - today).days
            
            return days_remaining
            
        except Exception:
            # Se houver erro no parse, retorna -1 (considerar expirado)
            return -1
    
    def get_expiration_status(self, first_scan_date: str) -> tuple:
        """
        Retorna status baseado na contagem de dias
        
        Returns:
            Tupla (status, days_info) onde:
            - status: "ONLINE", "EXPIRING" ou "OFFLINE"
            - days_info: String descritiva dos dias restantes
        """
        days = self.calculate_days_remaining(first_scan_date)
        
        if days < 0:
            return "OFFLINE", "Expirado"
        elif days == 0:
            return "EXPIRING", "Expira hoje"
        elif days <= 7:
            return "EXPIRING", f"{days}d restantes ⚠️"
        else:
            return "ONLINE", f"{days}d restantes"


# Instância global para ser importada
checker = TransferItChecker()