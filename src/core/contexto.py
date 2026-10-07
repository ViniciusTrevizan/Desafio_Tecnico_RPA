"""Contexto de uma execução: pastas de resultado, fila e evidências."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import settings
from src.core.evidencias import Evidencias
from src.core.fila import FilaArquivo


@dataclass
class Contexto:
    run_id: str
    pasta: Path
    pasta_logs: Path
    pasta_csv: Path
    pasta_prints: Path
    csv_comprador: Path
    csv_catalogo: Path
    arquivo_resumo: Path
    fila: FilaArquivo
    evidencias: Evidencias

    @classmethod
    def criar(cls, run_id: str | None = None, usar_ultima: bool = False) -> "Contexto":
        """Cria (ou reabre) a pasta resultados/<run_id> com csv/, prints/ e logs/.

        usar_ultima=True reaproveita a execução mais recente (útil para rodar só o consumer).
        """
        if not run_id and usar_ultima:
            anteriores = sorted(p.name for p in settings.PASTA_RESULTADOS.iterdir() if p.is_dir())
            run_id = anteriores[-1] if anteriores else None
        run_id = run_id or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        pasta = settings.PASTA_RESULTADOS / run_id
        pastas = {nome: pasta / nome for nome in ("logs", "csv", "prints")}
        for caminho in pastas.values():
            caminho.mkdir(parents=True, exist_ok=True)

        return cls(
            run_id=run_id,
            pasta=pasta,
            pasta_logs=pastas["logs"],
            pasta_csv=pastas["csv"],
            pasta_prints=pastas["prints"],
            csv_comprador=pastas["csv"] / "comprador.csv",
            csv_catalogo=pastas["csv"] / "catalogo.csv",
            arquivo_resumo=pasta / "resumo.json",
            fila=FilaArquivo(pasta / "fila.json"),
            evidencias=Evidencias(pastas["prints"]),
        )
