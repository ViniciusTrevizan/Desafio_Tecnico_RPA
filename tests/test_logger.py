"""Testes de src/core/logger.py — logs da execução.

PDF §5: "Log de execução — registro textual de toda a execução do robô, item a item".
PDF §6: a qualidade e a legibilidade do log são critérios de avaliação.
"""
import logging
import re
import sys

import pytest

from src.core.logger import (_EnriquecerRegistro, _FormatadorConsole, _handler_arquivo, banner,
                             configurar_logs, get_logger)

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _registro(nome="rpa.producer", nivel=logging.INFO, mensagem="Coletado: #1 'Sauce Labs Backpack'",
              exc_info=None):
    """LogRecord como se emitido por coletar_catalogo() em saucedemo.py:71."""
    return logging.LogRecord(nome, nivel, "/projeto/src/producer/saucedemo.py", 71, mensagem, None,
                             exc_info, func="coletar_catalogo")


def _enriquecido(**kwargs):
    registro = _registro(**kwargs)
    _EnriquecerRegistro().filter(registro)
    return registro


class TestGetLogger:
    @pytest.mark.parametrize("componente, nome", [("", "rpa"), ("producer", "rpa.producer"), ("consumer", "rpa.consumer")])
    def test_devolve_o_logger_do_componente(self, componente, nome):
        assert get_logger(componente) is logging.getLogger(nome)

    def test_sem_componente_devolve_o_logger_principal(self):
        assert get_logger() is logging.getLogger("rpa")


class TestEnriquecerRegistro:
    @pytest.mark.parametrize("nome, componente", [("rpa.producer", "producer"), ("rpa.consumer", "consumer"), ("rpa", "main")])
    def test_adiciona_componente_local_e_funcao(self, nome, componente):
        registro = _registro(nome=nome)
        assert _EnriquecerRegistro().filter(registro) is True
        assert (registro.componente, registro.local, registro.funcao) == (componente, "saucedemo.py:71", "coletar_catalogo()")


class TestFormatadorConsole:
    def test_sem_cores_mostra_hora_nivel_componente_local_funcao_e_mensagem(self):
        linha = _FormatadorConsole(usar_cores=False).format(_enriquecido())
        assert not ANSI.search(linha)
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2} INFO\s+producer\s+saucedemo\.py:71\s+coletar_catalogo\(\)\s+"
                            r"Coletado: #1 'Sauce Labs Backpack'", linha)

    def test_com_cores_destaca_o_nivel_sem_alterar_o_texto(self):
        linha = _FormatadorConsole(usar_cores=True).format(_enriquecido(nivel=logging.ERROR))
        assert "\033[31mERROR   \033[0m" in linha
        assert ANSI.sub("", linha).endswith("Coletado: #1 'Sauce Labs Backpack'")

    def test_inclui_o_traceback_quando_ha_excecao(self):
        try:
            raise ValueError("seletor não encontrado")
        except ValueError:
            registro = _enriquecido(nivel=logging.ERROR, exc_info=sys.exc_info())
        linha = _FormatadorConsole(usar_cores=False).format(registro)
        assert "Traceback" in linha
        assert linha.endswith("ValueError: seletor não encontrado")

    @pytest.mark.parametrize("usar_cores, esperado", [(True, "\033[1mtexto\033[0m"), (False, "texto")])
    def test_c_aplica_a_cor_somente_quando_habilitada(self, usar_cores, esperado):
        assert _FormatadorConsole(usar_cores)._c("\033[1m", "texto") == esperado


class TestHandlerArquivo:
    def test_grava_em_utf8_no_formato_documentado(self, tmp_path):
        caminho = tmp_path / "execucao.log"
        handler = _handler_arquivo(caminho, logging.DEBUG)
        try:
            handler.handle(_registro(mensagem="• Preço ← '29,99'"))
        finally:
            handler.close()
        # README: data hora | nível | componente | arquivo:linha | função() | mensagem
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| INFO {5}\| producer \| saucedemo\.py:71 +"
                            r"\| coletar_catalogo\(\) +\| • Preço ← '29,99'\n",
                            caminho.read_text(encoding="utf-8"))

    def test_usa_o_nivel_minimo_informado(self, tmp_path):
        handler = _handler_arquivo(tmp_path / "erros.log", logging.WARNING)
        handler.close()
        assert handler.level == logging.WARNING


class TestConfigurarLogs:
    def _ler(self, pasta):
        return {arquivo.name: arquivo.read_text(encoding="utf-8") for arquivo in pasta.glob("*.log")}

    def test_separa_os_logs_por_componente_e_por_gravidade(self, tmp_path):
        pasta = tmp_path / "execucao" / "logs"  # ainda não existe
        configurar_logs(pasta)
        get_logger().info("orquestrador iniciado")
        get_logger("producer").info("produto coletado")
        get_logger("consumer").warning("falha técnica no cadastro")

        logs = self._ler(pasta)
        assert set(logs) == {"execucao.log", "producer.log", "consumer.log", "erros.log"}
        assert all(m in logs["execucao.log"] for m in ("orquestrador iniciado", "produto coletado", "falha técnica"))
        assert "produto coletado" in logs["producer.log"]
        assert "falha técnica" not in logs["producer.log"] and "orquestrador" not in logs["producer.log"]
        assert "falha técnica no cadastro" in logs["consumer.log"] and "produto coletado" not in logs["consumer.log"]
        assert logs["erros.log"].splitlines() == [l for l in logs["execucao.log"].splitlines() if "WARNING" in l]

    def test_pode_ser_chamada_de_novo_sem_duplicar_linhas(self, tmp_path):
        configurar_logs(tmp_path)
        configurar_logs(tmp_path)
        get_logger("producer").info("uma vez só")
        logs = self._ler(tmp_path)
        assert logs["execucao.log"].count("uma vez só") == 1
        assert logs["producer.log"].count("uma vez só") == 1

    def test_console_respeita_o_nivel_e_nao_usa_cores_fora_do_terminal(self, tmp_path, capsys):
        configurar_logs(tmp_path, nivel_console="warning")
        get_logger().info("detalhe só no arquivo")
        get_logger().warning("aviso no console")
        saida = capsys.readouterr().out
        assert "aviso no console" in saida
        assert "detalhe só no arquivo" not in saida
        assert not ANSI.search(saida)
        assert "detalhe só no arquivo" in self._ler(tmp_path)["execucao.log"]


class TestBanner:
    def test_escreve_o_titulo_em_caixa_alta_entre_separadores(self, caplog):
        banner(get_logger("producer"), "Producer — automação web")
        assert [r.getMessage() for r in caplog.records] == ["═" * 72, "  PRODUCER — AUTOMAÇÃO WEB", "═" * 72]
        assert {r.levelno for r in caplog.records} == {logging.INFO}

    def test_registro_aponta_para_quem_chamou(self, caplog):
        banner(get_logger(), "Resumo da execução")
        assert {r.funcName for r in caplog.records} == {"test_registro_aponta_para_quem_chamou"}
