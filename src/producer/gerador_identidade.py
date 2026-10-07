"""Passo 1 — Gera um comprador fake raspando o fakenamegenerator.com."""
import re

from config import settings
from src.core.decorators import com_retry, log_etapa
from src.core.evidencias import Evidencias
from src.core.excecoes import SystemException
from src.core.logger import get_logger
from src.models.entidades import Comprador

log = get_logger("producer")

SELETOR_NOME = "#identity-name"
SELETOR_ENDERECO = "p.gen-address.adr"  # rua <br> cidade-UF <br> CEP
REGEX_CEP = re.compile(r"\b\d{5}-?\d{3}\b|\b\d{5}\b")


@log_etapa(log)
def gerar_comprador(page, evidencias: Evidencias) -> Comprador:
    """Gera o comprador fake (nome, sobrenome e CEP)."""
    try:
        comprador = _raspar_fakenamegenerator(page, evidencias)
    except Exception:
        evidencias.erro("gerador_identidade", page)
        raise

    comprador.validar()
    log.info(f"Comprador gerado → nome='{comprador.nome}' sobrenome='{comprador.sobrenome}' cep='{comprador.cep}'")
    return comprador


@com_retry(log)
def _raspar_fakenamegenerator(page, evidencias: Evidencias) -> Comprador:
    """Abre o gerador e extrai nome completo e CEP do bloco de endereço."""
    log.info(f"Acessando {settings.URL_GERADOR_IDENTIDADE}")
    page.goto(settings.URL_GERADOR_IDENTIDADE, wait_until="domcontentloaded")
    page.wait_for_selector(SELETOR_NOME)

    nome_completo = page.inner_text(SELETOR_NOME).strip()
    endereco = page.inner_text(SELETOR_ENDERECO).strip()
    log.debug(f"Nome completo raspado: '{nome_completo}' | Endereço: '{endereco!r}'")

    partes = nome_completo.split()
    linhas = [linha.strip() for linha in endereco.splitlines() if linha.strip()]
    # CEP é a 3ª linha do endereço; regex valida o formato
    cep = REGEX_CEP.search(linhas[2]) if len(linhas) >= 3 else None
    if len(partes) < 2 or not cep:
        raise SystemException(f"Layout inesperado no gerador: nome='{nome_completo}' endereço='{endereco}'")

    evidencias.navegador(page, "gerador_identidade", pagina_inteira=False)
    # Nome do meio/inicial é descartado: 1ª palavra = nome, última = sobrenome
    return Comprador(nome=partes[0], sobrenome=partes[-1], cep=cep.group())
