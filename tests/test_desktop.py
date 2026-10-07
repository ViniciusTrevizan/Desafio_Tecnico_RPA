"""Testes de src/consumer/desktop.py — primitivas de automação desktop.

PDF §4.5: localizar os campos por reconhecimento de imagem e navegar entre eles com
atalhos de teclado.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from PIL import Image

from config import settings
from src.consumer import desktop
from src.core.excecoes import ElementoNaoEncontrado, SystemException


class ImagemNaoEncontrada(Exception):
    """Equivalente a pyautogui.ImageNotFoundException."""


class RelogioFalso:
    """Substitui o módulo time de desktop.py: sleep() avança o relógio sem esperar de verdade."""

    def __init__(self):
        self.agora = 0.0
        self.esperas = []

    def monotonic(self):
        return self.agora

    def sleep(self, segundos):
        self.esperas.append(segundos)
        self.agora += segundos


@pytest.fixture
def pyautogui_falso(monkeypatch):
    falso = MagicMock(name="pyautogui")
    falso.ImageNotFoundException = ImagemNaoEncontrada
    falso.center.side_effect = lambda caixa: (caixa[0] + caixa[2] // 2, caixa[1] + caixa[3] // 2)
    monkeypatch.setattr(desktop, "pyautogui", falso)
    return falso


@pytest.fixture
def pyperclip_falso(monkeypatch):
    falso = MagicMock(name="pyperclip")
    monkeypatch.setattr(desktop, "pyperclip", falso)
    return falso


@pytest.fixture
def relogio(monkeypatch):
    relogio = RelogioFalso()
    monkeypatch.setattr(desktop, "time", relogio)
    return relogio


@pytest.fixture
def imagem_referencia(tmp_path, monkeypatch):
    """Recorte PNG de 'btn_novo_produto' numa pasta de imagens temporária."""
    monkeypatch.setattr(settings, "PASTA_IMAGENS", tmp_path)
    caminho = tmp_path / settings.IMAGENS["btn_novo_produto"]
    Image.new("RGB", (10, 10)).save(caminho)
    return caminho


@pytest.fixture
def tela(monkeypatch):
    """Print simulado da área de trabalho, que começa em x=-1920 (monitor extra à esquerda)."""
    imagem = Image.new("RGB", (3840, 1080))
    monkeypatch.setattr(desktop, "_capturar_tela", lambda: (imagem, -1920, 0))
    return imagem


def test_modulo_ativa_failsafe_e_pausa_entre_acoes():
    """README: mover o mouse para o canto superior esquerdo aborta o robô."""
    assert desktop.pyautogui.FAILSAFE is True
    assert desktop.pyautogui.PAUSE == settings.PAUSA_ENTRE_ACOES


class TestCapturarTela:
    def test_captura_todos_os_monitores_e_devolve_imagem_e_deslocamento(self, monkeypatch):
        area_de_trabalho = {"left": -1920, "top": 0, "width": 2, "height": 1}
        sct = MagicMock(name="sct")
        sct.__enter__.return_value = sct
        sct.monitors = [area_de_trabalho, {"left": 0, "top": 0, "width": 1, "height": 1}]
        sct.grab.return_value = SimpleNamespace(size=(2, 1), rgb=bytes([255, 0, 0, 0, 0, 255]))
        monkeypatch.setattr(desktop, "mss", SimpleNamespace(mss=lambda: sct))

        imagem, esquerda, topo = desktop._capturar_tela()

        sct.grab.assert_called_once_with(area_de_trabalho)
        assert (imagem.mode, imagem.size) == ("RGB", (2, 1))
        assert [imagem.getpixel((0, 0)), imagem.getpixel((1, 0))] == [(255, 0, 0), (0, 0, 255)]
        assert (esquerda, topo) == (-1920, 0)


class TestLocalizar:
    def test_reconhece_a_imagem_e_devolve_o_centro_em_coordenadas_da_tela(
            self, pyautogui_falso, imagem_referencia, tela, relogio):
        pyautogui_falso.locate.return_value = (100, 200, 40, 20)  # left, top, largura, altura
        assert desktop.localizar("btn_novo_produto") == (120 - 1920, 210)
        pyautogui_falso.locate.assert_called_once_with(
            str(imagem_referencia), tela, confidence=settings.CONFIANCA_IMAGEM, grayscale=True)
        assert relogio.esperas == []

    def test_procura_de_novo_ate_a_imagem_aparecer(self, pyautogui_falso, imagem_referencia, tela, relogio):
        pyautogui_falso.locate.side_effect = [ImagemNaoEncontrada(), None, (0, 0, 10, 10)]
        assert desktop.localizar("btn_novo_produto", timeout=5) == (5 - 1920, 5)
        assert pyautogui_falso.locate.call_count == 3
        assert relogio.esperas == [0.5, 0.5]

    def test_estoura_o_timeout_com_elemento_nao_encontrado(self, pyautogui_falso, imagem_referencia, tela, relogio):
        pyautogui_falso.locate.side_effect = ImagemNaoEncontrada()
        with pytest.raises(ElementoNaoEncontrado, match="Imagem 'btn_novo_produto' não encontrada em 2s"):
            desktop.localizar("btn_novo_produto", timeout=2)
        assert relogio.agora == 2
        assert pyautogui_falso.locate.call_count == 5  # t = 0 / 0,5 / 1 / 1,5 / 2

    def test_timeout_padrao_vem_de_settings(self, pyautogui_falso, imagem_referencia, tela, relogio, monkeypatch):
        monkeypatch.setattr(settings, "TIMEOUT_IMAGEM", 1)
        pyautogui_falso.locate.return_value = None
        with pytest.raises(ElementoNaoEncontrado, match="não encontrada em 1s"):
            desktop.localizar("btn_novo_produto")

    def test_recorte_de_referencia_ausente_e_erro_de_configuracao(self, pyautogui_falso, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "PASTA_IMAGENS", tmp_path)
        with pytest.raises(SystemException, match="Imagem de referência ausente: assets/imagens/btn_novo_produto.png") as erro:
            desktop.localizar("btn_novo_produto")
        assert not isinstance(erro.value, ElementoNaoEncontrado)
        pyautogui_falso.locate.assert_not_called()


class TestExiste:
    def test_verdadeiro_quando_a_imagem_aparece_no_timeout(self, monkeypatch):
        localizar = MagicMock(return_value=(10, 10))
        monkeypatch.setattr(desktop, "localizar", localizar)
        assert desktop.existe("app_pronto") is True
        localizar.assert_called_once_with("app_pronto", 2)

    def test_falso_quando_a_imagem_nao_aparece(self, monkeypatch):
        monkeypatch.setattr(desktop, "localizar", MagicMock(side_effect=ElementoNaoEncontrado("não encontrada")))
        assert desktop.existe("app_pronto", timeout=0.1) is False

    def test_nao_esconde_erro_de_configuracao(self, monkeypatch):
        monkeypatch.setattr(desktop, "localizar", MagicMock(side_effect=SystemException("Imagem de referência ausente")))
        with pytest.raises(SystemException, match="Imagem de referência ausente"):
            desktop.existe("app_pronto")


class TestClicarImagem:
    @pytest.fixture(autouse=True)
    def localizar(self, monkeypatch):
        monkeypatch.setattr(desktop, "localizar", MagicMock(return_value=(300, 400)))

    def test_clica_no_centro_da_imagem(self, pyautogui_falso):
        desktop.clicar_imagem("btn_novo_contato")
        pyautogui_falso.click.assert_called_once_with(300, 400)
        pyautogui_falso.doubleClick.assert_not_called()

    def test_desloca_o_clique_para_o_campo_ao_lado_do_rotulo(self, pyautogui_falso):
        desktop.clicar_imagem("campo_contato_nome", offset_x=150, offset_y=-5)
        pyautogui_falso.click.assert_called_once_with(450, 395)

    def test_clique_duplo(self, pyautogui_falso):
        desktop.clicar_imagem("nav_produtos", duplo=True)
        pyautogui_falso.doubleClick.assert_called_once_with(300, 400)
        pyautogui_falso.click.assert_not_called()


class TestDigitar:
    def test_limpa_o_campo_e_cola_o_texto_com_acentos(self, pyautogui_falso, pyperclip_falso):
        ordem = MagicMock()
        ordem.attach_mock(pyautogui_falso, "pyautogui")
        ordem.attach_mock(pyperclip_falso, "pyperclip")
        desktop.digitar("Conceição")
        assert ordem.mock_calls == [
            call.pyautogui.hotkey("ctrl", "a"),
            call.pyautogui.press("delete"),
            call.pyperclip.copy("Conceição"),
            call.pyautogui.hotkey("ctrl", "v"),
        ]

    def test_sem_limpar_apenas_cola(self, pyautogui_falso, pyperclip_falso):
        desktop.digitar("29,99", limpar=False)
        pyperclip_falso.copy.assert_called_once_with("29,99")
        pyautogui_falso.hotkey.assert_called_once_with("ctrl", "v")
        pyautogui_falso.press.assert_not_called()


class TestAtalho:
    def test_dispara_a_combinacao_de_teclas(self, pyautogui_falso):
        desktop.atalho("ctrl", "s")
        pyautogui_falso.hotkey.assert_called_once_with("ctrl", "s")


class TestTecla:
    def test_pressiona_uma_vez_por_padrao(self, pyautogui_falso):
        desktop.tecla("tab")
        pyautogui_falso.press.assert_called_once_with("tab", presses=1)

    def test_pressiona_n_vezes(self, pyautogui_falso):
        desktop.tecla("esc", 2)
        pyautogui_falso.press.assert_called_once_with("esc", presses=2)
