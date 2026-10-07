"""Testes de src/core/fila.py — fila de trabalho em JSON entre producer (web) e consumer (desktop).

PDF §4.5/§4.6: cada registro coletado vira um item a cadastrar. PDF §6: o status de cada
item permite conferir exatamente o que foi cadastrado e retomar o que faltou.
"""
import json
import re
from datetime import datetime

import pytest

from src.core import fila as modulo_fila
from src.core.fila import FilaArquivo, ItemFila, Status, _agora

ISO_SEGUNDOS = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"


@pytest.fixture
def arquivo(tmp_path):
    return tmp_path / "fila.json"


@pytest.fixture
def fila(arquivo):
    return FilaArquivo(arquivo)


def _no_disco(arquivo):
    return json.loads(arquivo.read_text(encoding="utf-8"))


def test_agora_devolve_data_hora_iso_com_precisao_de_segundos():
    agora = _agora()
    assert re.fullmatch(ISO_SEGUNDOS, agora)
    assert abs((datetime.now() - datetime.fromisoformat(agora)).total_seconds()) < 5


class TestItemFila:
    def test_nasce_pendente_sem_tentativas_e_com_datas(self):
        item = ItemFila(tipo="produto", referencia="Sauce Labs Backpack", payload={"numero": "1"})
        assert (item.status, item.tentativas, item.erro) == (Status.PENDENTE, 0, "")
        assert re.fullmatch(r"[0-9a-f]{8}", item.id)
        assert re.fullmatch(ISO_SEGUNDOS, item.criado_em)
        assert re.fullmatch(ISO_SEGUNDOS, item.atualizado_em)

    def test_cada_item_recebe_um_id_diferente(self):
        assert len({ItemFila("produto", "x", {}).id for _ in range(100)}) == 100


class TestCarregarESalvar:
    def test_arquivo_inexistente_comeca_com_fila_vazia(self, fila, arquivo):
        assert fila.itens() == []
        assert not arquivo.exists()

    def test_grava_json_legivel_preservando_acentos(self, fila, arquivo):
        fila.adicionar("contato", "Vitória Rocha", {"nome": "Vitória"})
        assert '"referencia": "Vitória Rocha"' in arquivo.read_text(encoding="utf-8")

    def test_escrita_atomica_nao_deixa_arquivo_temporario(self, fila, arquivo):
        fila.adicionar("produto", "Sauce Labs Backpack", {})
        assert arquivo.exists()
        assert not arquivo.with_suffix(".tmp").exists()

    def test_reabrir_o_arquivo_recupera_itens_e_status(self, fila, arquivo):
        """Permite rodar só o consumer depois, ou retomar uma execução interrompida."""
        fila.adicionar("contato", "Vitória Rocha", {"nome": "Vitória"})
        fila.adicionar("produto", "Sauce Labs Backpack", {"preco": "29.99"})
        fila.concluir(fila.proximo("contato"))
        assert FilaArquivo(arquivo).itens() == fila.itens()


class TestAdicionarELimpar:
    def test_adicionar_enfileira_pendente_na_ordem_de_chegada_e_persiste(self, fila, arquivo):
        contato = fila.adicionar("contato", "Vitória Rocha", {"nome": "Vitória"})
        produto = fila.adicionar("produto", "Sauce Labs Backpack", {"numero": "1"})
        assert fila.itens() == [contato, produto]
        assert contato.status == produto.status == Status.PENDENTE
        assert [d["id"] for d in _no_disco(arquivo)] == [contato.id, produto.id]

    def test_limpar_esvazia_a_fila_e_o_arquivo(self, fila, arquivo):
        fila.adicionar("produto", "Sauce Labs Backpack", {})
        fila.limpar()
        assert fila.itens() == []
        assert _no_disco(arquivo) == []


class TestProximo:
    def test_entrega_o_primeiro_pendente_e_marca_processando(self, fila, arquivo):
        primeiro = fila.adicionar("produto", "Sauce Labs Backpack", {})
        fila.adicionar("produto", "Sauce Labs Bike Light", {})
        item = fila.proximo()
        assert item is primeiro
        assert (item.status, item.tentativas) == (Status.PROCESSANDO, 1)
        assert _no_disco(arquivo)[0]["status"] == Status.PROCESSANDO

    def test_entrega_todos_os_pendentes_em_ordem_e_depois_none(self, fila):
        nomes = ["Sauce Labs Backpack", "Sauce Labs Bike Light", "Sauce Labs Onesie"]
        for nome in nomes:
            fila.adicionar("produto", nome, {})
        entregues = []
        while item := fila.proximo():
            entregues.append(item.referencia)
        assert entregues == nomes

    def test_filtra_por_tipo(self, fila):
        fila.adicionar("produto", "Sauce Labs Backpack", {})
        contato = fila.adicionar("contato", "Vitória Rocha", {})
        assert fila.proximo("contato") is contato
        assert fila.proximo("contato") is None


class TestConcluirDevolverFalhar:
    def test_concluir_marca_sucesso_limpa_erro_e_atualiza_data(self, fila, arquivo, monkeypatch):
        item = fila.adicionar("produto", "Sauce Labs Backpack", {})
        fila.devolver(fila.proximo(), "timeout")
        monkeypatch.setattr(modulo_fila, "_agora", lambda: "2026-10-07T10:00:00")
        fila.concluir(fila.proximo())
        assert (item.status, item.erro, item.tentativas) == (Status.SUCESSO, "", 2)
        assert item.atualizado_em == "2026-10-07T10:00:00"
        assert _no_disco(arquivo)[0]["status"] == Status.SUCESSO

    def test_devolver_volta_para_pendente_guardando_erro_e_tentativas(self, fila):
        item = fila.adicionar("produto", "Sauce Labs Backpack", {})
        fila.devolver(fila.proximo(), "Imagem 'btn_novo_produto' não encontrada em 15s")
        assert (item.status, item.tentativas) == (Status.PENDENTE, 1)
        assert item.erro == "Imagem 'btn_novo_produto' não encontrada em 15s"
        assert fila.proximo() is item

    @pytest.mark.parametrize("negocio, status", [(False, Status.FALHA_SISTEMA), (True, Status.FALHA_NEGOCIO)])
    def test_falhar_distingue_falha_tecnica_de_falha_de_negocio(self, fila, arquivo, negocio, status):
        item = fila.adicionar("produto", "Sauce Labs Backpack", {})
        fila.falhar(fila.proximo(), "motivo", negocio=negocio)
        assert (item.status, item.erro) == (status, "motivo")
        assert _no_disco(arquivo)[0]["status"] == status
        assert fila.proximo() is None


class TestReabrirFalhas:
    def test_recoloca_falhas_e_travados_como_pendentes_com_tentativas_zeradas(self, fila, arquivo):
        for nome in ("sucesso", "negocio", "sistema", "travado", "pendente"):
            fila.adicionar("produto", nome, {})
        fila.concluir(fila.proximo())
        fila.falhar(fila.proximo(), "preço inválido", negocio=True)
        fila.falhar(fila.proximo(), "timeout")
        fila.proximo()  # "travado" fica em PROCESSANDO, como num robô interrompido

        assert fila.reabrir_falhas() == 3
        assert [(i.referencia, i.status, i.tentativas, i.erro) for i in fila.itens()] == [
            ("sucesso", Status.SUCESSO, 1, ""),
            ("negocio", Status.PENDENTE, 0, ""),
            ("sistema", Status.PENDENTE, 0, ""),
            ("travado", Status.PENDENTE, 0, ""),
            ("pendente", Status.PENDENTE, 0, ""),
        ]
        assert [d["status"] for d in _no_disco(arquivo)] == [Status.SUCESSO] + [Status.PENDENTE] * 4

    def test_sem_falhas_nao_reabre_nada(self, fila):
        fila.adicionar("produto", "Sauce Labs Backpack", {})
        assert fila.reabrir_falhas() == 0


class TestConsultas:
    @pytest.fixture
    def fila_mista(self, fila):
        fila.adicionar("contato", "Vitória Rocha", {})
        for nome in ("Sauce Labs Backpack", "Sauce Labs Bike Light", "Sauce Labs Onesie"):
            fila.adicionar("produto", nome, {})
        fila.concluir(fila.proximo("contato"))
        fila.concluir(fila.proximo("produto"))
        fila.falhar(fila.proximo("produto"), "timeout")
        return fila

    def test_itens_filtra_por_tipo_e_por_status(self, fila_mista):
        assert len(fila_mista.itens()) == 4
        assert [i.referencia for i in fila_mista.itens("produto")] == [
            "Sauce Labs Backpack", "Sauce Labs Bike Light", "Sauce Labs Onesie"]
        assert [i.referencia for i in fila_mista.itens("produto", Status.SUCESSO)] == ["Sauce Labs Backpack"]
        assert [i.referencia for i in fila_mista.itens(status=Status.PENDENTE)] == ["Sauce Labs Onesie"]

    def test_resumo_conta_itens_por_tipo_e_status(self, fila_mista):
        assert fila_mista.resumo() == {
            "contato": {Status.SUCESSO: 1},
            "produto": {Status.SUCESSO: 1, Status.FALHA_SISTEMA: 1, Status.PENDENTE: 1},
        }
