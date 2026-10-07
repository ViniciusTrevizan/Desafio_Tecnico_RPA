"""Decorators de rastreabilidade (log de etapa) e resiliência (retry)."""
import functools
import inspect
import logging
import time

from config import settings
from src.core.excecoes import BusinessException


def _emitir(logger: logging.Logger, func, nivel: int, mensagem: str) -> None:
    """Emite o log como se viesse da função decorada (arquivo, linha e nome reais)."""
    if logger.isEnabledFor(nivel):
        codigo = inspect.unwrap(func).__code__
        logger.handle(logger.makeRecord(
            logger.name, nivel, codigo.co_filename, codigo.co_firstlineno,
            mensagem, None, None, func=codigo.co_name,
        ))


def log_etapa(logger: logging.Logger, descricao: str | None = None):
    """Registra início, fim, duração e falha da função decorada.

    A descrição vem do parâmetro ou da 1ª linha da docstring. O registro aponta
    para o arquivo/linha/nome da função decorada (e não para este wrapper).
    """

    def decorador(func):
        texto = descricao or (inspect.getdoc(func) or func.__name__).splitlines()[0]

        def emitir(nivel: int, mensagem: str) -> None:
            _emitir(logger, func, nivel, mensagem)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            emitir(logging.INFO, f"▶ INÍCIO | {texto}")
            inicio = time.perf_counter()
            try:
                resultado = func(*args, **kwargs)
            except Exception as erro:
                duracao = time.perf_counter() - inicio
                emitir(logging.ERROR, f"✖ FALHA  | {texto} | {type(erro).__name__}: {erro} ({duracao:.2f}s)")
                raise
            emitir(logging.INFO, f"✔ FIM    | {texto} ({time.perf_counter() - inicio:.2f}s)")
            return resultado

        return wrapper

    return decorador


def com_retry(logger: logging.Logger, tentativas: int | None = None, espera: float | None = None):
    """Repete a função em falhas técnicas; BusinessException é propagada sem repetir."""
    tentativas = tentativas or settings.TENTATIVAS_POR_ITEM
    espera = settings.ESPERA_ENTRE_TENTATIVAS if espera is None else espera

    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for tentativa in range(1, tentativas + 1):
                try:
                    return func(*args, **kwargs)
                except BusinessException:
                    raise
                except Exception as erro:
                    if tentativa == tentativas:
                        raise
                    _emitir(
                        logger, func, logging.WARNING,
                        f"Tentativa {tentativa}/{tentativas} falhou "
                        f"({type(erro).__name__}: {erro}). Nova tentativa em {espera}s"
                    )
                    time.sleep(espera)

        return wrapper

    return decorador
