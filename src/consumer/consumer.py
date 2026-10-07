"""CONSUMER — etapa desktop: consome a fila e cadastra cada item no Fakturama."""
import time
from typing import Callable

from config import settings
from src.consumer.fakturama import Fakturama
from src.core.contexto import Contexto
from src.core.decorators import log_etapa
from src.core.evidencias import Evidencias
from src.core.excecoes import BusinessException
from src.core.fila import FilaArquivo, ItemFila
from src.core.logger import banner, get_logger
from src.models.entidades import Comprador, Produto

log = get_logger("consumer")


@log_etapa(log, "Consumer: cadastro desktop dos itens da fila")
def executar_consumer(ctx: Contexto, reprocessar_falhas: bool = False) -> None:
    banner(log, "Consumer — automação desktop")
    if reprocessar_falhas:
        log.info(f"{ctx.fila.reabrir_falhas()} itens com falha recolocados na fila")

    evidencias = ctx.evidencias.para(log)
    app = Fakturama(evidencias)
    app.abrir()

    processar_fila(ctx.fila, "contato", lambda p: app.cadastrar_contato(Comprador(**p)), app, evidencias)
    processar_fila(ctx.fila, "produto", lambda p: app.cadastrar_produto(Produto(**p).validar()), app, evidencias)

    app.evidenciar_lista("contatos")
    app.evidenciar_lista("produtos")


def processar_fila(fila: FilaArquivo, tipo: str, acao: Callable[[dict], None],
                   app: Fakturama, evidencias: Evidencias) -> None:
    """Consome todos os itens pendentes de um tipo, com retry em falhas técnicas."""
    total = len(fila.itens(tipo))
    pendentes = len(fila.itens(tipo, "PENDENTE"))
    log.info(f"── Fila '{tipo}': {pendentes} pendentes de {total} ──")

    while item := fila.proximo(tipo):
        _processar_item(item, fila, acao, app, evidencias, total)


def _processar_item(item: ItemFila, fila: FilaArquivo, acao: Callable[[dict], None],
                    app: Fakturama, evidencias: Evidencias, total: int) -> None:
    """Executa a ação do item e registra SUCESSO, nova tentativa ou falha definitiva."""
    posicao = fila.itens(item.tipo).index(item) + 1
    prefixo = f"[{posicao}/{total}] {item.tipo} '{item.referencia}' (id={item.id}, tentativa {item.tentativas})"
    log.info(f"{prefixo} → processando")
    try:
        acao(item.payload)
    except BusinessException as erro:
        log.error(f"{prefixo} → FALHA DE NEGÓCIO: {erro}")
        fila.falhar(item, str(erro), negocio=True)
    except Exception as erro:
        evidencias.erro(f"{item.tipo}_{item.id}")
        app.recuperar()
        if item.tentativas < settings.TENTATIVAS_POR_ITEM:
            log.warning(f"{prefixo} → falha técnica ({type(erro).__name__}: {erro}); voltando para a fila")
            fila.devolver(item, str(erro))
            time.sleep(settings.ESPERA_ENTRE_TENTATIVAS)
        else:
            log.exception(f"{prefixo} → FALHA DEFINITIVA após {item.tentativas} tentativas")
            fila.falhar(item, str(erro))
    else:
        fila.concluir(item)
        log.info(f"{prefixo} → ✔ SUCESSO")
