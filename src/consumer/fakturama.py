"""Passos 5 e 6 — Ações de negócio no Fakturama (contatos e produtos)."""
import subprocess
import time
from pathlib import Path

from config import settings
from src.consumer import desktop
from src.core.decorators import log_etapa
from src.core.evidencias import Evidencias
from src.core.excecoes import SystemException
from src.core.logger import get_logger
from src.models.entidades import Comprador, Produto

log = get_logger("consumer")


class Fakturama:
    def __init__(self, evidencias: Evidencias):
        self.evidencias = evidencias

    @log_etapa(log)
    def abrir(self) -> None:
        """Abre o Fakturama (se necessário) e aguarda a janela principal."""
        if desktop.existe("app_pronto"):
            log.info("Fakturama já está aberto")
            return
        executavel = Path(settings.FAKTURAMA_EXECUTAVEL)
        if not executavel.exists():
            raise SystemException(f"Executável do Fakturama não encontrado: {executavel} (defina FAKTURAMA_EXE)")
        log.info(f"Iniciando {executavel}")
        subprocess.Popen([str(executavel)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        desktop.localizar("app_pronto", timeout=settings.TIMEOUT_ABERTURA_APP)
        log.info("Janela principal do Fakturama pronta")

    def _preencher(self, chave_rotulo: str, valor: str, campo: str) -> None:
        """Clica no campo ao lado do rótulo (imagem) e digita o valor; TAB confirma."""
        log.info(f"  • {campo:<10} ← '{valor}'", stacklevel=2)
        desktop.clicar_imagem(chave_rotulo, offset_x=settings.OFFSET_CAMPO_X)
        desktop.digitar(valor)
        desktop.tecla("tab")

    def _salvar_e_fechar_editor(self, nome_print: str) -> None:
        """Ctrl+S salva, captura a evidência do registro salvo e Ctrl+W fecha o editor."""
        desktop.atalho("ctrl", "s")
        time.sleep(settings.ESPERA_APOS_SALVAR)
        self.evidencias.tela(nome_print)
        desktop.atalho("ctrl", "w")

    @log_etapa(log)
    def cadastrar_contato(self, comprador: Comprador) -> None:
        """Cadastra o comprador como novo contato."""
        desktop.clicar_imagem("btn_novo_contato")
        desktop.localizar("campo_contato_nome")  # garante que o editor abriu
        self._preencher("campo_contato_nome", comprador.nome, "Nome")
        self._preencher("campo_contato_sobrenome", comprador.sobrenome, "Sobrenome")
        self._preencher("campo_contato_cep", comprador.cep, "CEP")
        self._salvar_e_fechar_editor("contato_cadastrado")

    @log_etapa(log)
    def cadastrar_produto(self, produto: Produto) -> None:
        """Cadastra um produto do catálogo como novo item."""
        preco = produto.preco.replace(".", settings.SEPARADOR_DECIMAL_FAKTURAMA)
        desktop.clicar_imagem("btn_novo_produto")
        desktop.localizar("campo_produto_numero")
        self._preencher("campo_produto_numero", produto.numero, "Número")
        self._preencher("campo_produto_nome", produto.nome, "Nome")
        self._preencher("campo_produto_descricao", produto.descricao, "Descrição")
        self._preencher("campo_produto_preco", preco, "Preço")
        self._salvar_e_fechar_editor(f"produto_{produto.numero}_cadastrado")

    @log_etapa(log)
    def evidenciar_lista(self, tipo: str) -> Path:
        """Abre a lista de contatos/produtos no menu lateral e captura o print final."""
        desktop.clicar_imagem(f"nav_{tipo}")
        time.sleep(settings.ESPERA_APOS_SALVAR)
        return self.evidencias.tela(f"lista_{tipo}")

    def recuperar(self) -> None:
        """Tenta voltar a um estado limpo após falha (fecha diálogos/editores abertos)."""
        log.warning("Recuperando estado da aplicação (ESC x2)")
        desktop.tecla("esc", 2)
