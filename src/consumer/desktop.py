"""Primitivas de automação desktop: reconhecimento de imagem, mouse e teclado.

Requer sessão gráfica X11 (no Wayland o pyautogui não controla mouse/teclado).
"""
import time

import mss
import pyautogui
import pyperclip
from PIL import Image

from config import settings
from src.core.excecoes import ElementoNaoEncontrado, SystemException
from src.core.logger import get_logger

log = get_logger("consumer")

pyautogui.FAILSAFE = True  # mover o mouse para o canto superior esquerdo aborta o robô
pyautogui.PAUSE = settings.PAUSA_ENTRE_ACOES


def _capturar_tela() -> tuple[Image.Image, int, int]:
    """Retorna o print da área de trabalho e o deslocamento (left, top) dela."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        bruto = sct.grab(monitor)
        return Image.frombytes("RGB", bruto.size, bruto.rgb), monitor["left"], monitor["top"]


def localizar(chave: str, timeout: float | None = None) -> tuple[int, int]:
    """Procura a imagem de referência na tela até o timeout e devolve o centro (x, y)."""
    caminho = settings.PASTA_IMAGENS / settings.IMAGENS[chave]
    if not caminho.exists():
        raise SystemException(f"Imagem de referência ausente: assets/imagens/{caminho.name}")

    timeout = settings.TIMEOUT_IMAGEM if timeout is None else timeout
    limite = time.monotonic() + timeout
    while True:
        tela, esquerda, topo = _capturar_tela()
        try:
            caixa = pyautogui.locate(str(caminho), tela, confidence=settings.CONFIANCA_IMAGEM, grayscale=True)
        except pyautogui.ImageNotFoundException:
            caixa = None
        if caixa:
            x, y = pyautogui.center(caixa)
            log.debug(f"Imagem '{chave}' encontrada em ({x + esquerda}, {y + topo})", stacklevel=2)
            return int(x + esquerda), int(y + topo)
        if time.monotonic() >= limite:
            raise ElementoNaoEncontrado(f"Imagem '{chave}' não encontrada em {timeout}s")
        time.sleep(0.5)


def existe(chave: str, timeout: float = 2) -> bool:
    """True se a imagem aparecer na tela dentro do timeout."""
    try:
        localizar(chave, timeout)
        return True
    except ElementoNaoEncontrado:
        return False


def clicar_imagem(chave: str, offset_x: int = 0, offset_y: int = 0, duplo: bool = False) -> None:
    """Localiza a imagem e clica no centro dela (ou deslocado, ex.: campo ao lado do rótulo)."""
    x, y = localizar(chave)
    log.debug(f"Clique {'duplo ' if duplo else ''}em '{chave}' (+{offset_x},+{offset_y})", stacklevel=2)
    (pyautogui.doubleClick if duplo else pyautogui.click)(x + offset_x, y + offset_y)


def digitar(texto: str, limpar: bool = True) -> None:
    """Digita via área de transferência (suporta acentos), limpando o campo antes."""
    if limpar:
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("delete")
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")


def atalho(*teclas: str) -> None:
    """Executa um atalho de teclado, ex.: atalho('ctrl', 's')."""
    log.debug(f"Atalho: {'+'.join(teclas)}", stacklevel=2)
    pyautogui.hotkey(*teclas)


def tecla(nome: str, vezes: int = 1) -> None:
    """Pressiona uma tecla N vezes, ex.: tecla('tab', 2)."""
    pyautogui.press(nome, presses=vezes)
