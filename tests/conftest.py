"""Configuração compartilhada dos testes unitários.

O robô controla o mundo real: navegador (Playwright), tela (mss), mouse/teclado (pyautogui)
e área de transferência (pyperclip). Aqui essas bibliotecas são trocadas por módulos falsos
ANTES de o código ser importado — a suíte roda sem internet, sem Fakturama, sem sessão
gráfica e sem mexer no computador de quem executa. Cada teste configura o dublê de que precisa.

Proteções automáticas (autouse): nenhum teste espera de verdade (time.sleep), grava na pasta
resultados/ real ou deixa os loggers do robô configurados para o teste seguinte.
"""
import logging
import sys
import time
import types
from unittest.mock import MagicMock

import pytest


def _instalar_dubles() -> None:
    """Registra módulos falsos no lugar das bibliotecas que tocam o mundo real."""
    mss_tools = types.ModuleType("mss.tools")
    mss = types.ModuleType("mss")
    mss.tools = mss_tools
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = MagicMock(name="sync_playwright")
    playwright = types.ModuleType("playwright")
    playwright.sync_api = sync_api
    for modulo in (types.ModuleType("pyautogui"), types.ModuleType("pyperclip"),
                   mss, mss_tools, playwright, sync_api):
        sys.modules.setdefault(modulo.__name__, modulo)


_instalar_dubles()

from config import settings  # noqa: E402  (importados depois dos dublês)
from src.core.contexto import Contexto  # noqa: E402
from src.core.evidencias import Evidencias  # noqa: E402
from src.models.entidades import Comprador, Produto  # noqa: E402

# Vitrine real do Sauce Demo: (nome, descrição, preço como exibido na página)
CATALOGO_SAUCEDEMO = [
    ("Sauce Labs Backpack",
     "carry.allTheThings() with the sleek, streamlined Sly Pack that melds uncompromising style "
     "with unequaled laptop and tablet protection.",
     "$29.99"),
    ("Sauce Labs Bike Light",
     "A red light isn't the desired state in testing but it sure helps when riding your bike at night. "
     "Water-resistant with 3 lighting modes, 1 AAA battery included.",
     "$9.99"),
    ("Sauce Labs Bolt T-Shirt",
     "Get your testing superhero on with the Sauce Labs bolt T-shirt. From American Apparel, "
     "100% ringspun combed cotton, heather gray with red bolt.",
     "$15.99"),
    ("Sauce Labs Fleece Jacket",
     "It's not every day that you come across a midweight quarter-zip fleece jacket capable of handling "
     "everything from a relaxing day outdoors to a busy day at the office.",
     "$49.99"),
    ("Sauce Labs Onesie",
     "Rib snap infant onesie for the junior automation engineer in development. Reinforced 3-snap bottom "
     "closure, two-needle hemmed sleeved and bottom won't unravel.",
     "$7.99"),
    ("Test.allTheThings() T-Shirt (Red)",
     "This classic Sauce Labs t-shirt is perfect to wear when cozying up to your keyboard to automate "
     "a few tests. Super-soft and comfy ringspun combed cotton.",
     "$15.99"),
]


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    """Troca time.sleep por um mock: retries e esperas da interface passam na hora."""
    espera = MagicMock(name="time.sleep")
    monkeypatch.setattr(time, "sleep", espera)
    return espera


@pytest.fixture(autouse=True)
def pasta_resultados(tmp_path, monkeypatch):
    """Redireciona settings.PASTA_RESULTADOS para uma pasta temporária."""
    pasta = tmp_path / "resultados"
    pasta.mkdir()
    monkeypatch.setattr(settings, "PASTA_RESULTADOS", pasta)
    return pasta


@pytest.fixture(autouse=True)
def _restaurar_loggers():
    """configurar_logs() altera loggers globais; devolve o estado original após cada teste."""
    yield
    for nome in ("rpa", "rpa.producer", "rpa.consumer"):
        logger = logging.getLogger(nome)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


@pytest.fixture
def ctx(pasta_resultados):
    """Contexto real (pastas, fila e evidências) dentro da pasta temporária."""
    return Contexto.criar("execucao_teste")


@pytest.fixture
def evidencias():
    """Evidências simuladas: registram os prints pedidos sem capturar nada."""
    return MagicMock(spec=Evidencias)


@pytest.fixture
def comprador():
    """Comprador como o gerador brasileiro devolve (CEP com hífen)."""
    return Comprador(nome="Vitória", sobrenome="Rocha", cep="14090-260")


@pytest.fixture
def catalogo_saucedemo():
    """Os 6 produtos da vitrine do Sauce Demo, como aparecem na página."""
    return list(CATALOGO_SAUCEDEMO)


@pytest.fixture
def produtos():
    """O catálogo acima depois de coletado: número sequencial e preço sem '$'."""
    return [Produto(numero=str(indice), nome=nome, descricao=descricao, preco=preco.lstrip("$"))
            for indice, (nome, descricao, preco) in enumerate(CATALOGO_SAUCEDEMO, start=1)]
