"""Sending email. One entry point, `send_email`, behind a switchable backend.

* `console` (default): sends nothing. In dev mode the message body is logged so you can copy a code.
* `smtp`: delivers through any SMTP provider, with TLS (STARTTLS on 587, or SSL on 465) and optional login.

Nothing here ever logs a one-time code outside dev mode, and a failed send raises `EmailError` with a
message that is safe to log (it never contains the password).
"""

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from app.core.config import settings

logger = logging.getLogger("campusbid.mail")


class EmailError(Exception):
    """The message could not be delivered to the mail server."""


def build_message(to: str, subject: str, text: str, html_body: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to  # header injection is impossible: EmailMessage refuses newlines in header values
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    domain = parseaddr(settings.email_from)[1].rpartition("@")[2] or "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def _send_smtp(msg: EmailMessage) -> None:
    host, port = settings.smtp_host, settings.smtp_port
    context = ssl.create_default_context()
    try:
        if settings.smtp_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=settings.smtp_timeout, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=settings.smtp_timeout)
        with server:
            server.ehlo()
            if settings.smtp_starttls and not settings.smtp_ssl:
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError(f"The mail server rejected the username or password ({e.smtp_code})") from e
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Could not send through {host}:{port}: {type(e).__name__}: {e}") from e


def send_email(to: str, subject: str, text: str, html_body: str | None = None) -> None:
    msg = build_message(to, subject, text, html_body)
    if settings.email_backend == "smtp":
        _send_smtp(msg)
        logger.info("Sent an email to %s", to)  # the subject can carry a code: never log it
        return
    if settings.dev_mode:
        logger.warning("[DEV] Email to %s: %s\n%s", to, subject, text)
    else:
        logger.warning("EMAIL_BACKEND is 'console': nothing was sent to %s", to)


# --- the messages ------------------------------------------------------------


def _wrap(heading: str, lines: list[str], code: str | None = None, link: tuple[str, str] | None = None) -> tuple[str, str]:
    """(plain text, html) with the same content. Everything dynamic is escaped for the HTML version.
    `link` is (label, url): a button-style link in the HTML, and "label: url" in the plain text."""
    link_text = [f"{link[0]}: {link[1]}"] if link else []
    text = "\n\n".join([heading, *([f"    {code}"] if code else []), *lines, *link_text, "Relay"])
    box = (
        f'<p style="font-size:30px;letter-spacing:8px;font-weight:700;margin:20px 0;'
        f'padding:14px 18px;background:#f1f5f9;border-radius:10px;display:inline-block">{html.escape(code)}</p>'
        if code
        else ""
    )
    body = "".join(f'<p style="margin:0 0 12px">{html.escape(line)}</p>' for line in lines)
    if link:
        body += (
            f'<p style="margin:18px 0"><a href="{html.escape(link[1], quote=True)}" style="background:#1d4ed8;color:#fff;'
            f'padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600">{html.escape(link[0])}</a></p>'
        )
    page = (
        '<div style="font-family:Inter,Arial,sans-serif;color:#0f172a;max-width:480px;margin:0 auto;padding:24px">'
        f'<h2 style="margin:0 0 12px">{html.escape(heading)}</h2>{box}{body}'
        '<p style="color:#64748b;font-size:13px;margin-top:24px">Relay, the campus auction marketplace</p></div>'
    )
    return text, page


def verification_email(code: str, minutes: int) -> tuple[str, str, str]:
    text, page = _wrap(
        "Verify your campus email",
        [f"Enter this code in Relay to finish setting up your account. It expires in {minutes} minutes.",
         "If you didn't create an account, you can ignore this email."],
        code,
    )
    return f"Your Relay verification code: {code}", text, page


def password_reset_email(code: str, minutes: int) -> tuple[str, str, str]:
    text, page = _wrap(
        "Reset your password",
        [f"Use this code to choose a new password. It expires in {minutes} minutes.",
         "If you didn't ask to reset your password, ignore this email: your password has not changed."],
        code,
    )
    return f"Your Relay password reset code: {code}", text, page


def password_changed_email() -> tuple[str, str, str]:
    text, page = _wrap(
        "Your password was changed",
        ["Your Relay password was just changed and your other devices were signed out.",
         "If this wasn't you, reset your password right away and contact campus support."],
    )
    return "Your Relay password was changed", text, page


# --- how auctions and sales turn out ----------------------------------------------------------------------------


def _rupees(amount: int) -> str:
    return f"₹{amount:,}"


def _person_line(role: str, name: str, phone: str | None) -> str:
    if phone:
        return f"{role}: {name}, mobile {phone}"
    return f"{role}: {name} hasn't added a mobile number, so arrange the handover in person at the meet-up spot."


def auction_won_email(title: str, price: int, seller_name: str, handover_spot: str | None, url: str) -> tuple[str, str, str]:
    lines = [
        f"Congratulations! Your bid of {_rupees(price)} was the highest when the auction ended.",
        f"It's provisional until the seller, {seller_name}, approves the sale. You'll get another email with their contact "
        "details as soon as they do.",
    ]
    if handover_spot:
        lines.append(f"Planned handover spot: {handover_spot}.")
    text, page = _wrap(f"You won {title}", lines, link=("View the auction", url))
    return f"You won {title} for {_rupees(price)}", text, page


def auction_ended_seller_email(title: str, price: int, winner_name: str, url: str) -> tuple[str, str, str]:
    lines = [
        f"The auction ended with a top bid of {_rupees(price)} from {winner_name}.",
        "Open the sale to approve or reject it. The winner's contact details are shared with you once you approve.",
    ]
    text, page = _wrap(f"{title} has ended", lines, link=("Review the sale", url))
    return f"{title} ended at {_rupees(price)}: approve or reject the sale", text, page


def sale_approved_buyer_email(
    title: str, price: int, seller_name: str, seller_phone: str | None, handover_spot: str | None, url: str
) -> tuple[str, str, str]:
    lines = [
        f"{seller_name} approved your winning bid of {_rupees(price)}.",
        _person_line("Seller", seller_name, seller_phone),
    ]
    if handover_spot:
        lines.append(f"Meet at: {handover_spot}.")
    lines.append("Meet in daylight in a public campus spot, and check the item before you pay.")
    text, page = _wrap(f"Sale approved: {title}", lines, link=("Open the listing", url))
    return f"Sale approved: {title}", text, page


def sale_approved_seller_email(
    title: str, price: int, buyer_name: str, buyer_phone: str | None, handover_spot: str | None, url: str
) -> tuple[str, str, str]:
    lines = [
        f"You approved the sale of {title} for {_rupees(price)}.",
        _person_line("Buyer", buyer_name, buyer_phone),
    ]
    if handover_spot:
        lines.append(f"Meet at: {handover_spot}.")
    lines.append("After the handover, mark it as handed over in My listings.")
    text, page = _wrap(f"Sale approved: {title}", lines, link=("Open My listings", url))
    return f"Contact details for {title}", text, page


def sale_rejected_email(title: str, note: str, url: str) -> tuple[str, str, str]:
    text, page = _wrap(
        f"The sale of {title} did not go ahead",
        [f"{note}", "Your bid no longer applies. Other auctions are still open."],
        link=("Browse auctions", url),
    )
    return f"The sale of {title} did not go ahead", text, page
