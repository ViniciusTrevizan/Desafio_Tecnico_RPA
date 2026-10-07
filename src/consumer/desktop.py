"""Primitivas de automação desktop: reconhecimento de imagem, janelas, mouse e teclado.

Requer sessão gráfica X11 (no Wayland o pyautogui não controla mouse/teclado).
"""
import time

import mss
import pyautogui
import pyperclip
from PIL import Image

from config import settings
from src.core import ambiente
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
    esquerda, topo, largura, altura = localizar_caixa(chave, timeout)
    return esquerda + largura // 2, topo + altura // 2


def localizar_caixa(chave: str, timeout: float | None = None) -> tuple[int, int, int, int]:
    """Procura a imagem de referência na tela até o timeout e devolve (left, top, width, height)."""
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
            x, y, largura, altura = (int(v) for v in caixa)
            x, y = x + esquerda, y + topo
            log.debug(f"Imagem '{chave}' encontrada em ({x}, {y}) {largura}x{altura}", stacklevel=3)
            return x, y, largura, altura
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


def ponto_de_clique(chave: str) -> tuple[int, int]:
    """Onde clicar na imagem: o centro dela ou, para rótulos "campo_*", a caixa de texto ao lado.

    Imagens "campo_*" são rótulos: o clique vai OFFSET_CAMPO_X px à direita da
    borda direita do rótulo, dentro da caixa de texto, e não no rótulo em si.
    """
    esquerda, topo, largura, altura = localizar_caixa(chave)
    y = topo + altura // 2
    if chave.startswith("campo_"):
        return esquerda + largura + settings.OFFSET_CAMPO_X, y
    return esquerda + largura // 2, y


def clicar(x: int, y: int, duplo: bool = False) -> None:
    """Clica (uma vez, ou duas se duplo=True) na posição de tela informada."""
    log.debug(f"Clique {'duplo ' if duplo else ''}em ({x}, {y})", stacklevel=2)
    (pyautogui.doubleClick if duplo else pyautogui.click)(x, y)


def clicar_imagem(chave: str, offset_x: int = 0, offset_y: int = 0, duplo: bool = False) -> None:
    """Localiza a imagem e clica no ponto_de_clique dela (deslocado por offset_x/offset_y)."""
    x, y = ponto_de_clique(chave)
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


def maximizar_janela(nome: str) -> bool:
    """Traz a janela do aplicativo para a frente e maximiza; False se ela não estiver aberta."""
    maximizou = _maximizar_x11(nome) if ambiente.eh_linux() else _maximizar_windows(nome)
    if maximizou:
        log.debug(f"Janela '{nome}' ativada e maximizada", stacklevel=2)
        time.sleep(settings.ESPERA_APOS_MAXIMIZAR)  # animação do gerenciador de janelas
    return maximizou


def _maximizar_x11(nome: str) -> bool:
    """Pede ao gerenciador de janelas (EWMH) para ativar e maximizar a janela de classe/título `nome`."""
    from Xlib import X, display, error, protocol  # só existe/é usado no Linux

    tela = display.Display()
    try:
        raiz = tela.screen().root
        atomo = tela.intern_atom
        lista = raiz.get_full_property(atomo("_NET_CLIENT_LIST"), X.AnyPropertyType)
        janela = None
        for id_janela in lista.value if lista else []:
            candidata = tela.create_resource_object("window", id_janela)
            try:
                classe = (candidata.get_wm_class() or ("", ""))[1]
                titulo = candidata.get_full_property(atomo("_NET_WM_NAME"), 0)
            except error.XError:  # janela fechou durante a varredura
                continue
            if classe == nome and titulo and titulo.value.decode(errors="ignore").startswith(nome):
                janela = candidata  # ignora splash/diálogos: só a janela principal tem o título "Fakturama - ..."
                break
        if janela is None:
            return False

        def enviar(tipo: str, dados: list[int]) -> None:
            evento = protocol.event.ClientMessage(window=janela, client_type=atomo(tipo),
                                                  data=(32, dados + [0] * (5 - len(dados))))
            raiz.send_event(evento, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

        enviar("_NET_ACTIVE_WINDOW", [1, X.CurrentTime])
        enviar("_NET_WM_STATE", [1, atomo("_NET_WM_STATE_MAXIMIZED_VERT"), atomo("_NET_WM_STATE_MAXIMIZED_HORZ"), 1])
        tela.sync()
        return True
    finally:
        tela.close()


def _maximizar_windows(nome: str) -> bool:
    """Ativa e maximiza a primeira janela cujo título começa com `nome`."""
    import pygetwindow  # dependência do pyautogui; não funciona no Linux

    janelas = [j for j in pygetwindow.getWindowsWithTitle(nome) if j.title.startswith(nome)]
    if not janelas:
        return False
    janela = janelas[0]
    if janela.isMinimized:
        janela.restore()
    janela.maximize()
    try:
        janela.activate()
    except pygetwindow.PyGetWindowException:  # o Windows às vezes recusa o foco; maximizada já basta
        pass
    return True
