"""Conferência final: CSVs (web) × itens cadastrados (desktop) e resumo da execução."""
import json

from src.core.contexto import Contexto
from src.core.fila import Status
from src.core.logger import banner, get_logger
from src.models.entidades import Comprador, Produto
from src.utils.csv_handler import ler_csv

log = get_logger()


def gerar_relatorio(ctx: Contexto) -> bool:
    """Compara as quantidades do CSV com os sucessos da fila e grava resumo.json."""
    banner(log, "Resumo da execução")

    no_csv = {
        "contato": len(ler_csv(ctx.csv_comprador, Comprador)) if ctx.csv_comprador.exists() else 0,
        "produto": len(ler_csv(ctx.csv_catalogo, Produto)) if ctx.csv_catalogo.exists() else 0,
    }
    cadastrados = {tipo: len(ctx.fila.itens(tipo, Status.SUCESSO)) for tipo in no_csv}
    sucesso = all(no_csv[t] == cadastrados[t] and no_csv[t] > 0 for t in no_csv)

    log.info(f"{'Tipo':<10}{'CSV (web)':>12}{'Fakturama':>12}   Situação")
    for tipo in no_csv:
        situacao = "OK" if no_csv[tipo] == cadastrados[tipo] else "DIVERGENTE"
        nivel = log.info if situacao == "OK" else log.error
        nivel(f"{tipo:<10}{no_csv[tipo]:>12}{cadastrados[tipo]:>12}   {situacao}")

    for item in ctx.fila.itens():
        if item.status != Status.SUCESSO:
            log.warning(f"Pendência: {item.tipo} '{item.referencia}' → {item.status} {item.erro}")

    resumo = {
        "run_id": ctx.run_id,
        "sucesso": sucesso,
        "csv": no_csv,
        "cadastrados": cadastrados,
        "fila": ctx.fila.resumo(),
        "prints": sorted(p.name for p in ctx.pasta_prints.glob("*.png")),
    }
    ctx.arquivo_resumo.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Resumo salvo em {ctx.arquivo_resumo}")
    (log.info if sucesso else log.error)(
        "RESULTADO: dados web e desktop batem 100%" if sucesso else "RESULTADO: há divergências — ver erros.log")
    return sucesso
