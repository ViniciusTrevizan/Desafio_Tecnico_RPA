"""Testes de src/producer/navegador.py — ciclo de vida do Chromium usado na etapa web."""
from unittest.mock import MagicMock

import pytest

from config import settings
from src.producer import navegador


@pytest.fixture
def pw(monkeypatch):
    """sync_playwright simulado; devolve o objeto entregue pelo `with sync_playwright()`."""
    pw = MagicMock(name="pw")
    sync_playwright = MagicMock(name="sync_playwright")
    sync_playwright.return_value.__enter__.return_value = pw
    monkeypatch.setattr(navegador, "sync_playwright", sync_playwright)
    return pw


class TestAbrirNavegador:
    def test_entrega_uma_pagina_do_chromium_configurada(self, pw, monkeypatch):
        monkeypatch.setattr(settings, "NAVEGADOR_HEADLESS", True)
        monkeypatch.setattr(settings, "TIMEOUT_WEB_MS", 12_000)
        chromium = pw.chromium.launch.return_value

        with navegador.abrir_navegador() as pagina:
            assert pagina is chromium.new_context.return_value.new_page.return_value

        pw.chromium.launch.assert_called_once_with(headless=True)
        chromium.new_context.assert_called_once_with(viewport={"width": 1366, "height": 900}, locale="pt-BR")
        pagina.set_default_timeout.assert_called_once_with(12_000)

    def test_fecha_contexto_e_navegador_ao_sair(self, pw, caplog):
        chromium = pw.chromium.launch.return_value
        contexto = chromium.new_context.return_value
        with navegador.abrir_navegador():
            contexto.close.assert_not_called()
        contexto.close.assert_called_once_with()
        chromium.close.assert_called_once_with()
        assert "Navegador encerrado" in caplog.text

    def test_fecha_o_navegador_mesmo_quando_a_etapa_falha(self, pw):
        chromium = pw.chromium.launch.return_value
        with pytest.raises(RuntimeError, match="seletor não encontrado"):
            with navegador.abrir_navegador():
                raise RuntimeError("seletor não encontrado")
        chromium.new_context.return_value.close.assert_called_once_with()
        chromium.close.assert_called_once_with()
