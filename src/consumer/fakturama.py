"""Passos 5 e 6 — Ações de negócio no Fakturama (contatos e produtos)."""
import subprocess
import time
from pathlib import Path

from config import settings
from src.consumer import desktop
from src.core import ambiente
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
        """Abre o Fakturama (se necessário), aguarda a janela principal e a deixa maximizada."""
        if desktop.maximizar_janela(settings.FAKTURAMA_JANELA):  # já aberto: traz para a frente
            desktop.localizar("app_pronto")
            log.info("Fakturama já está aberto (janela maximizada)")
            return
        executavel = ambiente.executavel_fakturama()
        if not executavel.exists():
            raise SystemException(f"Executável do Fakturama não encontrado: {executavel} (defina FAKTURAMA_EXE)")
        log.info(f"Iniciando {executavel}")
        if ambiente.eh_linux():
            # Sessão própria: o Fakturama continua aberto se o robô for interrompido (Ctrl+C).
            # Sem as variáveis do snap do VS Code, que quebram o navegador embutido (WebKitGTK).
            subprocess.Popen([str(executavel)], cwd=executavel.resolve().parent, start_new_session=True,
                             env=ambiente.variaveis_sem_snap(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([str(executavel)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        desktop.localizar("app_pronto", timeout=settings.TIMEOUT_ABERTURA_APP)
        if not desktop.maximizar_janela(settings.FAKTURAMA_JANELA):
            raise SystemException(f"Janela '{settings.FAKTURAMA_JANELA}' não encontrada para maximizar")
        log.info("Janela principal do Fakturama pronta (maximizada)")

    def _preencher_formulario(self, campos: list[tuple[str, str, str]]) -> None:
        """Preenche o editor: cada campo recebe UM clique na caixa ao lado do rótulo e o valor digitado.

        Todos os campos são localizados antes do primeiro clique: o campo com foco fica amarelo no
        Fakturama e o recorte do rótulo (que pega um pedaço da caixa) deixaria de ser reconhecido.
        """
        posicoes = [desktop.ponto_de_clique(chave_rotulo) for chave_rotulo, _, _ in campos]
        for (_, valor, campo), (x, y) in zip(campos, posicoes):
            log.info(f"  • {campo:<10} ← '{valor}'", stacklevel=2)
            desktop.clicar(x, y)
            desktop.digitar(valor)

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
        self._preencher_formulario([
            ("campo_contato_nome", comprador.nome, "Nome"),
            ("campo_contato_sobrenome", comprador.sobrenome, "Sobrenome"),
            ("campo_contato_cep", comprador.cep, "CEP"),
        ])
        self._salvar_e_fechar_editor("contato_cadastrado")

    @log_etapa(log)
    def cadastrar_produto(self, produto: Produto) -> None:
        """Cadastra um produto do catálogo como novo item."""
        preco = produto.preco.replace(".", settings.SEPARADOR_DECIMAL_FAKTURAMA)
        desktop.clicar_imagem("btn_novo_produto")
        desktop.localizar("campo_produto_numero")  # garante que o editor abriu
        self._preencher_formulario([
            ("campo_produto_numero", produto.numero, "Número"),
            ("campo_produto_nome", produto.nome, "Nome"),
            ("campo_produto_descricao", produto.descricao, "Descrição"),
            ("campo_produto_preco", preco, "Preço"),
        ])
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
