"""
Service Email — Gmail SMTP
Envoi notifications création de compte et reset mot de passe
"""
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from loguru import logger
from backend.config import settings


async def send_email(to: str, subject: str, html_body: str):
    """Envoie un email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.mail_username,
            password=settings.mail_password,
        )
        logger.info(f"[Email] Envoyé à {to} — {subject}")
        return True
    except Exception as e:
        logger.error(f"[Email] Erreur envoi à {to}: {e}")
        return False


async def send_account_created(email: str, full_name: str, password: str):
    """Email de bienvenue lors de la création d'un compte."""
    subject = "Votre accès — Système d'archivage NouvelAir MRO"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #f5f7fa; border-radius: 10px;">
        <div style="background: #1a3a6b; padding: 20px; border-radius: 8px; text-align: center;">
            <h1 style="color: white; margin: 0;">✈ NouvelAir MRO</h1>
            <p style="color: #a8c4e8; margin: 5px 0;">Système d'Archivage Intelligent</p>
        </div>
        <div style="background: white; padding: 30px; border-radius: 8px; margin-top: 15px;">
            <h2 style="color: #1a3a6b;">Bienvenue, {full_name} !</h2>
            <p style="color: #444;">Un compte a été créé pour vous sur le système d'archivage NouvelAir MRO.</p>
            <div style="background: #f0f4ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #1a3a6b;">
                <p style="margin: 5px 0;"><strong>Email :</strong> {email}</p>
                <p style="margin: 5px 0;"><strong>Mot de passe temporaire :</strong> <code style="background: #e8eeff; padding: 3px 8px; border-radius: 4px; font-size: 16px;">{password}</code></p>
            </div>
            <p style="color: #e74c3c;"><strong>⚠ Vous devrez changer votre mot de passe lors de votre première connexion.</strong></p>
            <div style="text-align: center; margin-top: 25px;">
                <a href="https://archive-mro-nouvelair.vercel.app" 
                   style="background: #1a3a6b; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; font-weight: bold;">
                    Accéder au système
                </a>
            </div>
        </div>
        <p style="text-align: center; color: #888; font-size: 12px; margin-top: 15px;">
            NouvelAir MRO — Système d'Archivage Intelligent © 2026
        </p>
    </div>
    """
    return await send_email(email, subject, html)


async def send_password_changed(email: str, full_name: str):
    """Email de confirmation après changement de mot de passe."""
    subject = "Mot de passe modifié — NouvelAir MRO"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #f5f7fa; border-radius: 10px;">
        <div style="background: #1a3a6b; padding: 20px; border-radius: 8px; text-align: center;">
            <h1 style="color: white; margin: 0;">✈ NouvelAir MRO</h1>
        </div>
        <div style="background: white; padding: 30px; border-radius: 8px; margin-top: 15px;">
            <h2 style="color: #27ae60;">✓ Mot de passe modifié</h2>
            <p style="color: #444;">Bonjour {full_name},</p>
            <p style="color: #444;">Votre mot de passe a été modifié avec succès.</p>
            <p style="color: #e74c3c;">Si vous n'êtes pas à l'origine de cette modification, contactez immédiatement l'administrateur.</p>
        </div>
    </div>
    """
    return await send_email(email, subject, html)