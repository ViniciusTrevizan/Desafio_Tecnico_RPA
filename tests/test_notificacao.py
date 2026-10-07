"""Testes de src/core/notificacao.py — e-mail enviado quando web × desktop não batem 100%.

PDF §6: os dados precisam bater 100%; quando não batem, o responsável é avisado por e-mail
com as pendências da fila e os arquivos de conferência (resumo.json e erros.log) anexados.
"""
import logging
import smtplib
from dataclasses import asdict

import pytest

from config import settings
from src.core.notificacao import montar_email, notificar_divergencia
from src.core.relatorio import gerar_relatorio


@pytest.fixture
def credenciais(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.setattr(settings, "SMTP_PORTA", 587)
    monkeypatch.setattr(settings, "SMTP_USUARIO", "robo@exemplo.com")
    monkeypatch.setattr(settings, "SMTP_SENHA", "senha-de-app")
    monkeypatch.setattr(settings, "EMAIL_REMETENTE", "robo@exemplo.com")


@pytest.fixture
def divergente(ctx, comprador, produtos):
    """Execução em que o 'Sauce Labs Onesie' não foi cadastrado no Fakturama."""
    ctx.fila.adicionar("contato", f"{comprador.nome} {comprador.sobrenome}", asdict(comprador))
    for produto in produtos:
        ctx.fila.adicionar("produto", produto.nome, asdict(produto))
    while item := ctx.fila.proximo():
        if item.referencia == "Sauce Labs Onesie":
            ctx.fila.falhar(item, "Imagem 'campo_produto_preco' não encontrada em 15s")
        else:
            ctx.fila.concluir(item)
    (ctx.pasta_logs / "erros.log").write_text("ERROR | produto não cadastrado\n", encoding="utf-8")
    gerar_relatorio(ctx)
    return ctx


def test_destinatario_padrao_e_o_responsavel_pelo_robo():
    assert settings.EMAIL_DESTINATARIO == "vinicius_trevizan.dev@outlook.com"


def test_email_lista_pendencias_e_anexa_resumo_e_erros(divergente, credenciais):
    msg = montar_email(divergente)
    assert msg["To"] == settings.EMAIL_DESTINATARIO
    assert msg["From"] == "robo@exemplo.com"
    assert msg["Subject"] == "[RPA] Divergência na execução execucao_teste"
    corpo = msg.get_body().get_content()
    assert "não batem 100%" in corpo
    assert "produto 'Sauce Labs Onesie' → FALHA_SISTEMA Imagem 'campo_produto_preco' não encontrada" in corpo
    assert "Vitória Rocha" not in corpo  # cadastrado com sucesso não é pendência
    assert [a.get_filename() for a in msg.iter_attachments()] == ["resumo.json", "erros.log"]


def test_envia_por_smtp_com_starttls_e_login(divergente, credenciais, smtp, caplog):
    assert notificar_divergencia(divergente) is True
    smtp.assert_called_once_with("smtp.exemplo.com", 587, timeout=settings.TIMEOUT_SMTP)
    sessao = smtp.return_value.__enter__.return_value
    sessao.starttls.assert_called_once()
    sessao.login.assert_called_once_with("robo@exemplo.com", "senha-de-app")
    assert sessao.send_message.call_args.args[0]["To"] == settings.EMAIL_DESTINATARIO
    assert f"E-mail de divergência enviado para {settings.EMAIL_DESTINATARIO}" in caplog.text


def test_sem_credenciais_nao_tenta_enviar_e_avisa(divergente, monkeypatch, smtp, caplog):
    monkeypatch.setattr(settings, "SMTP_SENHA", "")
    assert notificar_divergencia(divergente) is False
    smtp.assert_not_called()
    assert any(r.levelno == logging.WARNING and "RPA_SMTP_SENHA" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("erro", [smtplib.SMTPAuthenticationError(535, b"auth failed"), OSError("sem rede")])
def test_falha_no_envio_e_registrada_sem_derrubar_o_robo(divergente, credenciais, smtp, caplog, erro):
    smtp.return_value.__enter__.return_value.login.side_effect = erro
    assert notificar_divergencia(divergente) is False
    assert any(r.levelno == logging.ERROR and "Falha ao enviar e-mail de divergência" in r.getMessage()
               for r in caplog.records)
