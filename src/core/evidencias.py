"""Captura de prints (evidências) da tela, do navegador e de erros."""
import logging
from datetime import datetime
from pathlib import Path

from src.core.logger import get_logger


class Evidencias:
    """Salva prints numerados em sequência: 01_nome_HHMMSS.png, 02_..."""

    def __init__(self, pasta: Path, logger: logging.Logger | None = None, _contador: list[int] | None = None):
        self.pasta = pasta
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.log = logger or get_logger()
        # Contador compartilhado entre visões; continua a numeração se já houver prints
        self._contador = _contador if _contador is not None else [len(list(pasta.glob("*.png")))]

    def para(self, logger: logging.Logger) -> "Evidencias":
        """Mesma pasta e numeração, mas registrando no log do componente (producer/consumer)."""
        return Evidencias(self.pasta, logger, self._contador)

    def _novo_caminho(self, nome: str) -> Path:
        self._contador[0] += 1
        return self.pasta / f"{self._contador[0]:02d}_{nome}_{datetime.now():%H%M%S}.png"

    def tela(self, nome: str) -> Path:
        """Print da tela inteira (todos os monitores) — usado na etapa desktop."""
        import mss
        import mss.tools

        caminho = self._novo_caminho(nome)
        with mss.mss() as sct:
            imagem = sct.grab(sct.monitors[0])
            mss.tools.to_png(imagem.rgb, imagem.size, output=str(caminho))
        self.log.info(f"📸 Print da tela salvo: {caminho.name}", stacklevel=2)
        return caminho

    def navegador(self, page, nome: str, pagina_inteira: bool = True) -> Path:
        """Print da página atual do navegador (Playwright) — usado na etapa web."""
        caminho = self._novo_caminho(nome)
        page.screenshot(path=str(caminho), full_page=pagina_inteira)
        self.log.info(f"📸 Print do navegador salvo: {caminho.name}", stacklevel=2)
        return caminho

    def erro(self, nome: str, page=None) -> Path | None:
        """Print de falha. Nunca levanta exceção para não mascarar o erro original."""
        try:
            return self.navegador(page, f"ERRO_{nome}", False) if page else self.tela(f"ERRO_{nome}")
        except Exception as falha:
            self.log.warning(f"Não foi possível capturar print de erro '{nome}': {falha}", stacklevel=2)
            return None
