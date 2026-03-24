"""
Módulo Base para Checkers de Links
Define a interface que todos os módulos devem implementar
"""

from abc import ABC, abstractmethod
from typing import Tuple, List

class BaseChecker(ABC):
    """Classe base abstrata para todos os checkers de serviços"""
    
    @property
    @abstractmethod
    def service_name(self) -> str:
        """Nome do serviço (ex: 'TeraBox', 'Pixeldrain')"""
        pass
    
    @property
    @abstractmethod
    def domains(self) -> List[str]:
        """Lista de domínios que este checker suporta"""
        pass
    
    @abstractmethod
    def check_link(self, url: str) -> Tuple[str, any]:
        """
        Verifica o status de um link
        
        Args:
            url: URL a ser verificada
            
        Returns:
            Tupla (status, count) onde:
            - status: "ONLINE", "OFFLINE", "ERROR", "UNKNOWN"
            - count: Número de arquivos ou outro indicador relevante
        """
        pass
    
    def supports_url(self, url: str) -> bool:
        """Verifica se este checker suporta a URL fornecida"""
        url_lower = url.lower()
        return any(domain.lower() in url_lower for domain in self.domains)
    
    def __str__(self):
        return f"{self.service_name} Checker"
