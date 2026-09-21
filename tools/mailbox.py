import mimetypes
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any, Dict, List, Optional


def _normalise_inline_image(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "path": spec.get("path") or "",
        "cid": spec.get("cid") or "",
        "alt": spec.get("alt") or "Scout proof",
        "caption": spec.get("caption") or "",
        "link_url": spec.get("link_url") or "",
    }


def _build_html_email(
    body: str,
    inline_images: Optional[List[Dict[str, Any]]] = None,
) -> str:
    safe_body = escape(body).replace("\n", "<br>\n")

    image_blocks: List[str] = []

    for raw_spec in inline_images or []:
        spec = _normalise_inline_image(raw_spec)

        if not spec["path"] or not os.path.exists(spec["path"]):
            continue

        image_tag = (
            f'<img src="cid:{escape(spec["cid"])}" '
            f'alt="{escape(spec["alt"])}" '
            'style="display:block;width:100%;height:auto;'
            'border:0;border-radius:12px;" />'
        )

        if spec["link_url"]:
            image_tag = (
                f'<a href="{escape(spec["link_url"], quote=True)}" '
                'style="text-decoration:none;">'
                f"{image_tag}</a>"
            )

        caption_html = (
            f'<div style="font-family:Arial,Helvetica,sans-serif;'
            f'font-size:13px;line-height:1.4;color:#64748b;'
            f'margin-top:8px;">{escape(spec["caption"])}</div>'
            if spec["caption"]
            else ""
        )

        image_blocks.append(
            '<div style="margin:0 0 24px 0;">'
            f"{image_tag}"
            f"{caption_html}"
            "</div>"
        )

    proof_section = ""

    if image_blocks:
        proof_section = (
            '<div style="margin-top:28px;padding-top:24px;'
            'border-top:1px solid #e2e8f0;">'
            '<div style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:12px;font-weight:700;letter-spacing:.08em;'
            'text-transform:uppercase;color:#94a3b8;margin-bottom:16px;">'
            'Scout proof'
            '</div>'
            + "".join(image_blocks)
            + "</div>"
        )

    return f"""
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f8fafc;">
    <div style="max-width:680px;margin:0 auto;background:#ffffff;
                border:1px solid #e2e8f0;border-radius:16px;
                padding:28px;box-sizing:border-box;">
      <div style="font-family:Arial,Helvetica,sans-serif;
                  font-size:15px;line-height:1.65;color:#1e293b;">
        {safe_body}
      </div>
      {proof_section}
    </div>
  </body>
</html>
""".strip()


def _attach_inline_image(
    message: MIMEMultipart,
    spec: Dict[str, Any],
) -> None:
    path = spec.get("path") or ""
    cid = spec.get("cid") or ""

    if not path or not cid or not os.path.exists(path):
        return

    content_type, _ = mimetypes.guess_type(path)
    subtype = None

    if content_type and content_type.startswith("image/"):
        subtype = content_type.split("/", 1)[1]

    with open(path, "rb") as file:
        image_data = file.read()

    if subtype:
        image = MIMEImage(image_data, _subtype=subtype)
    else:
        image = MIMEImage(image_data)

    image.add_header("Content-ID", f"<{cid}>")
    image.add_header(
        "Content-Disposition",
        "inline",
        filename=os.path.basename(path),
    )

    message.attach(image)


def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    sender_email: str,
    app_password: str,
    attachment_paths: Optional[List[str]] = None,
    inline_images: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Send an email through the sender's own Gmail mailbox via SMTP.

    The existing attachment_paths argument is retained for backward
    compatibility, but Scout's live outreach path now uses inline_images.
    """

    # If a legacy caller still supplies attachment paths, convert those
    # images to inline images rather than creating downloadable attachments.
    merged_inline_images = list(inline_images or [])

    if attachment_paths:
        for index, path in enumerate(attachment_paths):
            if not path:
                continue

            merged_inline_images.append(
                {
                    "path": path,
                    "cid": f"legacy-scout-proof-{index}",
                    "alt": os.path.basename(path),
                    "caption": os.path.basename(path),
                }
            )

    html_body = _build_html_email(
        body=body,
        inline_images=merged_inline_images,
    )

    root = MIMEMultipart("related")
    root["Subject"] = subject
    root["From"] = sender_email
    root["To"] = to_email

    alternative = MIMEMultipart("alternative")
    alternative.attach(
        MIMEText(body, "plain", "utf-8")
    )
    alternative.attach(
        MIMEText(html_body, "html", "utf-8")
    )

    root.attach(alternative)

    for spec in merged_inline_images:
        _attach_inline_image(root, spec)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_email, app_password)
        smtp.sendmail(
            sender_email,
            [to_email],
            root.as_string(),
        )

    return (
        f"Email sent to {to_email} via {sender_email}'s mailbox "
        f"with inline proof images"
    )


def verify_mailbox_credentials(
    sender_email: str,
    app_password: str,
) -> None:
    """Raises an exception if the Gmail address + App Password can't authenticate."""

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_email, app_password)
