"""Ciclo de vida do navegador Playwright usado pelo producer."""
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from config import settings
from src.core.logger import get_logger

log = get_logger("producer")


@contextmanager
def abrir_navegador():
    """Abre o Chromium, entrega uma página pronta e garante o fechamento ao final."""
    log.info(f"Iniciando Chromium (headless={settings.NAVEGADOR_HEADLESS})")
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=settings.NAVEGADOR_HEADLESS)
        contexto = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
        pagina = contexto.new_page()
        pagina.set_default_timeout(settings.TIMEOUT_WEB_MS)
        try:
            yield pagina
        finally:
            contexto.close()
            navegador.close()
            log.info("Navegador encerrado")
