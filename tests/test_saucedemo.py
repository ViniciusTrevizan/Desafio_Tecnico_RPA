"""Testes de src/producer/saucedemo.py — login e raspagem do catálogo.

PDF §3: usar as credenciais de teste documentadas na própria página de login.
PDF §4.2: autenticar preenchendo o formulário de login via automação web.
PDF §4.3: extrair número, nome, descrição e preço de TODOS os produtos — nenhum sorteio
ou seleção parcial.
"""
import re
from unittest.mock import MagicMock

import pytest

from config import settings
from src.core.excecoes import BusinessException, SystemException
from src.models.entidades import Produto
from src.producer.saucedemo import coletar_catalogo, login, obter_credenciais

USUARIOS = ["standard_user", "locked_out_user", "problem_user", "performance_glitch_user", "error_user", "visual_user"]
URL_INVENTARIO = "https://www.saucedemo.com/inventory.html"


class _Localizador:
    """Imita o Locator do Playwright sobre uma lista de elementos."""

    def __init__(self, elementos):
        self._elementos = list(elementos)

    def count(self):
        return len(self._elementos)

    def nth(self, indice):
        return self._elementos[indice]

    def inner_text(self):
        return self._elementos[0]


class _ItemVitrine:
    def __init__(self, nome, descricao, preco):
        self._textos = {".inventory_item_name": nome, ".inventory_item_desc": descricao, ".inventory_item_price": preco}

    def locator(self, seletor):
        return _Localizador([self._textos[seletor]])


class PaginaSauceDemo:
    """Dublê do Sauce Demo com o comportamento que importa ao robô.

    - a tela de login exibe os usuários aceitos e a senha de teste;
    - o formulário de login só existe fora do inventário, como no site real;
    - usuário bloqueado ou senha errada exibem a mensagem de erro do site;
    - falhas técnicas podem ser injetadas na navegação e no carregamento do inventário.
    """

    def __init__(self, catalogo=(), usuarios=USUARIOS, senha="secret_sauce", falhas_navegacao=0, inventario_lento=0):
        self.url = "about:blank"
        self.catalogo = list(catalogo)
        self.usuarios = list(usuarios)
        self.senha = senha
        self.falhas_navegacao = falhas_navegacao
        self.inventario_lento = inventario_lento
        self.formulario = {}
        self.erro = ""
        self.cliques = 0

    def goto(self, url, wait_until=None):
        if self.falhas_navegacao:
            self.falhas_navegacao -= 1
            raise TimeoutError(f"Timeout ao abrir {url}")
        self.url, self.formulario, self.erro = url, {}, ""

    def inner_text(self, seletor):
        return {
            "#login_credentials": "Accepted usernames are:\n" + "\n".join(self.usuarios),
            ".login_password": f"Password for all users:\n{self.senha}",
        }[seletor]

    def fill(self, seletor, valor):
        if "inventory" in self.url:
            raise TimeoutError(f"Timeout esperando '{seletor}': não há formulário de login no inventário")
        self.formulario[seletor] = valor

    def click(self, seletor):
        self.cliques += 1
        usuario, senha = self.formulario.get("#user-name"), self.formulario.get("#password")
        if usuario == "locked_out_user":
            self.erro = "Epic sadface: Sorry, this user has been locked out."
        elif usuario not in self.usuarios or senha != self.senha:
            self.erro = "Epic sadface: Username and password do not match any user in this service"
        else:
            self.url = URL_INVENTARIO

    def locator(self, seletor):
        if seletor == '[data-test="error"]':
            return _Localizador([self.erro] if self.erro else [])
        if seletor == ".inventory_item":
            return _Localizador(_ItemVitrine(*produto) for produto in self.catalogo)
        raise AssertionError(f"Seletor inesperado: {seletor}")

    def wait_for_selector(self, seletor):
        if self.inventario_lento:
            self.inventario_lento -= 1
            raise TimeoutError(f"Timeout esperando '{seletor}'")


class TestObterCredenciais:
    def test_le_usuario_e_senha_exibidos_na_propria_pagina_de_login(self):
        page = PaginaSauceDemo()
        assert obter_credenciais(page) == ("standard_user", "secret_sauce")
        assert page.url == settings.URL_SAUCEDEMO

    def test_credenciais_nao_estao_fixas_no_codigo(self):
        page = PaginaSauceDemo(usuarios=["visual_user", "standard_user"], senha="senha_publicada_hoje")
        assert obter_credenciais(page) == ("standard_user", "senha_publicada_hoje")

    def test_sem_standard_user_usa_o_primeiro_usuario_listado(self):
        assert obter_credenciais(PaginaSauceDemo(usuarios=["problem_user", "visual_user"]))[0] == "problem_user"

    @pytest.mark.parametrize("texto_usuarios, texto_senha", [
        pytest.param("Accepted usernames are:", "Password for all users:\nsecret_sauce", id="sem-usuarios"),
        pytest.param("Accepted usernames are:\nstandard_user", "Password for all users:", id="sem-senha"),
        pytest.param("", "", id="blocos-vazios"),
    ])
    def test_credenciais_ausentes_na_pagina_sao_falha_tecnica(self, texto_usuarios, texto_senha):
        page = MagicMock(name="page")
        page.inner_text.side_effect = {"#login_credentials": texto_usuarios, ".login_password": texto_senha}.__getitem__
        with pytest.raises(SystemException, match="Credenciais de teste não encontradas"):
            obter_credenciais(page)


class TestLogin:
    def test_preenche_usuario_e_senha_clica_e_chega_ao_inventario(self, evidencias, caplog):
        page = PaginaSauceDemo()
        login(page, "standard_user", "secret_sauce", evidencias)
        assert page.formulario == {"#user-name": "standard_user", "#password": "secret_sauce"}
        assert (page.cliques, page.url) == (1, URL_INVENTARIO)
        assert "Login realizado — página de inventário carregada" in caplog.text
        evidencias.erro.assert_not_called()

    @pytest.mark.parametrize("usuario, senha, mensagem", [
        ("locked_out_user", "secret_sauce", "Sorry, this user has been locked out."),
        ("standard_user", "senha_errada", "Username and password do not match"),
    ])
    def test_login_recusado_e_falha_de_negocio_sem_nova_tentativa(self, evidencias, sem_espera, usuario, senha, mensagem):
        page = PaginaSauceDemo()
        with pytest.raises(BusinessException, match=f"Login recusado: Epic sadface: {re.escape(mensagem)}"):
            login(page, usuario, senha, evidencias)
        assert page.cliques == 1
        sem_espera.assert_not_called()
        evidencias.erro.assert_called_once_with("login", page)

    def test_falha_tecnica_na_navegacao_e_repetida(self, evidencias, sem_espera):
        page = PaginaSauceDemo(falhas_navegacao=1)
        login(page, "standard_user", "secret_sauce", evidencias)
        assert page.url == URL_INVENTARIO
        assert sem_espera.call_count == 1

    def test_nova_tentativa_funciona_mesmo_se_a_anterior_ja_autenticou(self, evidencias):
        """O clique autenticou, mas o inventário estourou o timeout. A nova tentativa não pode
        depender do formulário de login: ele não existe mais na página de inventário."""
        page = PaginaSauceDemo(inventario_lento=1)
        login(page, "standard_user", "secret_sauce", evidencias)
        assert page.url == URL_INVENTARIO


class TestColetarCatalogo:
    def test_coleta_todos_os_produtos_da_vitrine_na_ordem(self, catalogo_saucedemo, produtos, evidencias):
        assert coletar_catalogo(PaginaSauceDemo(catalogo=catalogo_saucedemo), evidencias) == produtos

    def test_numero_e_sequencial_e_preco_vem_sem_cifrao(self, catalogo_saucedemo, evidencias):
        coletados = coletar_catalogo(PaginaSauceDemo(catalogo=catalogo_saucedemo), evidencias)
        assert [p.numero for p in coletados] == ["1", "2", "3", "4", "5", "6"]
        assert [p.preco for p in coletados] == ["29.99", "9.99", "15.99", "49.99", "7.99", "15.99"]

    def test_remove_espacos_em_volta_dos_textos(self, evidencias):
        page = PaginaSauceDemo(catalogo=[("  Sauce Labs Onesie \n", "\tRib snap infant onesie. ", " $7.99 ")])
        assert coletar_catalogo(page, evidencias) == [Produto("1", "Sauce Labs Onesie", "Rib snap infant onesie.", "7.99")]

    def test_registra_no_log_cada_produto_coletado(self, catalogo_saucedemo, evidencias, caplog):
        coletar_catalogo(PaginaSauceDemo(catalogo=catalogo_saucedemo), evidencias)
        assert "6 produtos encontrados na vitrine" in caplog.text
        assert "[1/6] Coletado: #1 'Sauce Labs Backpack' — $ 29.99" in caplog.text
        assert "[6/6] Coletado: #6 'Test.allTheThings() T-Shirt (Red)' — $ 15.99" in caplog.text

    def test_tira_print_da_vitrine_completa(self, catalogo_saucedemo, evidencias):
        page = PaginaSauceDemo(catalogo=catalogo_saucedemo)
        coletar_catalogo(page, evidencias)
        evidencias.navegador.assert_called_once_with(page, "saucedemo_catalogo")

    def test_vitrine_vazia_e_falha_tecnica(self, evidencias):
        with pytest.raises(SystemException, match="Nenhum produto encontrado na vitrine"):
            coletar_catalogo(PaginaSauceDemo(catalogo=[]), evidencias)

    def test_produto_ilegivel_interrompe_a_coleta_em_vez_de_sumir_do_catalogo(self, catalogo_saucedemo, evidencias):
        """Sem seleção parcial: um produto com preço inválido não pode ser descartado em silêncio."""
        catalogo_saucedemo[2] = ("Sauce Labs Bolt T-Shirt", "Get your testing superhero on...", "Sold out")
        with pytest.raises(BusinessException, match="Preço inválido no produto 'Sauce Labs Bolt T-Shirt'"):
            coletar_catalogo(PaginaSauceDemo(catalogo=catalogo_saucedemo), evidencias)
        evidencias.navegador.assert_not_called()
