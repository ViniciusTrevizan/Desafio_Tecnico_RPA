"""Testes de src/consumer/desktop.py — primitivas de automação desktop.

PDF §4.5: localizar os campos por reconhecimento de imagem e navegar entre eles com
atalhos de teclado.
"""
import sys
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
    def test_localizar_caixa_devolve_posicao_e_tamanho_em_coordenadas_da_tela(
            self, pyautogui_falso, imagem_referencia, tela, relogio):
        pyautogui_falso.locate.return_value = (100, 200, 40, 20)
        assert desktop.localizar_caixa("btn_novo_produto") == (100 - 1920, 200, 40, 20)

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
    def localizar_caixa(self, monkeypatch):
        # left, top, largura, altura → centro em (300, 400), borda direita em x=320
        monkeypatch.setattr(desktop, "localizar_caixa", MagicMock(return_value=(280, 390, 40, 20)))

    def test_clica_no_centro_da_imagem(self, pyautogui_falso):
        desktop.clicar_imagem("btn_novo_contato")
        pyautogui_falso.click.assert_called_once_with(300, 400)
        pyautogui_falso.doubleClick.assert_not_called()

    def test_desloca_o_clique_manualmente(self, pyautogui_falso):
        desktop.clicar_imagem("btn_novo_contato", offset_x=150, offset_y=-5)
        pyautogui_falso.click.assert_called_once_with(450, 395)

    def test_campo_clica_a_direita_do_rotulo_e_nao_nele(self, pyautogui_falso, monkeypatch):
        monkeypatch.setattr(settings, "OFFSET_CAMPO_X", 40)
        desktop.clicar_imagem("campo_contato_nome")
        pyautogui_falso.click.assert_called_once_with(320 + 40, 400)

    def test_clique_duplo(self, pyautogui_falso):
        desktop.clicar_imagem("nav_produtos", duplo=True)
        pyautogui_falso.doubleClick.assert_called_once_with(300, 400)
        pyautogui_falso.click.assert_not_called()

    def test_ponto_de_clique_de_campo_e_a_caixa_ao_lado_do_rotulo(self, pyautogui_falso, monkeypatch):
        monkeypatch.setattr(settings, "OFFSET_CAMPO_X", 40)
        assert desktop.ponto_de_clique("campo_produto_nome") == (320 + 40, 400)
        assert desktop.ponto_de_clique("btn_novo_produto") == (300, 400)
        pyautogui_falso.click.assert_not_called()  # só calcula, não clica


class TestClicar:
    def test_um_unico_clique_na_posicao(self, pyautogui_falso):
        desktop.clicar(360, 400)
        pyautogui_falso.click.assert_called_once_with(360, 400)
        pyautogui_falso.doubleClick.assert_not_called()


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


class TestMaximizarJanela:
    @pytest.mark.parametrize("sistema, funcao", [("Linux", "_maximizar_x11"), ("Windows", "_maximizar_windows")])
    def test_usa_o_mecanismo_do_sistema_e_espera_a_animacao(self, monkeypatch, relogio, sistema, funcao):
        monkeypatch.setattr(desktop.ambiente, "SISTEMA", sistema)
        maximizar = MagicMock(return_value=True)
        monkeypatch.setattr(desktop, funcao, maximizar)
        assert desktop.maximizar_janela("Fakturama") is True
        maximizar.assert_called_once_with("Fakturama")
        assert relogio.esperas == [settings.ESPERA_APOS_MAXIMIZAR]

    def test_janela_fechada_devolve_falso_sem_esperar(self, monkeypatch, relogio):
        monkeypatch.setattr(desktop.ambiente, "SISTEMA", "Linux")
        monkeypatch.setattr(desktop, "_maximizar_x11", MagicMock(return_value=False))
        assert desktop.maximizar_janela("Fakturama") is False
        assert relogio.esperas == []

    def test_windows_restaura_minimizada_maximiza_e_ativa(self, monkeypatch):
        janela = MagicMock(title="Fakturama - C:\\Fakturama", isMinimized=True)
        outra = MagicMock(title="Ajuda do Fakturama")  # título contém, mas não começa com "Fakturama"
        pygetwindow = SimpleNamespace(getWindowsWithTitle=lambda nome: [outra, janela],
                                      PyGetWindowException=Exception)
        monkeypatch.setitem(sys.modules, "pygetwindow", pygetwindow)
        assert desktop._maximizar_windows("Fakturama") is True
        janela.restore.assert_called_once_with()
        janela.maximize.assert_called_once_with()
        janela.activate.assert_called_once_with()
        outra.maximize.assert_not_called()

    def test_windows_sem_janela_devolve_falso(self, monkeypatch):
        pygetwindow = SimpleNamespace(getWindowsWithTitle=lambda nome: [], PyGetWindowException=Exception)
        monkeypatch.setitem(sys.modules, "pygetwindow", pygetwindow)
        assert desktop._maximizar_windows("Fakturama") is False
