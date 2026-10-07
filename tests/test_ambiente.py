"""Testes de src/core/ambiente.py — validação do sistema e localização do Fakturama.

Windows segue como sempre (FAKTURAMA_EXE); no Linux o robô exige X11 e acha o Fakturama sozinho.
"""
import pytest

from config import settings
from src.core import ambiente
from src.core.excecoes import SystemException


@pytest.fixture
def linux(monkeypatch, tmp_path):
    """Linux sem nada instalado: PATH, caminhos conhecidos e atalhos apontam para pastas vazias."""
    monkeypatch.setattr(ambiente, "SISTEMA", "Linux")
    monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(tmp_path / "nao_instalado"))
    monkeypatch.setattr(ambiente.shutil, "which", lambda nome: None)
    monkeypatch.setattr(ambiente, "CAMINHOS_LINUX", [])
    monkeypatch.setattr(ambiente, "PASTAS_ATALHOS_LINUX", [tmp_path / "applications"])
    monkeypatch.setattr(ambiente, "PASTA_SESSOES_X11", tmp_path / "xsessions")
    for variavel in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(variavel, raising=False)
    return tmp_path


def _executavel(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.touch(mode=0o755)
    return caminho


class TestValidarAmbiente:
    def test_windows_nao_exige_nada(self, monkeypatch):
        monkeypatch.setattr(ambiente, "SISTEMA", "Windows")
        ambiente.validar_ambiente(precisa_desktop=True)

    def test_so_producer_nao_exige_sessao_grafica(self, linux, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        ambiente.validar_ambiente(precisa_desktop=False)

    def test_linux_com_x11_e_valido(self, linux, monkeypatch, caplog):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.setenv("DISPLAY", ":0")
        ambiente.validar_ambiente(precisa_desktop=True)
        assert "Sessão gráfica X11 em DISPLAY=:0" in caplog.text

    @pytest.mark.parametrize("variaveis", [{"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"},
                                           {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}])
    def test_linux_com_wayland_orienta_trocar_para_xorg(self, linux, monkeypatch, variaveis):
        for nome, valor in variaveis.items():
            monkeypatch.setenv(nome, valor)
        with pytest.raises(SystemException, match="Wayland.*on Xorg"):
            ambiente.validar_ambiente(precisa_desktop=True)

    def test_wayland_cita_o_nome_da_sessao_xorg_instalada(self, linux, monkeypatch):
        sessoes = linux / "xsessions"
        sessoes.mkdir()
        (sessoes / "zorin.desktop").write_text("[Desktop Entry]\nName=Zorin Desktop\n")
        (sessoes / "zorin-xorg.desktop").write_text("[Desktop Entry]\nName=Zorin Desktop on Xorg\n")
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        with pytest.raises(SystemException, match="entre com 'Zorin Desktop on Xorg'"):
            ambiente.validar_ambiente(precisa_desktop=True)

    def test_linux_sem_display_e_invalido(self, linux, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "tty")
        with pytest.raises(SystemException, match="DISPLAY ausente"):
            ambiente.validar_ambiente(precisa_desktop=True)

    def test_sistema_nao_suportado(self, monkeypatch):
        monkeypatch.setattr(ambiente, "SISTEMA", "Darwin")
        with pytest.raises(SystemException, match="'Darwin' não suportado"):
            ambiente.validar_ambiente(precisa_desktop=True)


class TestExecutavelFakturama:
    def test_windows_usa_a_configuracao_como_esta(self, monkeypatch):
        monkeypatch.setattr(ambiente, "SISTEMA", "Windows")
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", r"C:\Fakturama2\Fakturama.exe")
        assert str(ambiente.executavel_fakturama()) == r"C:\Fakturama2\Fakturama.exe"

    def test_linux_prioriza_fakturama_exe(self, linux, monkeypatch):
        configurado = _executavel(linux / "meu" / "Fakturama")
        monkeypatch.setattr(settings, "FAKTURAMA_EXECUTAVEL", str(configurado))
        monkeypatch.setattr(ambiente.shutil, "which", lambda nome: "/usr/local/bin/Fakturama")
        assert ambiente.executavel_fakturama() == configurado

    def test_linux_procura_no_path(self, linux, monkeypatch):
        no_path = _executavel(linux / "bin" / "Fakturama")
        monkeypatch.setattr(ambiente.shutil, "which", lambda nome: str(no_path) if nome == "Fakturama" else None)
        assert ambiente.executavel_fakturama() == no_path

    def test_linux_procura_nos_caminhos_de_instalacao(self, linux, monkeypatch):
        instalado = _executavel(linux / "usr" / "share" / "fakturama2" / "Fakturama")
        monkeypatch.setattr(ambiente, "CAMINHOS_LINUX", [linux / "opt" / "Fakturama", instalado])
        assert ambiente.executavel_fakturama() == instalado

    def test_linux_le_o_atalho_desktop(self, linux):
        alvo = _executavel(linux / "app" / "Fakturama")
        atalho = linux / "applications" / "fakturama2.desktop"
        atalho.parent.mkdir()
        atalho.write_text(f"[Desktop Entry]\nName=Fakturama2\nExec={alvo} %U\nType=Application\n")
        assert ambiente.executavel_fakturama() == alvo

    def test_linux_ignora_arquivo_sem_permissao_de_execucao(self, linux, monkeypatch):
        sem_permissao = linux / "Fakturama"
        sem_permissao.touch(mode=0o644)
        monkeypatch.setattr(ambiente, "CAMINHOS_LINUX", [sem_permissao])
        with pytest.raises(SystemException):
            ambiente.executavel_fakturama()

    def test_linux_nao_instalado_orienta_instalar_ou_definir_fakturama_exe(self, linux):
        with pytest.raises(SystemException, match="não encontrado no Linux.*defina FAKTURAMA_EXE"):
            ambiente.executavel_fakturama()


class TestVariaveisSemSnap:
    def test_remove_o_que_o_snap_do_vscode_injeta_e_restaura_os_originais(self):
        terminal_do_vscode_snap = {
            "DISPLAY": ":0",
            "PATH": "/usr/bin:/bin",
            "SNAP": "/snap/code/263",
            "SNAP_NAME": "code",
            "GTK_PATH": "/snap/code/263/usr/lib/x86_64-linux-gnu/gtk-3.0",
            "GDK_PIXBUF_MODULEDIR": "/snap/code/263/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders",
            "XDG_DATA_DIRS": "/snap/code/263/usr/share:/usr/share",
            "XDG_DATA_DIRS_VSCODE_SNAP_ORIG": "/usr/share/zorin-xorg:/usr/share",
            "GIO_MODULE_DIR": "/home/vinicius/snap/code/common/.cache/gio-modules",
            "GIO_MODULE_DIR_VSCODE_SNAP_ORIG": "",
        }
        assert ambiente.variaveis_sem_snap(terminal_do_vscode_snap) == {
            "DISPLAY": ":0",
            "PATH": "/usr/bin:/bin",
            "XDG_DATA_DIRS": "/usr/share/zorin-xorg:/usr/share",
        }

    def test_terminal_comum_fica_igual(self):
        terminal = {"DISPLAY": ":0", "HOME": "/home/vinicius", "XDG_DATA_DIRS": "/usr/share:/var/lib/snapd/desktop"}
        assert ambiente.variaveis_sem_snap(terminal) == terminal
