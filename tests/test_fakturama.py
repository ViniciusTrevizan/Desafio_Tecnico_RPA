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
from src.core import ambiente
from src.core.evidencias import Evidencias
from src.core.excecoes import ElementoNaoEncontrado, SystemException
from src.models.entidades import Produto


@pytest.fixture
def tela(monkeypatch, sem_espera):
    """Registra, em ordem, as ações no desktop, as esperas e os prints pedidos."""
    tela = MagicMock()
    tela.attach_mock(MagicMock(spec=Evidencias), "evidencias")
    tela.attach_mock(sem_espera, "espera")
    tela.desktop.ponto_de_clique.side_effect = lambda chave: (f"x:{chave}", f"y:{chave}")
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


def _preencher(*campos):
    """Localiza TODOS os campos antes de tocar no formulário; depois, por campo: UM clique → digita (sem TAB)."""
    rotulos = [rotulo for rotulo, _ in campos]
    return [*[call.desktop.ponto_de_clique(rotulo) for rotulo in rotulos],
            *[chamada for rotulo, valor in campos
              for chamada in (call.desktop.clicar(f"x:{rotulo}", f"y:{rotulo}"), call.desktop.digitar(valor))]]


def _salvar_com_print(nome_print):
    """Ctrl+S → espera → print do registro salvo → Ctrl+W."""
    return [call.desktop.atalho("ctrl", "s"),
            call.espera(settings.ESPERA_APOS_SALVAR),
            call.evidencias.tela(nome_print),
            call.desktop.atalho("ctrl", "w")]


class TestAbrir:
    @pytest.fixture(autouse=True)
    def windows(self, monkeypatch):
        """Comportamento padrão (Windows): usa FAKTURAMA_EXE / settings como está."""
        monkeypatch.setattr(ambiente, "SISTEMA", "Windows")

    @pytest.fixture
    def executavel(self, tmp_path, monkeypatch):
        executavel = tmp_path / "Fakturama"
        executavel.touch()
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(executavel))
        return executavel

    def test_reaproveita_o_fakturama_ja_aberto_trazendo_para_a_frente_maximizado(self, app, tela, popen):
        tela.desktop.maximizar_janela.return_value = True
        app.abrir()
        popen.assert_not_called()
        assert tela.mock_calls == [call.desktop.maximizar_janela(settings.FAKTURAMA_JANELA),
                                   call.desktop.localizar("app_pronto")]

    def test_inicia_o_executavel_aguarda_a_janela_principal_e_maximiza(self, app, tela, popen, executavel):
        tela.desktop.maximizar_janela.side_effect = [False, True]  # fechado → aberto pelo robô

        app.abrir()

        popen.assert_called_once_with([str(executavel)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert tela.mock_calls == [call.desktop.maximizar_janela(settings.FAKTURAMA_JANELA),
                                   call.desktop.localizar("app_pronto", timeout=settings.TIMEOUT_ABERTURA_APP),
                                   call.desktop.maximizar_janela(settings.FAKTURAMA_JANELA)]

    def test_janela_que_nao_maximiza_e_falha_tecnica(self, app, tela, popen, executavel):
        tela.desktop.maximizar_janela.return_value = False
        with pytest.raises(SystemException, match="não encontrada para maximizar"):
            app.abrir()

    def test_no_linux_abre_em_sessao_propria_sem_variaveis_do_snap(self, app, tela, popen, executavel, monkeypatch):
        monkeypatch.setattr(ambiente, "SISTEMA", "Linux")
        monkeypatch.setattr(ambiente, "executavel_fakturama", lambda: executavel)
        monkeypatch.setattr(ambiente, "variaveis_sem_snap", lambda: {"DISPLAY": ":0"})
        tela.desktop.maximizar_janela.side_effect = [False, True]

        app.abrir()

        popen.assert_called_once_with([str(executavel)], cwd=executavel.parent, start_new_session=True,
                                      env={"DISPLAY": ":0"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_executavel_ausente_e_falha_tecnica_com_orientacao(self, app, tela, popen, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(tmp_path / "nao_instalado"))
        tela.desktop.maximizar_janela.return_value = False
        with pytest.raises(SystemException, match=r"Executável do Fakturama não encontrado: .*\(defina FAKTURAMA_EXE\)"):
            app.abrir()
        popen.assert_not_called()


class TestPreencherFormulario:
    def test_um_clique_por_campo_e_digita_sem_tab(self, app, tela, caplog):
        app._preencher_formulario([("campo_contato_nome", "Vitória", "Nome"),
                                   ("campo_contato_cep", "14090-260", "CEP")])
        assert tela.mock_calls == _preencher(("campo_contato_nome", "Vitória"), ("campo_contato_cep", "14090-260"))
        assert call.desktop.tecla("tab") not in tela.mock_calls
        assert re.search(r"• CEP\s+← '14090-260'", caplog.text)

    def test_campo_nao_localizado_interrompe_antes_de_digitar_qualquer_coisa(self, app, tela):
        def ponto_de_clique(chave):
            if chave == "campo_contato_cep":
                raise ElementoNaoEncontrado("Imagem 'campo_contato_cep' não encontrada em 15s")
            return 1, 1
        tela.desktop.ponto_de_clique.side_effect = ponto_de_clique
        with pytest.raises(ElementoNaoEncontrado):
            app._preencher_formulario([("campo_contato_nome", "Vitória", "Nome"),
                                       ("campo_contato_cep", "14090-260", "CEP")])
        tela.desktop.clicar.assert_not_called()
        tela.desktop.digitar.assert_not_called()


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
            *_preencher(("campo_contato_nome", "Vitória"),
                        ("campo_contato_sobrenome", "Rocha"),
                        ("campo_contato_cep", "14090-260")),
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
            *_preencher(("campo_produto_numero", "1"),
                        ("campo_produto_nome", "Sauce Labs Backpack"),
                        ("campo_produto_descricao", mochila.descricao),
                        ("campo_produto_preco", "29,99")),
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
    usadas = {c.args[0] for c in tela.desktop.mock_calls if c[0] in ("existe", "localizar", "clicar_imagem", "ponto_de_clique")}
    assert usadas == set(settings.IMAGENS)
