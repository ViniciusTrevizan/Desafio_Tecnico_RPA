"""Passos 2 e 3 — Login no Sauce Demo e raspagem do catálogo completo."""
from config import settings
from src.core.decorators import com_retry, log_etapa
from src.core.evidencias import Evidencias
from src.core.excecoes import BusinessException, SystemException
from src.core.logger import get_logger
from src.models.entidades import Produto

log = get_logger("producer")

USUARIO_PREFERIDO = "standard_user"


@log_etapa(log)
def obter_credenciais(page) -> tuple[str, str]:
    """Lê usuário e senha de teste exibidos na própria página de login."""
    page.goto(settings.URL_SAUCEDEMO, wait_until="domcontentloaded")
    # Ex.: "Accepted usernames are:\nstandard_user\nlocked_out_user\n..."
    usuarios = page.inner_text("#login_credentials").splitlines()[1:]
    senha = page.inner_text(".login_password").splitlines()[-1].strip()
    usuarios = [u.strip() for u in usuarios if u.strip()]
    if not usuarios or not senha:
        raise SystemException("Credenciais de teste não encontradas na página de login")

    usuario = USUARIO_PREFERIDO if USUARIO_PREFERIDO in usuarios else usuarios[0]
    log.info(f"Usuários disponíveis: {', '.join(usuarios)} → usando '{usuario}'")
    return usuario, senha


@log_etapa(log)
@com_retry(log)
def login(page, usuario: str, senha: str, evidencias: Evidencias) -> None:
    """Preenche o formulário de login e valida o acesso ao inventário."""
    if "inventory" not in page.url:
        page.goto(settings.URL_SAUCEDEMO, wait_until="domcontentloaded")
    log.info("Preenchendo campo usuário (#user-name)")
    page.fill("#user-name", usuario)
    log.info("Preenchendo campo senha (#password)")
    page.fill("#password", senha)
    log.info("Clicando em Login (#login-button)")
    page.click("#login-button")

    erro = page.locator('[data-test="error"]')
    if erro.count():
        evidencias.erro("login", page)
        raise BusinessException(f"Login recusado: {erro.inner_text()}")

    page.wait_for_selector(".inventory_list")
    log.info("Login realizado — página de inventário carregada")


@log_etapa(log)
def coletar_catalogo(page, evidencias: Evidencias) -> list[Produto]:
    """Percorre todos os produtos da vitrine e extrai número, nome, descrição e preço."""
    itens = page.locator(".inventory_item")
    total = itens.count()
    if total == 0:
        raise SystemException("Nenhum produto encontrado na vitrine")
    log.info(f"{total} produtos encontrados na vitrine")

    produtos = []
    for indice in range(total):
        item = itens.nth(indice)
        produto = Produto(
            numero=str(indice + 1),
            nome=item.locator(".inventory_item_name").inner_text().strip(),
            descricao=item.locator(".inventory_item_desc").inner_text().strip(),
            preco=item.locator(".inventory_item_price").inner_text().strip().lstrip("$"),
        ).validar()
        produtos.append(produto)
        log.info(f"[{indice + 1}/{total}] Coletado: #{produto.numero} '{produto.nome}' — $ {produto.preco}")

    evidencias.navegador(page, "saucedemo_catalogo")
    return produtos
