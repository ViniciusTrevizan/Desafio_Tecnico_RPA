"""Testes de src/core/contexto.py — a pasta de resultados de cada execução.

PDF §4.7 e §5: CSVs, prints e log de execução reunidos numa pasta de resultados.
"""
import re

from src.core.contexto import Contexto
from src.core.evidencias import Evidencias
from src.core.fila import FilaArquivo

RUN_ID_DATA_HORA = r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"


class TestCriar:
    def test_monta_a_pasta_da_execucao_com_csv_prints_e_logs(self, pasta_resultados):
        ctx = Contexto.criar("2026-10-07_09-00-00")
        pasta = pasta_resultados / "2026-10-07_09-00-00"
        assert (ctx.run_id, ctx.pasta) == ("2026-10-07_09-00-00", pasta)
        assert (ctx.pasta_csv, ctx.pasta_prints, ctx.pasta_logs) == (pasta / "csv", pasta / "prints", pasta / "logs")
        assert all(p.is_dir() for p in (ctx.pasta_csv, ctx.pasta_prints, ctx.pasta_logs))
        assert ctx.csv_comprador == pasta / "csv" / "comprador.csv"
        assert ctx.csv_catalogo == pasta / "csv" / "catalogo.csv"
        assert ctx.arquivo_resumo == pasta / "resumo.json"
        assert isinstance(ctx.fila, FilaArquivo) and ctx.fila.arquivo == pasta / "fila.json"
        assert isinstance(ctx.evidencias, Evidencias) and ctx.evidencias.pasta == ctx.pasta_prints

    def test_sem_run_id_usa_a_data_e_hora_atual(self):
        ctx = Contexto.criar()
        assert re.fullmatch(RUN_ID_DATA_HORA, ctx.run_id)
        assert ctx.pasta.is_dir()

    def test_usar_ultima_reaproveita_a_execucao_mais_recente(self, pasta_resultados):
        for nome in ("2026-10-06_18-00-00", "2026-10-07_08-40-01", "2026-10-07_08-05-00"):
            (pasta_resultados / nome).mkdir()
        (pasta_resultados / ".gitkeep").touch()  # arquivos soltos são ignorados
        assert Contexto.criar(usar_ultima=True).run_id == "2026-10-07_08-40-01"

    def test_usar_ultima_sem_execucoes_anteriores_cria_uma_nova(self):
        assert re.fullmatch(RUN_ID_DATA_HORA, Contexto.criar(usar_ultima=True).run_id)

    def test_run_id_informado_tem_prioridade_sobre_usar_ultima(self, pasta_resultados):
        (pasta_resultados / "2026-10-07_08-40-01").mkdir()
        assert Contexto.criar("minha_execucao", usar_ultima=True).run_id == "minha_execucao"

    def test_reabrir_uma_execucao_preserva_fila_e_arquivos(self):
        primeira = Contexto.criar("exec")
        primeira.fila.adicionar("produto", "Sauce Labs Backpack", {})
        primeira.csv_catalogo.write_text("numero;nome;descricao;preco\n", encoding="utf-8")

        reaberta = Contexto.criar("exec")
        assert [i.referencia for i in reaberta.fila.itens()] == ["Sauce Labs Backpack"]
        assert reaberta.csv_catalogo.read_text(encoding="utf-8") == "numero;nome;descricao;preco\n"
