"""Testes de src/models/entidades.py — validação de Comprador e Produto.

PDF §4.1: o comprador fake tem nome, sobrenome e CEP (gerador de identidades brasileiras).
PDF §4.3: cada produto do catálogo tem número, nome, descrição e preço.
"""
import pytest

from src.core.excecoes import BusinessException
from src.models.entidades import Comprador, Produto


class TestCompradorValidar:
    @pytest.mark.parametrize("cep", [
        pytest.param("14090-260", id="cep-com-hifen"),
        pytest.param("14090260", id="cep-sem-hifen"),
        pytest.param("12345", id="zip-eua-5-digitos"),
    ])
    def test_aceita_comprador_completo_e_devolve_ele_mesmo(self, cep):
        comprador = Comprador("Vitória", "Rocha", cep)
        assert comprador.validar() is comprador

    @pytest.mark.parametrize("nome, sobrenome", [("", "Rocha"), ("Vitória", ""), ("   ", "Rocha"), ("Vitória", "\t")])
    def test_rejeita_nome_ou_sobrenome_em_branco(self, nome, sobrenome):
        with pytest.raises(BusinessException, match="sem nome/sobrenome"):
            Comprador(nome, sobrenome, "14090-260").validar()

    @pytest.mark.parametrize("cep", ["", "1409-026", "140902601", "CEP-ABC"])
    def test_rejeita_cep_sem_8_digitos_br_ou_5_eua(self, cep):
        with pytest.raises(BusinessException, match="CEP inválido"):
            Comprador("Vitória", "Rocha", cep).validar()


class TestProdutoValidar:
    @pytest.mark.parametrize("preco", ["29.99", "7.99", "100"])
    def test_aceita_produto_com_preco_positivo_e_devolve_ele_mesmo(self, preco):
        produto = Produto("1", "Sauce Labs Backpack", "carry.allTheThings()", preco)
        assert produto.validar() is produto

    @pytest.mark.parametrize("nome", ["", "   "])
    def test_rejeita_produto_sem_nome(self, nome):
        with pytest.raises(BusinessException, match="Produto 1 sem nome"):
            Produto("1", nome, "descrição", "29.99").validar()

    # O CSV guarda o preço com ponto decimal e sem "$" (a raspagem remove o símbolo)
    @pytest.mark.parametrize("preco", [
        pytest.param("0", id="zero"),
        pytest.param("-5.00", id="negativo"),
        pytest.param("abc", id="texto"),
        pytest.param("", id="vazio"),
        pytest.param("$29.99", id="com-cifrao"),
        pytest.param("29,99", id="virgula-decimal"),
    ])
    def test_rejeita_preco_nao_numerico_ou_nao_positivo(self, preco):
        with pytest.raises(BusinessException, match="Preço inválido no produto 'Sauce Labs Backpack'"):
            Produto("1", "Sauce Labs Backpack", "descrição", preco).validar()
