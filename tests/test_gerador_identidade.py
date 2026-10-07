"""Testes de src/producer/gerador_identidade.py.

PDF §4.1: acessar o gerador de identidades (fakenamegenerator.com, identidade brasileira)
e extrair nome, sobrenome e CEP via raspagem de dados.
"""
from unittest.mock import MagicMock

import pytest

from config import settings
from src.core.excecoes import BusinessException, SystemException
from src.models.entidades import Comprador
from src.producer import gerador_identidade
from src.producer.gerador_identidade import SELETOR_ENDERECO, SELETOR_NOME, _raspar_fakenamegenerator, gerar_comprador

ENDERECO_BR = "Rua Barão de Itapetininga, 1245\nRibeirão Preto-SP\n14090-260"  # rua / cidade-UF / CEP


def _pagina(nome="Vitória Cunha Rocha", endereco=ENDERECO_BR):
    """Página do gerador simulada: devolve os textos dos seletores de nome e endereço."""
    page = MagicMock(name="page")
    page.inner_text.side_effect = {SELETOR_NOME: nome, SELETOR_ENDERECO: endereco}.__getitem__
    return page


class TestRasparFakenamegenerator:
    def test_extrai_nome_sobrenome_e_cep_do_gerador_brasileiro(self, evidencias):
        page = _pagina()
        assert _raspar_fakenamegenerator(page, evidencias) == Comprador("Vitória", "Rocha", "14090-260")
        page.goto.assert_called_once_with(settings.URL_GERADOR_IDENTIDADE, wait_until="domcontentloaded")
        page.wait_for_selector.assert_called_once_with(SELETOR_NOME)

    def test_primeira_palavra_e_o_nome_e_a_ultima_e_o_sobrenome(self, evidencias):
        comprador = _raspar_fakenamegenerator(_pagina(nome="  João P. Silva \n"), evidencias)
        assert (comprador.nome, comprador.sobrenome) == ("João", "Silva")

    @pytest.mark.parametrize("linha_cep, cep", [
        ("14090-260", "14090-260"),
        ("14090260", "14090260"),
        ("CEP 01310-100", "01310-100"),
    ])
    def test_reconhece_o_cep_com_ou_sem_hifen(self, evidencias, linha_cep, cep):
        page = _pagina(endereco=f"Av. Paulista, 1000\nSão Paulo-SP\n{linha_cep}")
        assert _raspar_fakenamegenerator(page, evidencias).cep == cep

    def test_ignora_linhas_em_branco_do_endereco(self, evidencias):
        page = _pagina(endereco="\n  Rua X, 1 \n\n Ribeirão Preto-SP \n 14090-260 \n")
        assert _raspar_fakenamegenerator(page, evidencias).cep == "14090-260"

    def test_tira_print_do_gerador_como_evidencia(self, evidencias):
        page = _pagina()
        _raspar_fakenamegenerator(page, evidencias)
        evidencias.navegador.assert_called_once_with(page, "gerador_identidade", pagina_inteira=False)

    @pytest.mark.parametrize("nome, endereco", [
        pytest.param("Vitória", ENDERECO_BR, id="nome-sem-sobrenome"),
        pytest.param("Vitória Rocha", "Rua X, 1\nRibeirão Preto-SP", id="endereco-sem-linha-do-cep"),
        pytest.param("Vitória Rocha", "Rua X, 1\nRibeirão Preto-SP\nsem cep", id="linha-do-cep-sem-numero"),
    ])
    def test_layout_inesperado_e_falha_tecnica_repetida(self, evidencias, nome, endereco):
        page = _pagina(nome, endereco)
        with pytest.raises(SystemException, match="Layout inesperado no gerador"):
            _raspar_fakenamegenerator(page, evidencias)
        assert page.goto.call_count == settings.TENTATIVAS_POR_ITEM
        evidencias.navegador.assert_not_called()


class TestGerarComprador:
    def test_devolve_o_comprador_validado_e_registra_no_log(self, evidencias, monkeypatch, caplog):
        page = MagicMock(name="page")
        raspar = MagicMock(return_value=Comprador("Vitória", "Rocha", "14090-260"))
        monkeypatch.setattr(gerador_identidade, "_raspar_fakenamegenerator", raspar)

        assert gerar_comprador(page, evidencias) == Comprador("Vitória", "Rocha", "14090-260")
        raspar.assert_called_once_with(page, evidencias)
        assert "Comprador gerado → nome='Vitória' sobrenome='Rocha' cep='14090-260'" in caplog.text

    def test_falha_na_raspagem_tira_print_de_erro_e_repropaga(self, evidencias, monkeypatch):
        page = MagicMock(name="page")
        monkeypatch.setattr(gerador_identidade, "_raspar_fakenamegenerator",
                            MagicMock(side_effect=SystemException("site fora do ar")))
        with pytest.raises(SystemException, match="site fora do ar"):
            gerar_comprador(page, evidencias)
        evidencias.erro.assert_called_once_with("gerador_identidade", page)

    def test_comprador_invalido_e_falha_de_negocio(self, evidencias, monkeypatch):
        monkeypatch.setattr(gerador_identidade, "_raspar_fakenamegenerator",
                            MagicMock(return_value=Comprador("Vitória", "Rocha", "123")))
        with pytest.raises(BusinessException, match="CEP inválido"):
            gerar_comprador(MagicMock(name="page"), evidencias)
