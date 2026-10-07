"""Exceções do RPA.

BusinessException -> regra de negócio violada (dado inválido): NÃO adianta repetir.
SystemException   -> falha técnica (timeout, elemento não encontrado): pode ser repetida.
"""


class RPAException(Exception):
    """Base de todas as exceções do robô."""


class BusinessException(RPAException):
    """Dado inválido ou regra de negócio violada."""


class SystemException(RPAException):
    """Falha técnica recuperável com nova tentativa."""


class ElementoNaoEncontrado(SystemException):
    """Imagem/elemento não localizado na tela dentro do timeout."""
