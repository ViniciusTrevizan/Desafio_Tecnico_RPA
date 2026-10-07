"""Testes de src/utils/csv_handler.py — CSVs que fazem a ponte entre a etapa web e a desktop.

PDF §4.4 e §5: um CSV para o comprador (nome, sobrenome, CEP) e outro para o catálogo
(número, nome, descrição e preço de TODOS os produtos coletados).
"""
import csv

import pytest

from config import settings
from src.models.entidades import Comprador, Produto
from src.utils.csv_handler import ler_csv, salvar_csv


def _linhas(caminho):
    """Lê o CSV cru (sem converter em dataclass) para conferir cabeçalho e colunas."""
    with caminho.open(newline="", encoding=settings.CSV_ENCODING) as arquivo:
        return list(csv.reader(arquivo, delimiter=settings.CSV_DELIMITADOR))


class TestSalvarCsv:
    def test_csv_do_comprador_tem_nome_sobrenome_e_cep(self, tmp_path, comprador):
        caminho = tmp_path / "comprador.csv"
        assert salvar_csv(caminho, [comprador]) == 1
        assert _linhas(caminho) == [["nome", "sobrenome", "cep"], ["Vitória", "Rocha", "14090-260"]]

    def test_csv_do_catalogo_tem_numero_nome_descricao_e_preco_de_todos_os_produtos(self, tmp_path, produtos):
        caminho = tmp_path / "catalogo.csv"
        assert salvar_csv(caminho, produtos) == 6
        cabecalho, *linhas = _linhas(caminho)
        assert cabecalho == ["numero", "nome", "descricao", "preco"]
        assert linhas == [[p.numero, p.nome, p.descricao, p.preco] for p in produtos]

    def test_grava_utf8_com_bom_e_ponto_e_virgula_para_abrir_no_excel(self, tmp_path, comprador):
        caminho = tmp_path / "comprador.csv"
        salvar_csv(caminho, [comprador])
        assert caminho.read_bytes() == "﻿nome;sobrenome;cep\r\nVitória;Rocha;14090-260\r\n".encode("utf-8")

    def test_regravar_substitui_o_conteudo_anterior(self, tmp_path, produtos):
        caminho = tmp_path / "catalogo.csv"
        salvar_csv(caminho, produtos)
        salvar_csv(caminho, produtos[:2])
        assert len(_linhas(caminho)) == 1 + 2

    def test_lista_vazia_e_erro_e_nao_cria_arquivo(self, tmp_path):
        caminho = tmp_path / "catalogo.csv"
        with pytest.raises(ValueError, match="Nenhum registro para salvar em catalogo.csv"):
            salvar_csv(caminho, [])
        assert not caminho.exists()


class TestLerCsv:
    def test_le_exatamente_o_que_foi_salvo(self, tmp_path, comprador, produtos):
        """Os dados que chegam ao desktop são os mesmos raspados na web (PDF §6)."""
        salvar_csv(tmp_path / "comprador.csv", [comprador])
        salvar_csv(tmp_path / "catalogo.csv", produtos)
        assert ler_csv(tmp_path / "comprador.csv", Comprador) == [comprador]
        assert ler_csv(tmp_path / "catalogo.csv", Produto) == produtos

    def test_preserva_textos_com_delimitador_aspas_e_quebra_de_linha(self, tmp_path):
        produto = Produto("7", 'Camiseta "Bolt"; edição limitada', "Linha 1\nLinha 2; com ponto e vírgula", "15.99")
        salvar_csv(tmp_path / "catalogo.csv", [produto])
        assert ler_csv(tmp_path / "catalogo.csv", Produto) == [produto]
