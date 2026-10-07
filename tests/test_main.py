"""Testes de main.py — orquestração das etapas e códigos de saída.

PDF §4: etapa web (producer) seguida da etapa desktop (consumer).
PDF §5: CSVs, prints e log reunidos na pasta de resultados.
PDF §6: dados web e desktop batendo 100% e tratamento de erros.
"""
import json
import re
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, call

import pytest

import main
from config import settings
from src.consumer import consumer
from src.core.evidencias import Evidencias
from src.core.excecoes import BusinessException, SystemException
from src.models.entidades import Comprador, Produto
from src.producer import producer
from src.utils.csv_handler import ler_csv


@pytest.fixture(autouse=True)
def ambiente_valido(monkeypatch):
    """A máquina que roda os testes pode não ter sessão gráfica X11: a validação é simulada."""
    validar = MagicMock(name="validar_ambiente")
    monkeypatch.setattr(main, "validar_ambiente", validar)
    return validar


def _rodar(monkeypatch, *argumentos):
    monkeypatch.setattr(sys, "argv", ["main.py", *argumentos])
    return main.main()


class TestLerArgumentos:
    def test_sem_argumentos_executa_todas_as_etapas(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py"])
        args = main.ler_argumentos()
        assert (args.etapa, args.run_id, args.reprocessar_falhas) == ("todas", None, False)

    def test_le_etapa_run_id_e_reprocessar_falhas(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py", "--etapa", "consumer", "--run-id", "2026-10-07_08-40-01",
                                          "--reprocessar-falhas"])
        args = main.ler_argumentos()
        assert (args.etapa, args.run_id, args.reprocessar_falhas) == ("consumer", "2026-10-07_08-40-01", True)

    def test_recusa_etapa_desconhecida(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["main.py", "--etapa", "desktop"])
        with pytest.raises(SystemExit) as saida:
            main.ler_argumentos()
        assert saida.value.code == 2
        assert "--etapa" in capsys.readouterr().err


class TestMain:
    @pytest.fixture
    def etapas(self, monkeypatch):
        """Etapas, logs e conferência simulados; registra a ordem das chamadas."""
        etapas = MagicMock()
        etapas.gerar_relatorio.return_value = True
        monkeypatch.setattr(producer, "executar_producer", etapas.executar_producer)
        monkeypatch.setattr(consumer, "executar_consumer", etapas.executar_consumer)
        monkeypatch.setattr(main, "configurar_logs", etapas.configurar_logs)
        monkeypatch.setattr(main, "gerar_relatorio", etapas.gerar_relatorio)
        return etapas

    @pytest.mark.parametrize("etapa, precisa_desktop", [("todas", True), ("consumer", True), ("producer", False)])
    def test_valida_o_ambiente_antes_de_tudo(self, monkeypatch, etapas, ambiente_valido, pasta_resultados,
                                             etapa, precisa_desktop):
        _rodar(monkeypatch, "--etapa", etapa)
        ambiente_valido.assert_called_once_with(precisa_desktop=precisa_desktop)

    def test_ambiente_invalido_aborta_sem_rodar_nenhuma_etapa(self, monkeypatch, etapas, ambiente_valido, caplog):
        ambiente_valido.side_effect = SystemException("Sessão gráfica Wayland detectada")
        assert _rodar(monkeypatch) == 1
        etapas.executar_producer.assert_not_called()
        etapas.executar_consumer.assert_not_called()
        assert "Ambiente inválido: Sessão gráfica Wayland detectada" in caplog.text

    def test_execucao_completa_roda_producer_consumer_e_conferencia(self, monkeypatch, etapas, pasta_resultados):
        assert _rodar(monkeypatch, "--run-id", "exec") == 0
        ctx = etapas.executar_producer.call_args.args[0]
        assert ctx.pasta == pasta_resultados / "exec"
        assert etapas.mock_calls == [
            call.configurar_logs(ctx.pasta_logs, settings.NIVEL_LOG_CONSOLE),
            call.executar_producer(ctx),
            call.executar_consumer(ctx, False),
            call.gerar_relatorio(ctx),
        ]

    def test_etapa_producer_coleta_sem_cadastrar_nem_conferir(self, monkeypatch, etapas):
        assert _rodar(monkeypatch, "--etapa", "producer") == 0
        etapas.executar_producer.assert_called_once()
        etapas.executar_consumer.assert_not_called()
        etapas.gerar_relatorio.assert_not_called()

    def test_etapa_consumer_retoma_a_ultima_execucao(self, monkeypatch, etapas, pasta_resultados):
        (pasta_resultados / "2026-10-07_08-40-01").mkdir()
        assert _rodar(monkeypatch, "--etapa", "consumer", "--reprocessar-falhas") == 0
        ctx = etapas.executar_consumer.call_args.args[0]
        assert ctx.run_id == "2026-10-07_08-40-01"
        etapas.executar_consumer.assert_called_once_with(ctx, True)
        etapas.executar_producer.assert_not_called()
        etapas.gerar_relatorio.assert_called_once_with(ctx)

    def test_regra_de_negocio_violada_retorna_2_e_ainda_confere(self, monkeypatch, etapas, caplog):
        etapas.executar_producer.side_effect = BusinessException("Login recusado")
        assert _rodar(monkeypatch) == 2
        etapas.executar_consumer.assert_not_called()
        etapas.gerar_relatorio.assert_called_once()
        assert "Execução abortada por regra de negócio: Login recusado" in caplog.text

    def test_erro_inesperado_retorna_1_e_tira_print_do_erro(self, monkeypatch, etapas, caplog):
        print_erro = MagicMock()
        monkeypatch.setattr(Evidencias, "erro", print_erro)
        etapas.executar_consumer.side_effect = RuntimeError("Fakturama travou")
        assert _rodar(monkeypatch) == 1
        print_erro.assert_called_once_with("execucao")
        etapas.gerar_relatorio.assert_called_once()
        assert "Execução abortada por erro inesperado" in caplog.text

    def test_interrupcao_pelo_usuario_retorna_130(self, monkeypatch, etapas, caplog):
        etapas.executar_consumer.side_effect = KeyboardInterrupt
        assert _rodar(monkeypatch) == 130
        assert "Execução interrompida pelo usuário" in caplog.text


def test_execucao_completa_simulada_entrega_o_que_o_pdf_exige(monkeypatch, pasta_resultados, comprador, produtos):
    """PDF §5 e §6 de ponta a ponta — só os sites e as telas do Fakturama são simulados.

    O que foi cadastrado no desktop tem de ser exatamente o que está nos CSVs, o resumo
    precisa apontar sucesso e o log de execução precisa registrar cada item.
    """
    cadastrados = []

    class FakturamaSimulado:
        def __init__(self, evidencias):
            pass

        def abrir(self):
            pass

        def cadastrar_contato(self, contato):
            cadastrados.append(contato)

        def cadastrar_produto(self, produto):
            cadastrados.append(produto)

        def evidenciar_lista(self, tipo):
            pass

        def recuperar(self):
            pass

    @contextmanager
    def navegador_simulado():
        yield MagicMock(name="page")

    monkeypatch.setattr(producer, "abrir_navegador", navegador_simulado)
    monkeypatch.setattr(producer, "gerar_comprador", lambda page, evidencias: comprador)
    monkeypatch.setattr(producer, "obter_credenciais", lambda page: ("standard_user", "secret_sauce"))
    monkeypatch.setattr(producer, "login", lambda page, usuario, senha, evidencias: None)
    monkeypatch.setattr(producer, "coletar_catalogo", lambda page, evidencias: produtos)
    monkeypatch.setattr(consumer, "Fakturama", FakturamaSimulado)

    assert _rodar(monkeypatch, "--run-id", "ponta_a_ponta") == 0

    pasta = pasta_resultados / "ponta_a_ponta"
    csvs = ler_csv(pasta / "csv" / "comprador.csv", Comprador) + ler_csv(pasta / "csv" / "catalogo.csv", Produto)
    assert cadastrados == csvs == [comprador, *produtos]
    assert json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))["sucesso"] is True

    assert {log.name for log in (pasta / "logs").iterdir()} == {"execucao.log", "producer.log", "consumer.log", "erros.log"}
    execucao = (pasta / "logs" / "execucao.log").read_text(encoding="utf-8")
    assert re.search(r"\[1/1\] contato 'Vitória Rocha' \(id=\w+, tentativa 1\) → ✔ SUCESSO", execucao)
    for posicao, produto in enumerate(produtos, start=1):
        assert re.search(rf"\[{posicao}/6\] produto '{re.escape(produto.nome)}' \(id=\w+, tentativa 1\) → ✔ SUCESSO",
                         execucao)
