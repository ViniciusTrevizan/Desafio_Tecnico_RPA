"""Testes de src/consumer/consumer.py — consumo da fila e cadastro desktop.

PDF §4.5/§4.6: cadastrar o comprador e CADA produto coletado no Fakturama.
PDF §4.7: prints das listas ao final. PDF §5: log item a item. PDF §6: tratamento de erros.
"""
from dataclasses import asdict
from unittest.mock import MagicMock, call

import pytest

from config import settings
from src.consumer import consumer
from src.consumer.fakturama import Fakturama
from src.core.excecoes import BusinessException, ElementoNaoEncontrado
from src.core.fila import Status
from src.core.logger import get_logger


@pytest.fixture
def fila(ctx, comprador, produtos):
    """Fila como o producer deixa: 1 contato + 6 produtos pendentes."""
    ctx.fila.adicionar("contato", f"{comprador.nome} {comprador.sobrenome}", asdict(comprador))
    for produto in produtos:
        ctx.fila.adicionar("produto", produto.nome, asdict(produto))
    return ctx.fila


@pytest.fixture
def app(monkeypatch):
    """Fakturama simulado — também é o que executar_consumer instancia."""
    app = MagicMock(spec=Fakturama)
    monkeypatch.setattr(consumer, "Fakturama", MagicMock(return_value=app))
    return app


def _falha_tecnica(*nomes, vezes=99):
    """Ação de cadastro que falha (imagem não encontrada) para os produtos indicados."""
    restantes = dict.fromkeys(nomes, vezes)

    def acao(payload):
        if restantes.get(payload["nome"]):
            restantes[payload["nome"]] -= 1
            raise ElementoNaoEncontrado("Imagem 'campo_produto_preco' não encontrada em 15s")

    return acao


class TestExecutarConsumer:
    def test_abre_o_fakturama_cadastra_comprador_e_cada_produto_e_tira_prints_das_listas(
            self, ctx, fila, app, comprador, produtos):
        consumer.executar_consumer(ctx)
        assert app.mock_calls == [
            call.abrir(),
            call.cadastrar_contato(comprador),
            *[call.cadastrar_produto(produto) for produto in produtos],
            call.evidenciar_lista("contatos"),
            call.evidenciar_lista("produtos"),
        ]
        assert fila.resumo() == {"contato": {Status.SUCESSO: 1}, "produto": {Status.SUCESSO: 6}}

    def test_prints_da_etapa_desktop_usam_o_log_do_consumer(self, ctx, fila, app):
        consumer.executar_consumer(ctx)
        evidencias = consumer.Fakturama.call_args.args[0]
        assert evidencias.pasta == ctx.pasta_prints
        assert evidencias.log is get_logger("consumer")

    def test_produto_invalido_na_fila_nao_e_cadastrado(self, ctx, fila, app):
        corrompido = fila.itens("produto")[1]
        corrompido.payload["preco"] = "abc"
        consumer.executar_consumer(ctx)
        assert corrompido.status == Status.FALHA_NEGOCIO
        assert app.cadastrar_produto.call_count == 5

    def _falhar_onesie(self, fila):
        while item := fila.proximo():
            if item.referencia == "Sauce Labs Onesie":
                fila.falhar(item, "timeout")
            else:
                fila.concluir(item)

    def test_reprocessar_falhas_cadastra_somente_o_que_tinha_falhado(self, ctx, fila, app):
        self._falhar_onesie(fila)
        consumer.executar_consumer(ctx, reprocessar_falhas=True)
        app.cadastrar_contato.assert_not_called()
        assert [c.args[0].nome for c in app.cadastrar_produto.call_args_list] == ["Sauce Labs Onesie"]
        assert fila.itens(status=Status.SUCESSO) == fila.itens()

    def test_sem_reprocessar_os_itens_com_falha_ficam_como_estao(self, ctx, fila, app):
        self._falhar_onesie(fila)
        consumer.executar_consumer(ctx)
        app.cadastrar_produto.assert_not_called()
        assert [i.referencia for i in fila.itens(status=Status.FALHA_SISTEMA)] == ["Sauce Labs Onesie"]


class TestProcessarFila:
    def test_cadastra_somente_os_pendentes_do_tipo_na_ordem(self, fila, app, evidencias, produtos):
        acao = MagicMock()
        consumer.processar_fila(fila, "produto", acao, app, evidencias)
        assert acao.call_args_list == [call(asdict(p)) for p in produtos]
        assert fila.itens("contato")[0].status == Status.PENDENTE

    def test_informa_no_log_quantos_estao_pendentes(self, fila, app, evidencias, caplog):
        consumer.processar_fila(fila, "produto", MagicMock(), app, evidencias)
        assert "── Fila 'produto': 6 pendentes de 6 ──" in caplog.text

    def test_falha_temporaria_e_resolvida_na_nova_tentativa(self, fila, app, evidencias):
        consumer.processar_fila(fila, "produto", _falha_tecnica("Sauce Labs Backpack", vezes=1), app, evidencias)
        mochila = fila.itens("produto")[0]
        assert (mochila.status, mochila.tentativas) == (Status.SUCESSO, 2)
        assert fila.resumo()["produto"] == {Status.SUCESSO: 6}

    def test_falha_definitiva_de_um_produto_nao_impede_os_demais(self, fila, app, evidencias):
        consumer.processar_fila(fila, "produto", _falha_tecnica("Sauce Labs Bike Light"), app, evidencias)
        luz = fila.itens("produto")[1]
        assert (luz.status, luz.tentativas) == (Status.FALHA_SISTEMA, settings.TENTATIVAS_POR_ITEM)
        assert fila.resumo()["produto"] == {Status.SUCESSO: 5, Status.FALHA_SISTEMA: 1}


class TestProcessarItem:
    @pytest.fixture
    def item(self, fila):
        return fila.proximo("produto")  # Sauce Labs Backpack, 1ª tentativa

    def test_sucesso_conclui_o_item_e_registra_no_log(self, fila, item, app, evidencias, caplog):
        acao = MagicMock()
        consumer._processar_item(item, fila, acao, app, evidencias, total=6)
        acao.assert_called_once_with(item.payload)
        assert item.status == Status.SUCESSO
        assert f"[1/6] produto 'Sauce Labs Backpack' (id={item.id}, tentativa 1) → ✔ SUCESSO" in caplog.text

    def test_falha_de_negocio_nao_e_repetida(self, fila, item, app, evidencias, sem_espera, caplog):
        erro = "Preço inválido no produto 'Sauce Labs Backpack': 'abc'"
        consumer._processar_item(item, fila, MagicMock(side_effect=BusinessException(erro)), app, evidencias, total=6)
        assert (item.status, item.erro) == (Status.FALHA_NEGOCIO, erro)
        app.recuperar.assert_not_called()
        evidencias.erro.assert_not_called()
        sem_espera.assert_not_called()
        assert f"→ FALHA DE NEGÓCIO: {erro}" in caplog.text

    def test_falha_tecnica_tira_print_recupera_a_tela_e_devolve_para_a_fila(
            self, fila, item, app, evidencias, sem_espera, caplog):
        erro = ElementoNaoEncontrado("Imagem 'btn_novo_produto' não encontrada em 15s")
        consumer._processar_item(item, fila, MagicMock(side_effect=erro), app, evidencias, total=6)
        assert (item.status, item.erro) == (Status.PENDENTE, str(erro))
        evidencias.erro.assert_called_once_with(f"produto_{item.id}")
        app.recuperar.assert_called_once_with()
        sem_espera.assert_called_once_with(settings.ESPERA_ENTRE_TENTATIVAS)
        assert "→ falha técnica (ElementoNaoEncontrado: " in caplog.text
        assert "voltando para a fila" in caplog.text

    def test_falha_tecnica_na_ultima_tentativa_e_definitiva(self, fila, item, app, evidencias, caplog):
        item.tentativas = settings.TENTATIVAS_POR_ITEM
        erro = ElementoNaoEncontrado("Imagem 'btn_novo_produto' não encontrada em 15s")
        consumer._processar_item(item, fila, MagicMock(side_effect=erro), app, evidencias, total=6)
        assert (item.status, item.erro) == (Status.FALHA_SISTEMA, str(erro))
        app.recuperar.assert_called_once_with()
        assert f"→ FALHA DEFINITIVA após {settings.TENTATIVAS_POR_ITEM} tentativas" in caplog.text
