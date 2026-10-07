"""Testes de src/core/evidencias.py — prints da tela, do navegador e de erros.

PDF §4.7 e §5: prints que comprovam o cadastro do comprador e a lista de produtos,
guardados na pasta de resultados da execução.
"""
import logging
import re
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.core.evidencias import Evidencias
from src.core.logger import get_logger


@pytest.fixture
def mss_falso(monkeypatch):
    """mss simulado: a área de trabalho é uma imagem 4x3 e to_png grava um PNG de verdade."""
    sct = MagicMock(name="sct")
    sct.__enter__.return_value = sct
    sct.monitors = [{"left": 0, "top": 0, "width": 4, "height": 3}, {"left": 0, "top": 0, "width": 4, "height": 3}]
    sct.grab.return_value = SimpleNamespace(rgb=bytes([200, 30, 30]) * 12, size=(4, 3))

    tools = types.ModuleType("mss.tools")
    tools.to_png = lambda dados, tamanho, output: Image.frombytes("RGB", tamanho, dados).save(output)
    mss = types.ModuleType("mss")
    mss.mss = MagicMock(return_value=sct)
    mss.tools = tools
    monkeypatch.setitem(sys.modules, "mss", mss)
    monkeypatch.setitem(sys.modules, "mss.tools", tools)
    return sct


class TestInitEPara:
    def test_cria_a_pasta_e_usa_o_logger_principal(self, tmp_path):
        evidencias = Evidencias(tmp_path / "prints")
        assert (tmp_path / "prints").is_dir()
        assert evidencias.log is get_logger()

    def test_continua_a_numeracao_dos_prints_ja_existentes(self, tmp_path):
        for nome in ("01_gerador_identidade_090000.png", "02_saucedemo_catalogo_090100.png", "anotacao.txt"):
            (tmp_path / nome).touch()
        assert Evidencias(tmp_path)._novo_caminho("contato_cadastrado").name.startswith("03_contato_cadastrado_")

    def test_para_compartilha_pasta_e_numeracao_mas_troca_o_logger(self, tmp_path):
        geral = Evidencias(tmp_path)
        producer = geral.para(get_logger("producer"))
        assert producer.pasta == geral.pasta
        assert producer.log is get_logger("producer")
        assert [geral._novo_caminho("a").name[:2], producer._novo_caminho("b").name[:2],
                geral._novo_caminho("c").name[:2]] == ["01", "02", "03"]


class TestNovoCaminho:
    def test_numera_em_sequencia_com_nome_e_horario(self, tmp_path):
        evidencias = Evidencias(tmp_path)
        primeiro = evidencias._novo_caminho("contato_cadastrado")
        segundo = evidencias._novo_caminho("lista_produtos")
        assert primeiro.parent == segundo.parent == tmp_path
        assert re.fullmatch(r"01_contato_cadastrado_\d{6}\.png", primeiro.name)
        assert re.fullmatch(r"02_lista_produtos_\d{6}\.png", segundo.name)


class TestTela:
    def test_salva_png_de_todos_os_monitores_na_pasta_de_prints(self, tmp_path, mss_falso, caplog):
        caminho = Evidencias(tmp_path).tela("lista_produtos")
        assert caminho.parent == tmp_path
        assert re.fullmatch(r"01_lista_produtos_\d{6}\.png", caminho.name)
        with Image.open(caminho) as imagem:
            assert imagem.size == (4, 3)
        mss_falso.grab.assert_called_once_with(mss_falso.monitors[0])  # monitor 0 = área de trabalho inteira
        assert f"📸 Print da tela salvo: {caminho.name}" in caplog.text


class TestNavegador:
    def test_salva_a_pagina_inteira_por_padrao(self, tmp_path, caplog):
        page = MagicMock(name="page")
        caminho = Evidencias(tmp_path).navegador(page, "saucedemo_catalogo")
        assert re.fullmatch(r"01_saucedemo_catalogo_\d{6}\.png", caminho.name)
        page.screenshot.assert_called_once_with(path=str(caminho), full_page=True)
        assert f"📸 Print do navegador salvo: {caminho.name}" in caplog.text

    def test_pode_salvar_somente_a_area_visivel(self, tmp_path):
        page = MagicMock(name="page")
        Evidencias(tmp_path).navegador(page, "gerador_identidade", pagina_inteira=False)
        assert page.screenshot.call_args.kwargs["full_page"] is False


class TestErro:
    def test_com_pagina_tira_print_da_area_visivel_do_navegador(self, tmp_path):
        page = MagicMock(name="page")
        caminho = Evidencias(tmp_path).erro("login", page)
        assert re.fullmatch(r"01_ERRO_login_\d{6}\.png", caminho.name)
        page.screenshot.assert_called_once_with(path=str(caminho), full_page=False)

    def test_sem_pagina_tira_print_da_tela(self, tmp_path, mss_falso):
        caminho = Evidencias(tmp_path).erro("produto_a1b2c3d4")
        assert re.fullmatch(r"01_ERRO_produto_a1b2c3d4_\d{6}\.png", caminho.name)
        assert caminho.exists()

    def test_falha_na_captura_nao_mascara_o_erro_original(self, tmp_path, caplog):
        page = MagicMock(name="page")
        page.screenshot.side_effect = RuntimeError("navegador fechado")
        assert Evidencias(tmp_path).erro("login", page) is None
        aviso = caplog.records[-1]
        assert aviso.levelno == logging.WARNING
        assert aviso.getMessage() == "Não foi possível capturar print de erro 'login': navegador fechado"
