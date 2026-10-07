"""Testes de src/core/decorators.py — rastreabilidade (@log_etapa) e resiliência (@com_retry).

PDF §5: o log registra toda a execução. PDF §6: tratamento de erros e legibilidade do log
são critérios de avaliação.
"""
import functools
import logging
import re
from unittest.mock import call

import pytest

from config import settings
from src.core.decorators import _emitir, com_retry, log_etapa
from src.core.excecoes import BusinessException, ElementoNaoEncontrado, SystemException

log = logging.getLogger("rpa.teste")


def coletar_catalogo():
    """Percorre a vitrine.

    Esta linha não aparece no log.
    """
    return ["Sauce Labs Backpack"]


def _falha_vezes(vezes, erro):
    """Função que levanta `erro` nas primeiras `vezes` chamadas e depois devolve 'ok'."""
    chamadas = []

    def acao(*args, **kwargs):
        chamadas.append((args, kwargs))
        if len(chamadas) <= vezes:
            raise erro
        return "ok"

    return acao, chamadas


class TestEmitir:
    def test_registro_aponta_para_arquivo_linha_e_nome_da_funcao(self, caplog):
        _emitir(log, coletar_catalogo, logging.INFO, "mensagem")
        registro, = caplog.records
        codigo = coletar_catalogo.__code__
        assert (registro.pathname, registro.lineno, registro.funcName) == (
            codigo.co_filename, codigo.co_firstlineno, "coletar_catalogo")
        assert (registro.name, registro.levelno, registro.getMessage()) == ("rpa.teste", logging.INFO, "mensagem")

    def test_desembrulha_funcao_ja_decorada(self, caplog):
        @functools.wraps(coletar_catalogo)
        def embrulho():
            return coletar_catalogo()

        _emitir(log, embrulho, logging.INFO, "mensagem")
        assert (caplog.records[0].funcName, caplog.records[0].lineno) == (
            "coletar_catalogo", coletar_catalogo.__code__.co_firstlineno)

    def test_nao_emite_se_o_nivel_estiver_desabilitado(self, caplog):
        caplog.set_level(logging.ERROR, logger="rpa.teste")
        _emitir(log, coletar_catalogo, logging.INFO, "silenciado")
        assert caplog.records == []


class TestLogEtapa:
    def test_registra_inicio_e_fim_com_duracao_e_devolve_o_resultado(self, caplog):
        assert log_etapa(log)(coletar_catalogo)() == ["Sauce Labs Backpack"]
        inicio, fim = (r.getMessage() for r in caplog.records)
        assert inicio == "▶ INÍCIO | Percorre a vitrine."
        assert re.fullmatch(r"✔ FIM    \| Percorre a vitrine\. \(\d+\.\d{2}s\)", fim)

    def test_falha_registra_erro_com_tipo_mensagem_e_duracao_e_repropaga(self, caplog):
        erro = SystemException("timeout no seletor #login-button")

        @log_etapa(log, "Login no Sauce Demo")
        def login():
            raise erro

        with pytest.raises(SystemException) as capturado:
            login()
        assert capturado.value is erro
        _, falha = caplog.records
        assert falha.levelno == logging.ERROR
        assert re.fullmatch(r"✖ FALHA  \| Login no Sauce Demo \| SystemException: timeout no seletor "
                            r"#login-button \(\d+\.\d{2}s\)", falha.getMessage())

    def test_descricao_vem_do_parametro_ou_da_docstring_ou_do_nome(self, caplog):
        @log_etapa(log, "Descrição explícita")
        def com_parametro():
            """Docstring ignorada."""

        @log_etapa(log)
        def sem_docstring():
            pass

        log_etapa(log)(coletar_catalogo)()
        com_parametro()
        sem_docstring()
        assert [r.getMessage() for r in caplog.records if "INÍCIO" in r.getMessage()] == [
            "▶ INÍCIO | Percorre a vitrine.",
            "▶ INÍCIO | Descrição explícita",
            "▶ INÍCIO | sem_docstring",
        ]

    def test_preserva_nome_docstring_e_argumentos_da_funcao(self):
        @log_etapa(log)
        def somar(a, b=0):
            """Soma."""
            return a + b

        assert (somar.__name__, somar.__doc__) == ("somar", "Soma.")
        assert somar(2, b=3) == 5

    def test_registros_apontam_para_a_funcao_decorada_e_nao_para_o_wrapper(self, caplog):
        log_etapa(log)(coletar_catalogo)()
        assert {(r.filename, r.funcName) for r in caplog.records} == {("test_decorators.py", "coletar_catalogo")}


class TestComRetry:
    def test_sucesso_na_primeira_tentativa_nao_espera(self, sem_espera):
        acao, chamadas = _falha_vezes(0, SystemException("timeout"))
        assert com_retry(log, tentativas=3, espera=1)(acao)() == "ok"
        assert len(chamadas) == 1
        sem_espera.assert_not_called()

    def test_falha_tecnica_e_repetida_ate_dar_certo(self, sem_espera, caplog):
        acao, chamadas = _falha_vezes(2, SystemException("timeout"))
        assert com_retry(log, tentativas=3, espera=0.5)(acao)() == "ok"
        assert len(chamadas) == 3
        assert sem_espera.call_args_list == [call(0.5), call(0.5)]
        assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
            (logging.WARNING, "Tentativa 1/3 falhou (SystemException: timeout). Nova tentativa em 0.5s"),
            (logging.WARNING, "Tentativa 2/3 falhou (SystemException: timeout). Nova tentativa em 0.5s"),
        ]

    def test_esgotadas_as_tentativas_repropaga_o_erro(self, sem_espera):
        erro = ElementoNaoEncontrado("Imagem 'btn_novo_produto' não encontrada em 15s")
        acao, chamadas = _falha_vezes(99, erro)
        with pytest.raises(ElementoNaoEncontrado) as capturado:
            com_retry(log, tentativas=3, espera=0)(acao)()
        assert capturado.value is erro
        assert len(chamadas) == 3
        assert sem_espera.call_count == 2

    def test_business_exception_nao_e_repetida(self, sem_espera):
        acao, chamadas = _falha_vezes(99, BusinessException("Login recusado"))
        with pytest.raises(BusinessException):
            com_retry(log, tentativas=3, espera=0)(acao)()
        assert len(chamadas) == 1
        sem_espera.assert_not_called()

    def test_repassa_argumentos_e_preserva_metadados(self):
        @com_retry(log, tentativas=2, espera=0)
        def dobrar(valor, *, vezes=2):
            """Dobra."""
            return valor * vezes

        assert (dobrar(21), dobrar(2, vezes=3)) == (42, 6)
        assert (dobrar.__name__, dobrar.__doc__) == ("dobrar", "Dobra.")

    def test_padroes_de_tentativas_e_espera_vem_de_settings(self, sem_espera):
        acao, chamadas = _falha_vezes(99, SystemException("timeout"))
        with pytest.raises(SystemException):
            com_retry(log)(acao)()
        assert len(chamadas) == settings.TENTATIVAS_POR_ITEM
        assert sem_espera.call_args_list == [call(settings.ESPERA_ENTRE_TENTATIVAS)] * (settings.TENTATIVAS_POR_ITEM - 1)

    def test_aviso_de_nova_tentativa_aponta_para_a_funcao_decorada(self, caplog):
        acao, _ = _falha_vezes(1, SystemException("timeout"))
        com_retry(log, tentativas=2, espera=0)(acao)()
        assert caplog.records[0].funcName == "acao"
