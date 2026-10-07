"""Entidades de negócio trafegadas entre producer e consumer."""
import re
from dataclasses import dataclass

from src.core.excecoes import BusinessException


@dataclass
class Comprador:
    nome: str
    sobrenome: str
    cep: str

    def validar(self) -> "Comprador":
        """Garante campos preenchidos e CEP com dígitos (BR: 8, US: 5)."""
        if not self.nome.strip() or not self.sobrenome.strip():
            raise BusinessException(f"Comprador sem nome/sobrenome: {self}")
        if len(re.sub(r"\D", "", self.cep)) not in (5, 8):
            raise BusinessException(f"CEP inválido: '{self.cep}'")
        return self


@dataclass
class Produto:
    numero: str
    nome: str
    descricao: str
    preco: str  # decimal com ponto, ex.: "29.99"

    def validar(self) -> "Produto":
        """Garante nome preenchido e preço numérico positivo."""
        if not self.nome.strip():
            raise BusinessException(f"Produto {self.numero} sem nome")
        try:
            if float(self.preco) <= 0:
                raise ValueError
        except ValueError:
            raise BusinessException(f"Preço inválido no produto '{self.nome}': '{self.preco}'") from None
        return self
