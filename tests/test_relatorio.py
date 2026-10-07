"""Testes de src/core/relatorio.py — conferência final CSV (web) × cadastrados (desktop).

PDF §6: a automação só é bem-sucedida quando o comprador e o número de produtos dos CSVs
coincidem exatamente com o que foi cadastrado no Fakturama — os dados batem 100%.
"""
import json
import logging
from dataclasses import asdict

import pytest

from src.core.relatorio import gerar_relatorio
from src.utils.csv_handler import salvar_csv


@pytest.fixture
def execucao(ctx, comprador, produtos):
    """Execução com CSVs gravados e fila montada, como o producer deixa."""
    salvar_csv(ctx.csv_comprador, [comprador])
    salvar_csv(ctx.csv_catalogo, produtos)
    ctx.fila.adicionar("contato", f"{comprador.nome} {comprador.sobrenome}", asdict(comprador))
    for produto in produtos:
        ctx.fila.adicionar("produto", produto.nome, asdict(produto))
    return ctx


def _cadastrar(fila, falham=()):
    """Simula o consumer: conclui todos os itens, exceto os de referência em `falham`."""
    while item := fila.proximo():
        if item.referencia in falham:
            fila.falhar(item, "Imagem 'campo_produto_preco' não encontrada em 15s")
        else:
            fila.concluir(item)


def _erros(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


def test_sucesso_quando_comprador_e_todos_os_produtos_foram_cadastrados(execucao, caplog):
    _cadastrar(execucao.fila)
    assert gerar_relatorio(execucao) is True
    assert "RESULTADO: dados web e desktop batem 100%" in caplog.text
    assert _erros(caplog) == []


def test_resumo_json_registra_contagens_status_e_prints(execucao):
    _cadastrar(execucao.fila)
    for nome in ("02_lista_produtos_101500.png", "01_contato_cadastrado_101000.png"):
        (execucao.pasta_prints / nome).touch()
    gerar_relatorio(execucao)
    assert json.loads(execucao.arquivo_resumo.read_text(encoding="utf-8")) == {
        "run_id": "execucao_teste",
        "sucesso": True,
        "csv": {"contato": 1, "produto": 6},
        "cadastrados": {"contato": 1, "produto": 6},
        "fila": {"contato": {"SUCESSO": 1}, "produto": {"SUCESSO": 6}},
        "prints": ["01_contato_cadastrado_101000.png", "02_lista_produtos_101500.png"],
    }


def test_produto_nao_cadastrado_deixa_o_resultado_divergente(execucao, caplog):
    _cadastrar(execucao.fila, falham={"Sauce Labs Onesie"})
    assert gerar_relatorio(execucao) is False
    erros = _erros(caplog)
    assert any(linha.startswith("produto") and linha.endswith("DIVERGENTE") for linha in erros)
    assert "RESULTADO: há divergências — ver erros.log" in erros
    assert "Pendência: produto 'Sauce Labs Onesie' → FALHA_SISTEMA" in caplog.text


def test_comprador_nao_cadastrado_deixa_o_resultado_divergente(execucao, caplog):
    _cadastrar(execucao.fila, falham={"Vitória Rocha"})
    assert gerar_relatorio(execucao) is False
    assert any(linha.startswith("contato") and linha.endswith("DIVERGENTE") for linha in _erros(caplog))


def test_cadastros_a_mais_que_no_csv_tambem_divergem(execucao, produtos):
    salvar_csv(execucao.csv_catalogo, produtos[:5])  # CSV com 5 produtos, Fakturama com 6
    _cadastrar(execucao.fila)
    assert gerar_relatorio(execucao) is False


def test_sem_csvs_nao_ha_sucesso_mesmo_sem_divergencia(ctx):
    """Nada coletado e nada cadastrado (0 = 0) não conta como sucesso."""
    assert gerar_relatorio(ctx) is False
    resumo = json.loads(ctx.arquivo_resumo.read_text(encoding="utf-8"))
    assert resumo["csv"] == resumo["cadastrados"] == {"contato": 0, "produto": 0}
