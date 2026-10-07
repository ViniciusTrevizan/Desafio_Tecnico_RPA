"""Notificação por e-mail quando a conferência final aponta divergência entre web e desktop."""
import smtplib
import ssl
from email.message import EmailMessage

from config import settings
from src.core.contexto import Contexto
from src.core.fila import Status
from src.core.logger import get_logger

log = get_logger()


def montar_email(ctx: Contexto) -> EmailMessage:
    """Monta o e-mail com as pendências da fila e anexa resumo.json e erros.log."""
    pendencias = [f"  • {item.tipo} '{item.referencia}' → {item.status} {item.erro or ''}".rstrip()
                  for item in ctx.fila.itens() if item.status != Status.SUCESSO]
    corpo = "\n".join([
        f"A execução {ctx.run_id} do RPA Sauce Demo → Fakturama terminou com DIVERGÊNCIA:",
        "os dados coletados na web não batem 100% com o que foi cadastrado no Fakturama.",
        "",
        "Itens não cadastrados:" if pendencias else "Nenhuma pendência na fila (divergência nas contagens).",
        *pendencias,
        "",
        f"Resultados: {ctx.pasta}",
        "Em anexo: resumo.json e erros.log.",
    ])

    msg = EmailMessage()
    msg["Subject"] = f"[RPA] Divergência na execução {ctx.run_id}"
    msg["From"] = settings.EMAIL_REMETENTE
    msg["To"] = settings.EMAIL_DESTINATARIO
    msg.set_content(corpo)
    for anexo in (ctx.arquivo_resumo, ctx.pasta_logs / "erros.log"):
        if anexo.exists():
            msg.add_attachment(anexo.read_bytes(), maintype="text", subtype="plain", filename=anexo.name)
    return msg


def notificar_divergencia(ctx: Contexto) -> bool:
    """Envia o e-mail de divergência; uma falha no envio é registrada, nunca derruba o robô."""
    destino = settings.EMAIL_DESTINATARIO
    if not (settings.SMTP_USUARIO and settings.SMTP_SENHA):
        log.warning(f"E-mail de divergência NÃO enviado para {destino}: "
                    "defina RPA_SMTP_USUARIO e RPA_SMTP_SENHA")
        return False

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORTA, timeout=settings.TIMEOUT_SMTP) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
            smtp.send_message(montar_email(ctx))
    except (smtplib.SMTPException, OSError) as erro:
        log.error(f"Falha ao enviar e-mail de divergência para {destino}: {erro}")
        return False

    log.info(f"E-mail de divergência enviado para {destino}")
    return True
