"""Testes de src/consumer/fakturama.py — ações de negócio no Fakturama.

PDF §4.5: cadastrar o comprador como novo contato, localizando os campos por imagem e
navegando com atalhos de teclado. PDF §4.6: cadastrar cada produto como novo item com a
mesma técnica. PDF §4.7/§5: prints do contato salvo e da lista de produtos.
"""
import re
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from config import settings
from src.consumer import fakturama
from src.consumer.fakturama import Fakturama
from src.core.evidencias import Evidencias
from src.core.excecoes import ElementoNaoEncontrado, SystemException
from src.models.entidades import Produto


@pytest.fixture
def tela(monkeypatch, sem_espera):
    """Registra, em ordem, as ações no desktop, as esperas e os prints pedidos."""
    tela = MagicMock()
    tela.attach_mock(MagicMock(spec=Evidencias), "evidencias")
    tela.attach_mock(sem_espera, "espera")
    monkeypatch.setattr(fakturama, "desktop", tela.desktop)
    return tela


@pytest.fixture
def app(tela):
    return Fakturama(tela.evidencias)


@pytest.fixture
def popen(monkeypatch):
    popen = MagicMock(name="Popen")
    monkeypatch.setattr(fakturama, "subprocess", SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL))
    return popen


def _preencher(rotulo, valor):
    """Clique ao lado do rótulo (imagem) → digita o valor → TAB."""
    return [call.desktop.clicar_imagem(rotulo, offset_x=settings.OFFSET_CAMPO_X),
            call.desktop.digitar(valor),
            call.desktop.tecla("tab")]


def _salvar_com_print(nome_print):
    """Ctrl+S → espera → print do registro salvo → Ctrl+W."""
    return [call.desktop.atalho("ctrl", "s"),
            call.espera(settings.ESPERA_APOS_SALVAR),
            call.evidencias.tela(nome_print),
            call.desktop.atalho("ctrl", "w")]


class TestAbrir:
    def test_reaproveita_o_fakturama_ja_aberto(self, app, tela, popen):
        tela.desktop.existe.return_value = True
        app.abrir()
        popen.assert_not_called()
        assert tela.mock_calls == [call.desktop.existe("app_pronto")]

    def test_inicia_o_executavel_e_aguarda_a_janela_principal(self, app, tela, popen, tmp_path, monkeypatch):
        executavel = tmp_path / "Fakturama"
        executavel.touch()
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(executavel))
        tela.desktop.existe.return_value = False

        app.abrir()

        popen.assert_called_once_with([str(executavel)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tela.desktop.localizar.assert_called_once_with("app_pronto", timeout=settings.TIMEOUT_ABERTURA_APP)

    def test_executavel_ausente_e_falha_tecnica_com_orientacao(self, app, tela, popen, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(tmp_path / "nao_instalado"))
        tela.desktop.existe.return_value = False
        with pytest.raises(SystemException, match=r"Executável do Fakturama não encontrado: .*\(defina FAKTURAMA_EXE\)"):
            app.abrir()
        popen.assert_not_called()


class TestPreencher:
    def test_clica_ao_lado_do_rotulo_digita_e_confirma_com_tab(self, app, tela, caplog):
        app._preencher("campo_contato_cep", "14090-260", "CEP")
        assert tela.mock_calls == _preencher("campo_contato_cep", "14090-260")
        assert re.search(r"• CEP\s+← '14090-260'", caplog.text)


class TestSalvarEFecharEditor:
    def test_salva_espera_tira_o_print_e_so_entao_fecha_o_editor(self, app, tela):
        app._salvar_e_fechar_editor("contato_cadastrado")
        assert tela.mock_calls == _salvar_com_print("contato_cadastrado")


class TestCadastrarContato:
    def test_cadastra_nome_sobrenome_e_cep_do_comprador_e_tira_print(self, app, tela, comprador):
        app.cadastrar_contato(comprador)
        assert tela.mock_calls == [
            call.desktop.clicar_imagem("btn_novo_contato"),
            call.desktop.localizar("campo_contato_nome"),  # o editor abriu
            *_preencher("campo_contato_nome", "Vitória"),
            *_preencher("campo_contato_sobrenome", "Rocha"),
            *_preencher("campo_contato_cep", "14090-260"),
            *_salvar_com_print("contato_cadastrado"),
        ]

    def test_editor_que_nao_abre_interrompe_sem_salvar(self, app, tela, comprador):
        tela.desktop.localizar.side_effect = ElementoNaoEncontrado("Imagem 'campo_contato_nome' não encontrada em 15s")
        with pytest.raises(ElementoNaoEncontrado):
            app.cadastrar_contato(comprador)
        assert call.desktop.atalho("ctrl", "s") not in tela.mock_calls


class TestCadastrarProduto:
    def test_cadastra_numero_nome_descricao_e_preco_e_tira_print(self, app, tela, produtos):
        mochila = produtos[0]
        app.cadastrar_produto(mochila)
        assert tela.mock_calls == [
            call.desktop.clicar_imagem("btn_novo_produto"),
            call.desktop.localizar("campo_produto_numero"),  # o editor abriu
            *_preencher("campo_produto_numero", "1"),
            *_preencher("campo_produto_nome", "Sauce Labs Backpack"),
            *_preencher("campo_produto_descricao", mochila.descricao),
            *_preencher("campo_produto_preco", "29,99"),
            *_salvar_com_print("produto_1_cadastrado"),
        ]
        assert mochila.preco == "29.99"  # o dado original (o mesmo do CSV) não é alterado

    @pytest.mark.parametrize("preco, digitado", [("9.99", "9,99"), ("49.99", "49,99"), ("100", "100")])
    def test_preco_e_digitado_com_virgula_decimal_do_fakturama_pt_br(self, app, tela, preco, digitado):
        app.cadastrar_produto(Produto("2", "Sauce Labs Bike Light", "A red light...", preco))
        assert call.desktop.digitar(digitado) in tela.mock_calls


class TestEvidenciarLista:
    @pytest.mark.parametrize("tipo", ["contatos", "produtos"])
    def test_abre_a_lista_pelo_menu_lateral_e_tira_o_print(self, app, tela, tipo):
        tela.evidencias.tela.return_value = f"prints/09_lista_{tipo}.png"
        assert app.evidenciar_lista(tipo) == f"prints/09_lista_{tipo}.png"
        assert tela.mock_calls == [
            call.desktop.clicar_imagem(f"nav_{tipo}"),
            call.espera(settings.ESPERA_APOS_SALVAR),
            call.evidencias.tela(f"lista_{tipo}"),
        ]


class TestRecuperar:
    def test_fecha_dialogos_e_editores_com_esc(self, app, tela, caplog):
        app.recuperar()
        assert tela.mock_calls == [call.desktop.tecla("esc", 2)]
        assert "Recuperando estado da aplicação (ESC x2)" in caplog.text


def test_cada_imagem_usada_no_cadastro_tem_recorte_mapeado_em_settings(app, tela, comprador, produtos):
    """Uma chave sem entrada em settings.IMAGENS só quebraria no meio do cadastro desktop."""
    tela.desktop.existe.return_value = True
    app.abrir()
    app.cadastrar_contato(comprador)
    app.cadastrar_produto(produtos[0])
    app.evidenciar_lista("contatos")
    app.evidenciar_lista("produtos")
    usadas = {c.args[0] for c in tela.desktop.mock_calls if c[0] in ("existe", "localizar", "clicar_imagem")}
    assert usadas == set(settings.IMAGENS)
