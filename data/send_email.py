"""Send the Daybreak report via SendGrid with PDF attachment."""

import base64
import logging
from pathlib import Path

import sendgrid
from sendgrid.helpers.mail import (
    Attachment, Disposition, FileContent, FileName, FileType, Mail,
)

logger = logging.getLogger(__name__)


def send_report(
    sg_api_key: str,
    from_email: str,
    to_emails: list[str],
    report_date: str,
    html_body: str,
    pdf_path: Path,
) -> None:
    """
    Send the Daybreak Edition email via SendGrid.

    Args:
        sg_api_key:  SendGrid API key
        from_email:  Verified sender address in SendGrid
        to_emails:   List of recipient addresses
        report_date: Human-readable date string for the subject line
        html_body:   Full HTML content for the email body
        pdf_path:    Path to the generated PDF file to attach
    """
    subject = f"Framework Foundry Daybreak Edition — {report_date}"

    message = Mail(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_body,
    )

    # Attach PDF
    pdf_data = pdf_path.read_bytes()
    encoded = base64.b64encode(pdf_data).decode()
    message.attachment = Attachment(
        FileContent(encoded),
        FileName(pdf_path.name),
        FileType("application/pdf"),
        Disposition("attachment"),
    )

    client = sendgrid.SendGridAPIClient(api_key=sg_api_key)
    try:
        response = client.send(message)
        logger.info(
            f"Email sent — HTTP {response.status_code} "
            f"to: {', '.join(to_emails)}"
        )
    except Exception as e:
        body = getattr(getattr(e, "body", None), "decode", lambda: str(e))()
        raise RuntimeError(f"SendGrid {getattr(e, 'status_code', '')} — {body}") from e
