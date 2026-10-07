"""Configuração centralizada de logs do RPA.

Arquivos gerados em <execução>/logs:
    execucao.log -> visão completa da execução, item a item
    producer.log -> somente a etapa web (coleta)
    consumer.log -> somente a etapa desktop (cadastro)
    erros.log    -> apenas WARNING ou acima, com traceback

Cada linha traz: data/hora | nível | componente | arquivo:linha | função() | mensagem
"""
import logging
import os
import sys
from pathlib import Path

RAIZ_LOGGER = "rpa"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
FORMATO_ARQUIVO = (
    "%(asctime)s | %(levelname)-8s | %(componente)-8s | "
    "%(local)-28s | %(funcao)-30s | %(message)s"
)

_CINZA, _NEGRITO, _RESET = "\033[90m", "\033[1m", "\033[0m"
_CORES = {
    "DEBUG": "\033[90m",
    "INFO": "\033[36m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41;97m",
}


class _EnriquecerRegistro(logging.Filter):
    """Adiciona ao registro os campos usados nos formatos (componente, local, função)."""

    def filter(self, record: logging.LogRecord) -> bool:
        partes = record.name.split(".")
        record.componente = partes[1] if len(partes) > 1 else "main"
        record.local = f"{record.filename}:{record.lineno}"
        record.funcao = f"{record.funcName}()"
        return True


class _FormatadorConsole(logging.Formatter):
    """Formato enxuto e colorido para o terminal."""

    def __init__(self, usar_cores: bool):
        super().__init__(datefmt="%H:%M:%S")
        self.usar_cores = usar_cores

    def _c(self, codigo: str, texto: str) -> str:
        return f"{codigo}{texto}{_RESET}" if self.usar_cores else texto

    def format(self, record: logging.LogRecord) -> str:
        linha = " ".join([
            self._c(_CINZA, self.formatTime(record, self.datefmt)),
            self._c(_CORES.get(record.levelname, ""), f"{record.levelname:<8}"),
            self._c(_NEGRITO, f"{record.componente:<8}"),
            self._c(_CINZA, f"{record.local:<26} {record.funcao:<28}"),
            record.getMessage(),
        ])
        if record.exc_info:
            linha += "\n" + self.formatException(record.exc_info)
        return linha


def _handler_arquivo(caminho: Path, nivel: int) -> logging.FileHandler:
    handler = logging.FileHandler(caminho, encoding="utf-8")
    handler.setLevel(nivel)
    handler.setFormatter(logging.Formatter(FORMATO_ARQUIVO, FORMATO_DATA))
    handler.addFilter(_EnriquecerRegistro())
    return handler


def configurar_logs(pasta_logs: Path, nivel_console: str = "INFO") -> None:
    """Cria os handlers de console e arquivos separados. Pode ser chamada mais de uma vez."""
    pasta_logs.mkdir(parents=True, exist_ok=True)

    raiz = logging.getLogger(RAIZ_LOGGER)
    raiz.setLevel(logging.DEBUG)
    raiz.propagate = False
    for nome in (RAIZ_LOGGER, f"{RAIZ_LOGGER}.producer", f"{RAIZ_LOGGER}.consumer"):
        logging.getLogger(nome).handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(nivel_console.upper())
    console.addFilter(_EnriquecerRegistro())
    console.setFormatter(_FormatadorConsole(sys.stdout.isatty() and not os.getenv("NO_COLOR")))

    raiz.addHandler(console)
    raiz.addHandler(_handler_arquivo(pasta_logs / "execucao.log", logging.DEBUG))
    raiz.addHandler(_handler_arquivo(pasta_logs / "erros.log", logging.WARNING))
    logging.getLogger(f"{RAIZ_LOGGER}.producer").addHandler(
        _handler_arquivo(pasta_logs / "producer.log", logging.DEBUG))
    logging.getLogger(f"{RAIZ_LOGGER}.consumer").addHandler(
        _handler_arquivo(pasta_logs / "consumer.log", logging.DEBUG))


def get_logger(componente: str = "") -> logging.Logger:
    """Retorna o logger do componente ('producer', 'consumer' ou vazio para 'main')."""
    return logging.getLogger(f"{RAIZ_LOGGER}.{componente}" if componente else RAIZ_LOGGER)


def banner(logger: logging.Logger, titulo: str) -> None:
    """Escreve um separador visual para marcar o início de uma etapa."""
    logger.info("═" * 72, stacklevel=2)
    logger.info(f"  {titulo.upper()}", stacklevel=2)
    logger.info("═" * 72, stacklevel=2)
