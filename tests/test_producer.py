"""Testes de src/producer/producer.py — a etapa web completa.

PDF §4.1–4.3: gerar o comprador, logar e raspar o catálogo, nessa ordem.
PDF §4.4: salvar comprador e catálogo em CSVs — a ponte de dados para a etapa desktop.
"""
from contextlib import contextmanager
from dataclasses import asdict
from unittest.mock import MagicMock, call

import pytest

from src.core.excecoes import BusinessException
from src.core.fila import Status
from src.core.logger import get_logger
from src.models.entidades import Comprador, Produto
from src.producer import producer
from src.utils.csv_handler import ler_csv


@pytest.fixture
def web(monkeypatch, comprador, produtos):
    """Substitui o navegador e os passos web por dublês que registram a ordem das chamadas."""
    web = MagicMock()
    web.pagina = MagicMock(name="page")
    web.gerar_comprador.return_value = comprador
    web.obter_credenciais.return_value = ("standard_user", "secret_sauce")
    web.coletar_catalogo.return_value = produtos

    @contextmanager
    def abrir_navegador():
        web.abrir_navegador()
        yield web.pagina
        web.fechar_navegador()

    monkeypatch.setattr(producer, "abrir_navegador", abrir_navegador)
    for passo in ("gerar_comprador", "obter_credenciais", "login", "coletar_catalogo"):
        monkeypatch.setattr(producer, passo, getattr(web, passo))
    return web


class TestExecutarProducer:
    def test_executa_os_passos_web_na_ordem_do_pdf_com_a_mesma_pagina(self, ctx, web):
        producer.executar_producer(ctx)
        evidencias = web.gerar_comprador.call_args.args[1]
        assert web.mock_calls == [
            call.abrir_navegador(),
            call.gerar_comprador(web.pagina, evidencias),
            call.obter_credenciais(web.pagina),
            call.login(web.pagina, "standard_user", "secret_sauce", evidencias),
            call.coletar_catalogo(web.pagina, evidencias),
            call.fechar_navegador(),
        ]

    def test_prints_da_etapa_web_vao_para_a_pasta_da_execucao_no_log_do_producer(self, ctx, web):
        producer.executar_producer(ctx)
        evidencias = web.gerar_comprador.call_args.args[1]
        assert evidencias.pasta == ctx.pasta_prints
        assert evidencias.log is get_logger("producer")

    def test_grava_csvs_e_fila_com_o_que_foi_coletado(self, ctx, web, comprador, produtos):
        producer.executar_producer(ctx)
        assert ler_csv(ctx.csv_comprador, Comprador) == [comprador]
        assert ler_csv(ctx.csv_catalogo, Produto) == produtos
        assert len(ctx.fila.itens()) == 1 + len(produtos)

    def test_falha_na_web_nao_gera_csv_nem_fila(self, ctx, web):
        web.login.side_effect = BusinessException("Login recusado: Epic sadface: Sorry, this user has been locked out.")
        with pytest.raises(BusinessException):
            producer.executar_producer(ctx)
        web.coletar_catalogo.assert_not_called()
        assert not ctx.csv_comprador.exists()
        assert not ctx.csv_catalogo.exists()
        assert ctx.fila.itens() == []


class TestPersistirCsvs:
    def test_salva_comprador_csv_e_catalogo_csv(self, ctx, comprador, produtos, caplog):
        producer.persistir_csvs(ctx, comprador, produtos)
        assert ler_csv(ctx.csv_comprador, Comprador) == [comprador]
        assert ler_csv(ctx.csv_catalogo, Produto) == produtos
        assert "CSV do comprador salvo: comprador.csv (1 registro)" in caplog.text
        assert "CSV do catálogo salvo: catalogo.csv (6 registros)" in caplog.text

    def test_catalogo_vazio_nao_gera_csv_do_catalogo(self, ctx, comprador):
        with pytest.raises(ValueError, match="Nenhum registro"):
            producer.persistir_csvs(ctx, comprador, [])
        assert not ctx.csv_catalogo.exists()


class TestEnfileirar:
    def test_cria_um_item_para_o_contato_e_um_para_cada_produto(self, ctx, comprador, produtos):
        producer.enfileirar(ctx, comprador, produtos)
        contato, *itens_produto = ctx.fila.itens()
        assert (contato.tipo, contato.referencia, contato.payload) == ("contato", "Vitória Rocha", asdict(comprador))
        assert [(i.tipo, i.referencia, i.payload) for i in itens_produto] == [
            ("produto", p.nome, asdict(p)) for p in produtos]
        assert {i.status for i in ctx.fila.itens()} == {Status.PENDENTE}

    def test_reexecutar_substitui_a_fila_sem_duplicar_itens(self, ctx, comprador, produtos):
        producer.enfileirar(ctx, comprador, produtos)
        producer.enfileirar(ctx, comprador, produtos)
        assert len(ctx.fila.itens()) == 1 + len(produtos)

    def test_registra_no_log_cada_item_enfileirado(self, ctx, comprador, produtos, caplog):
        producer.enfileirar(ctx, comprador, produtos)
        assert caplog.text.count("Fila ← produto") == len(produtos)
        assert "Fila ← contato" in caplog.text
        assert "Fila pronta: 7 itens pendentes" in caplog.text
