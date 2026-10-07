"""Fila de trabalho em arquivo JSON que liga o producer (web) ao consumer (desktop).

O producer adiciona um item por contato/produto; o consumer pega os pendentes,
processa e marca o status. O arquivo permite retomar uma execução interrompida.
"""
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


class Status:
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    SUCESSO = "SUCESSO"
    FALHA_NEGOCIO = "FALHA_NEGOCIO"
    FALHA_SISTEMA = "FALHA_SISTEMA"


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ItemFila:
    tipo: str                 # "contato" | "produto"
    referencia: str           # identificador legível (ex.: nome do produto)
    payload: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = Status.PENDENTE
    tentativas: int = 0
    erro: str = ""
    criado_em: str = field(default_factory=_agora)
    atualizado_em: str = field(default_factory=_agora)


class FilaArquivo:
    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self._lock = threading.Lock()
        self._itens: list[ItemFila] = self._carregar()

    # ── persistência ────────────────────────────────────────────────────────
    def _carregar(self) -> list[ItemFila]:
        if not self.arquivo.exists():
            return []
        return [ItemFila(**d) for d in json.loads(self.arquivo.read_text(encoding="utf-8"))]

    def _salvar(self) -> None:
        temporario = self.arquivo.with_suffix(".tmp")
        temporario.write_text(
            json.dumps([asdict(i) for i in self._itens], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporario, self.arquivo)  # escrita atômica

    # ── producer ────────────────────────────────────────────────────────────
    def limpar(self) -> None:
        with self._lock:
            self._itens = []
            self._salvar()

    def adicionar(self, tipo: str, referencia: str, payload: dict) -> ItemFila:
        with self._lock:
            item = ItemFila(tipo=tipo, referencia=referencia, payload=payload)
            self._itens.append(item)
            self._salvar()
            return item

    # ── consumer ────────────────────────────────────────────────────────────
    def proximo(self, tipo: str | None = None) -> ItemFila | None:
        """Retorna o próximo item pendente e o marca como PROCESSANDO."""
        with self._lock:
            for item in self._itens:
                if item.status == Status.PENDENTE and (tipo is None or item.tipo == tipo):
                    item.status = Status.PROCESSANDO
                    item.tentativas += 1
                    item.atualizado_em = _agora()
                    self._salvar()
                    return item
            return None

    def _finalizar(self, item: ItemFila, status: str, erro: str = "") -> None:
        with self._lock:
            item.status, item.erro, item.atualizado_em = status, erro, _agora()
            self._salvar()

    def concluir(self, item: ItemFila) -> None:
        self._finalizar(item, Status.SUCESSO)

    def devolver(self, item: ItemFila, erro: str) -> None:
        """Volta o item para PENDENTE para uma nova tentativa."""
        self._finalizar(item, Status.PENDENTE, erro)

    def falhar(self, item: ItemFila, erro: str, negocio: bool = False) -> None:
        self._finalizar(item, Status.FALHA_NEGOCIO if negocio else Status.FALHA_SISTEMA, erro)

    def reabrir_falhas(self) -> int:
        """Recoloca itens com falha (ou travados em PROCESSANDO) como PENDENTE."""
        with self._lock:
            reabertos = 0
            for item in self._itens:
                if item.status not in (Status.SUCESSO, Status.PENDENTE):
                    item.status, item.tentativas, item.erro = Status.PENDENTE, 0, ""
                    reabertos += 1
            self._salvar()
            return reabertos

    # ── consulta ────────────────────────────────────────────────────────────
    def itens(self, tipo: str | None = None, status: str | None = None) -> list[ItemFila]:
        return [i for i in self._itens
                if (tipo is None or i.tipo == tipo) and (status is None or i.status == status)]

    def resumo(self) -> dict[str, dict[str, int]]:
        """Contagem por tipo e status: {'produto': {'SUCESSO': 6}, ...}."""
        contagem: dict[str, dict[str, int]] = {}
        for item in self._itens:
            por_status = contagem.setdefault(item.tipo, {})
            por_status[item.status] = por_status.get(item.status, 0) + 1
        return contagem
