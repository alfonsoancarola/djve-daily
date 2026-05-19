"""DJVE email sender — SMTP via Gmail.

Loads config from .djve_env in the project root and sends the latest PDF
as attachment. Used as the last step of run_daily.py.

Config file format (.djve_env):
    SMTP_USER=alfonso.ancarola@gmail.com
    SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=465
    EMAIL_FROM_NAME=Informe DJVE
    EMAIL_SUBJECT_PREFIX=Informe DJVE
    EMAIL_RECIPIENTS=foo@bar.com,baz@qux.com
"""
import os, sys, ssl, smtplib, mimetypes
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


def load_env(env_path: Path) -> dict:
    """Parse a simple KEY=value .env file."""
    cfg = {}
    if not env_path.exists():
        print(f"   [WARN] No se encontró {env_path}")
        return cfg
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def send_report(pdf_path: Path, env_path: Path, summary: dict | None = None) -> bool:
    """Send the PDF report. Returns True on success."""
    cfg = load_env(env_path)
    required = ['SMTP_USER', 'SMTP_APP_PASSWORD', 'EMAIL_RECIPIENTS']
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(f"   [ERROR] Faltan claves en .djve_env: {missing}")
        return False
    if not pdf_path.exists():
        print(f"   [ERROR] PDF no encontrado: {pdf_path}")
        return False

    recipients = [r.strip() for r in cfg['EMAIL_RECIPIENTS'].split(',') if r.strip()]
    if not recipients:
        print("   [ERROR] EMAIL_RECIPIENTS vacío")
        return False

    today_str = datetime.now().strftime('%d/%m/%Y')
    subject = f"{cfg.get('EMAIL_SUBJECT_PREFIX', 'Informe DJVE')} — {today_str}"

    # Minimal plain-text body
    if summary:
        body = (
            f"Adjunto informe diario DJVE (Declaraciones Juradas de Ventas al Exterior — Ley 21.453) "
            f"del {summary.get('fecha_registro', today_str)}.\n\n"
            f"Total: {summary.get('total_djve','-')} DJVE · {summary.get('total_ton_fmt','-')} t · "
            f"{summary.get('n_shippers','-')} shippers.\n"
            f"Top: {summary.get('top_prod','-')} ({summary.get('top_prod_pct','-')}) · "
            f"Top shipper: {summary.get('top_shipper','-')}.\n\n"
            f"Fuente: MAGyP. Informe automático."
        )
    else:
        body = f"Adjunto informe diario DJVE del {today_str}.\n\nFuente: MAGyP."

    msg = EmailMessage()
    msg['From'] = f"{cfg.get('EMAIL_FROM_NAME', 'Informe DJVE')} <{cfg['SMTP_USER']}>"
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.set_content(body)

    # Attach PDF
    with open(pdf_path, 'rb') as f:
        msg.add_attachment(
            f.read(),
            maintype='application',
            subtype='pdf',
            filename=pdf_path.name,
        )

    host = cfg.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(cfg.get('SMTP_PORT', '465'))
    user = cfg['SMTP_USER']
    # Pass the app password exactly as stored — Gmail accepts both formats but is finicky
    pwd = cfg['SMTP_APP_PASSWORD']

    try:
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                server.login(user, pwd)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(user, pwd)
                server.send_message(msg)
        print(f"   ✔ Mail enviado a {len(recipients)} destinatario(s): {', '.join(recipients)}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"   [ERROR] Autenticación SMTP falló: {e}")
        print("   Verificá que la App Password sea correcta y que 2FA esté activa.")
        return False
    except Exception as e:
        print(f"   [ERROR] Envío SMTP falló: {type(e).__name__}: {e}")
        return False


if __name__ == '__main__':
    # Standalone test mode
    base = Path(__file__).resolve().parent.parent
    pdf = base / 'Informe_DJVE_Aprobadas.pdf'
    env = base / '.djve_env'
    ok = send_report(pdf, env)
    sys.exit(0 if ok else 1)
