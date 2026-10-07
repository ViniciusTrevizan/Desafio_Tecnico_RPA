"""PRODUCER — etapa web: coleta os dados, grava os CSVs e alimenta a fila de trabalho."""
from dataclasses import asdict

from src.core.contexto import Contexto
from src.core.decorators import log_etapa
from src.core.logger import banner, get_logger
from src.models.entidades import Comprador, Produto
from src.producer.gerador_identidade import gerar_comprador
from src.producer.navegador import abrir_navegador
from src.producer.saucedemo import coletar_catalogo, login, obter_credenciais
from src.utils.csv_handler import salvar_csv

log = get_logger("producer")


@log_etapa(log, "Producer: coleta web + geração de CSVs + fila")
def executar_producer(ctx: Contexto) -> None:
    banner(log, "Producer — automação web")
    evidencias = ctx.evidencias.para(log)

    with abrir_navegador() as page:
        comprador = gerar_comprador(page, evidencias)
        usuario, senha = obter_credenciais(page)
        login(page, usuario, senha, evidencias)
        produtos = coletar_catalogo(page, evidencias)

    persistir_csvs(ctx, comprador, produtos)
    enfileirar(ctx, comprador, produtos)


@log_etapa(log)
def persistir_csvs(ctx: Contexto, comprador: Comprador, produtos: list[Produto]) -> None:
    """Salva comprador.csv e catalogo.csv (ponte entre web e desktop)."""
    salvar_csv(ctx.csv_comprador, [comprador])
    log.info(f"CSV do comprador salvo: {ctx.csv_comprador.name} (1 registro)")
    total = salvar_csv(ctx.csv_catalogo, produtos)
    log.info(f"CSV do catálogo salvo: {ctx.csv_catalogo.name} ({total} registros)")


@log_etapa(log)
def enfileirar(ctx: Contexto, comprador: Comprador, produtos: list[Produto]) -> None:
    """Cria um item de fila para o contato e um para cada produto."""
    ctx.fila.limpar()
    item = ctx.fila.adicionar("contato", f"{comprador.nome} {comprador.sobrenome}", asdict(comprador))
    log.info(f"Fila ← contato [{item.id}] {item.referencia}")
    for produto in produtos:
        item = ctx.fila.adicionar("produto", produto.nome, asdict(produto))
        log.info(f"Fila ← produto [{item.id}] #{produto.numero} {produto.nome}")
    log.info(f"Fila pronta: {len(ctx.fila.itens())} itens pendentes")
