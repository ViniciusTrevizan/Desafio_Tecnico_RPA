"""Validação do ambiente (sistema operacional / sessão gráfica) e localização do Fakturama.

Windows: usa FAKTURAMA_EXE / settings.FAKTURAMA_EXECUTAVEL, sem mudanças.
Linux:   exige sessão X11 (pyautogui não controla mouse/teclado no Wayland) e procura o
         executável do Fakturama no PATH, nos caminhos de instalação conhecidos e nos
         atalhos .desktop do menu de aplicativos.
"""
import os
import platform
import shlex
import shutil
from pathlib import Path

from config import settings
from src.core.excecoes import SystemException
from src.core.logger import get_logger

log = get_logger()

SISTEMA = platform.system()  # "Windows", "Linux", "Darwin"

# Instalação pelo .deb oficial (/usr/share/fakturama2) e pelo instalador .tar.gz (/opt)
CAMINHOS_LINUX = [Path("/usr/share/fakturama2/Fakturama"), Path("/opt/Fakturama2/Fakturama"),
                  Path.home() / "Fakturama2" / "Fakturama"]
PASTA_SESSOES_X11 = Path("/usr/share/xsessions")
PASTAS_ATALHOS_LINUX = [Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                        Path.home() / ".local" / "share" / "applications"]


def eh_windows() -> bool:
    return SISTEMA == "Windows"


def eh_linux() -> bool:
    return SISTEMA == "Linux"


def validar_ambiente(precisa_desktop: bool) -> None:
    """Identifica o sistema e, se a etapa desktop vai rodar, confere se ele suporta a automação."""
    log.info(f"Ambiente: {SISTEMA} {platform.release()} | Python {platform.python_version()}")
    if not precisa_desktop or eh_windows():
        return
    if not eh_linux():
        raise SystemException(f"Sistema '{SISTEMA}' não suportado para a etapa desktop (use Windows ou Linux)")

    sessao = os.getenv("XDG_SESSION_TYPE", "").lower()
    if sessao == "wayland" or (os.getenv("WAYLAND_DISPLAY") and not sessao == "x11"):
        raise SystemException("Sessão gráfica Wayland detectada: o pyautogui não controla mouse/teclado nela. "
                              f"Faça logout e entre com '{_nome_sessao_xorg()}' (engrenagem na tela de login)")
    if not os.getenv("DISPLAY"):
        raise SystemException("Variável DISPLAY ausente: a etapa desktop precisa de uma sessão gráfica X11")
    log.info(f"Sessão gráfica X11 em DISPLAY={os.environ['DISPLAY']}")


def _nome_sessao_xorg() -> str:
    """Nome da sessão Xorg exibido na tela de login (varia por distro: Ubuntu, Zorin, Pop!_OS...)."""
    sessoes = sorted(PASTA_SESSOES_X11.glob("*.desktop")) if PASTA_SESSOES_X11.is_dir() else []
    for sessao in sorted(sessoes, key=lambda s: "xorg" not in s.name.lower()):
        for linha in sessao.read_text(errors="ignore").splitlines():
            if linha.startswith("Name=") and "xorg" in linha.lower():
                return linha[len("Name="):].strip()
    return "<sua área de trabalho> on Xorg"


def variaveis_sem_snap(origem: dict[str, str] | None = None) -> dict[str, str]:
    """Variáveis de ambiente sem o que o VS Code via snap injeta no terminal integrado.

    GTK_PATH, GDK_PIXBUF_MODULEDIR, GIO_MODULE_DIR... apontam para bibliotecas de dentro do snap
    e quebram o WebKitGTK do Fakturama ("no underlying browser available"). O snap guarda os
    valores originais em <VAR>_VSCODE_SNAP_ORIG: eles são restaurados (vazio = não existia).
    """
    origem = dict(os.environ if origem is None else origem)
    limpas = {nome: valor for nome, valor in origem.items()
              if not nome.startswith("SNAP") and "/snap/" not in valor and not nome.endswith("_VSCODE_SNAP_ORIG")}
    for nome, valor in origem.items():
        if nome.endswith("_VSCODE_SNAP_ORIG"):
            original = nome.removesuffix("_VSCODE_SNAP_ORIG")
            if valor:
                limpas[original] = valor
            else:
                limpas.pop(original, None)
    return limpas


def executavel_fakturama() -> Path:
    """Caminho do executável do Fakturama conforme o sistema operacional."""
    if not eh_linux():
        return Path(settings.FAKTURAMA_EXECUTAVEL)

    for candidato in _candidatos_linux():
        if candidato.is_file() and os.access(candidato, os.X_OK):
            log.debug(f"Fakturama encontrado em {candidato}")
            return candidato
    raise SystemException("Executável do Fakturama não encontrado no Linux (procurado em FAKTURAMA_EXE, PATH, "
                          f"{', '.join(map(str, CAMINHOS_LINUX))} e atalhos .desktop). "
                          "Instale o .deb de fakturama.info ou defina FAKTURAMA_EXE")


def _candidatos_linux():
    """Onde procurar, em ordem de prioridade."""
    yield Path(settings.FAKTURAMA_EXECUTAVEL)
    for nome in ("Fakturama", "fakturama", "fakturama2"):
        if achado := shutil.which(nome):
            yield Path(achado)
    yield from CAMINHOS_LINUX
    yield from _executaveis_dos_atalhos()


def _executaveis_dos_atalhos():
    """Lê a linha Exec= dos atalhos *fakturama*.desktop do menu de aplicativos."""
    for pasta in PASTAS_ATALHOS_LINUX:
        for atalho in sorted(pasta.glob("*[Ff]akturama*.desktop")) if pasta.is_dir() else []:
            for linha in atalho.read_text(errors="ignore").splitlines():
                if linha.startswith("Exec="):
                    comando = shlex.split(linha[len("Exec="):])
                    if comando:
                        yield Path(shutil.which(comando[0]) or comando[0])
                    break
