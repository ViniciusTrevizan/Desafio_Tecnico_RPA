"""Leitura e escrita dos CSVs que servem de ponte entre a etapa web e a desktop."""
import csv
from dataclasses import asdict, fields
from pathlib import Path

from config import settings


def salvar_csv(caminho: Path, registros: list) -> int:
    """Grava uma lista de dataclasses em CSV (cabeçalho = campos da dataclass)."""
    if not registros:
        raise ValueError(f"Nenhum registro para salvar em {caminho.name}")
    colunas = [f.name for f in fields(registros[0])]
    with caminho.open("w", newline="", encoding=settings.CSV_ENCODING) as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=settings.CSV_DELIMITADOR)
        escritor.writeheader()
        escritor.writerows(asdict(r) for r in registros)
    return len(registros)


def ler_csv(caminho: Path, classe) -> list:
    """Lê o CSV e converte cada linha na dataclass informada."""
    with caminho.open(newline="", encoding=settings.CSV_ENCODING) as arquivo:
        return [classe(**linha) for linha in csv.DictReader(arquivo, delimiter=settings.CSV_DELIMITADOR)]
