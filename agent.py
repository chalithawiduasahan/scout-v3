import os
import re
import asyncio
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from strands import Agent, tool
from strands.models import BedrockModel
from linkup import LinkupClient
from playwright.sync_api import sync_playwright

from tools.crm import save_lead_now, archive_lead_now, cleanup_stray_new_leads
from tools.slack import send_slack_lead_notification
from tools.hunter import find_best_contact


model = BedrockModel(
    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="us-east-1"
)

# ---------------------------------------------------------------------------
# Linkup search tools
# ---------------------------------------------------------------------------
# Discovery continues to use Linkup Standard.
#
# The selected-business research stage ALSO now uses Linkup Standard directly
# instead of Linkup Deep. This keeps the workflow focused on the small amount
# of public information Scout actually needs:
#
# - official website
# - domain
# - basic business facts
# - automation opportunity
# - email publicly listed on the business website
#
# Hunter is then used separately for personal contact enrichment.
linkup_client = LinkupClient(api_key=os.getenv("LINKUP_API_KEY"))


@tool
def linkup_search_standard(query: str) -> str:
    """Search the web for quick, standard-depth results.

    Use this for discovering businesses and lightweight web research.
    Args:
        query: The search query.
    """
    response = linkup_client.search(
        query=query,
        depth="standard",
        output_type="sourcedAnswer",
        include_images=False,
        include_inline_citations=False,
    )

    return response.answer


TALLY_FORM_URL = os.getenv("TALLY_FORM_URL")
AIRTABLE_SHARE_URL = os.getenv("AIRTABLE_SHARE_URL")


# Chromium launch args needed for hosted containers like Render.
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
]


# ---------------------------------------------------------------------------
# Plain-text sanitizer
# ---------------------------------------------------------------------------
def sanitize_plain_text(text: str) -> str:
    text = text.strip()

    lines = text.split("\n")

    while lines and not re.match(
        r"^\s*(business type|business facts|estimated scale|official website|domain|website contact email|contact email|one manual)",
        lines[0],
        re.IGNORECASE,
    ):
        if len(lines) <= 1:
            break
        lines.pop(0)

    text = "\n".join(lines).strip() or text

    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)

    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Stage 1: Discovery with Scale Criteria & Exclusions
# ---------------------------------------------------------------------------
DISCOVERY_SYSTEM_PROMPT = """You are a lead discovery assistant for an automation freelancer.

Given a business niche, location, targeted business scale, and a list of businesses to exclude:

- Small: Single-location independent businesses, boutique shops, or small local operations (<10 staff).
- Medium: Regional multi-location businesses or medium-sized teams (10-50 staff).
- Large: National chains, major franchises, or enterprise corporations (50+ staff).

Use the Linkup search tool to find REAL, currently operating businesses matching the requested niche and location.

Strictly filter candidates based on the scale category requested.

If "small" is requested, EXCLUDE large chains or well-known national franchises.

CRITICAL:
Do NOT include any business name that appears in the provided exclusion list.

Respond with ONLY a numbered list, one business name per line, in this exact format:

1. Business Name
2. Business Name
3. Business Name

No extra commentary before or after the list.
"""

discovery_agent = Agent(
    model=model,
    tools=[linkup_search_standard],
    system_prompt=DISCOVERY_SYSTEM_PROMPT,
    callback_handler=None
)


async def find_businesses(
    niche: str,
    location: str,
    scale: str = "small",
    excluded_businesses: list[str] | None = None,
) -> list[str]:
    excluded_businesses = excluded_businesses or []

    exclusion_text = (
        f"\nEXCLUDE these businesses completely "
        f"(already contacted by this user): {', '.join(excluded_businesses)}"
        if excluded_businesses
        else ""
    )

    query = (
        f"Find {scale}-scale businesses in the '{niche}' niche "
        f"located in {location}.{exclusion_text}"
    )

    response = await discovery_agent.invoke_async(query)

    text = str(response)

    names = []

    for line in text.strip().split("\n"):
        line = line.strip()

        if line and line[0].isdigit():
            name = line.split(".", 1)[-1].strip()

            if name and name not in excluded_businesses:
                names.append(name)

    return names


# ---------------------------------------------------------------------------
# Stage 2: Focused business research
# ---------------------------------------------------------------------------
# This replaces the previous Linkup Deep research stage.
#
# IMPORTANT:
# Linkup is responsible for discovering the REAL email listed publicly on
# the company's website.
#
# Hunter does NOT provide the fallback generic email.
# Hunter is only allowed to replace that website email if it finds a
# suitable personal decision-maker contact.
RESEARCH_FIELD_LABELS = [
    "Business type",
    "Business facts",
    "Estimated scale (small/medium/large)",
    "Official website",
    "Domain",
    "Website contact email",
    "One manual, repetitive customer inquiry or lead-handling task this business likely does that could be automated",
]


def _parse_research_fields(text: str) -> dict[str, str]:
    """
    Parse Linkup's labelled research response without introducing another
    LLM call.

    The parser allows fields to span multiple lines.
    """
    fields: dict[str, list[str]] = {}
    current_label: str | None = None

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()

        matched_label = None

        for label in RESEARCH_FIELD_LABELS:
            prefix = f"{label}:"

            if line.lower().startswith(prefix.lower()):
                matched_label = label
                current_label = label

                initial_value = line[len(prefix):].strip()

                if label not in fields:
                    fields[label] = []

                if initial_value:
                    fields[label].append(initial_value)

                break

        if matched_label is not None:
            continue

        if current_label and line:
            fields.setdefault(current_label, []).append(line)

    return {
        label: " ".join(values).strip()
        for label, values in fields.items()
    }


def _normalise_domain(value: str) -> str:
    if not value:
        return ""

    value = value.strip()

    if value.lower() == "not found":
        return ""

    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urlparse(value)
        domain = parsed.netloc or parsed.path.split("/")[0]
    except Exception:
        domain = value

    domain = domain.split("@")[-1]
    domain = domain.split(":")[0]
    domain = domain.removeprefix("www.")

    return domain.strip().rstrip("/")


def _normalise_website(value: str) -> str:
    if not value:
        return ""

    value = value.strip()

    if value.lower() == "not found":
        return ""

    if not value.lower().startswith(("http://", "https://")):
        value = "https://" + value

    return value


def _extract_email(value: str) -> str:
    if not value:
        return ""

    match = re.search(
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
        value
    )

    return match.group(0).strip() if match else ""


def _extract_website_email_from_linkup(
    field_value: str,
    raw_answer: str,
    domain: str,
) -> str:
    """
    Extract the email Linkup itself found publicly.

    We prefer the explicitly labelled Website contact email field.
    If that field was not parsed cleanly, we only accept an email from the
    raw answer when its domain matches the business domain.
    """
    direct_email = _extract_email(field_value)

    if direct_email:
        if not domain:
            return direct_email

        email_domain = direct_email.rsplit("@", 1)[-1].lower()

        if (
            email_domain == domain.lower()
            or email_domain.endswith("." + domain.lower())
        ):
            return direct_email

    if domain:
        raw_emails = re.findall(
            r"[\w.+-]+@[\w-]+\.[\w.-]+",
            raw_answer
        )

        for email in raw_emails:
            email_domain = email.rsplit("@", 1)[-1].lower()

            if (
                email_domain == domain.lower()
                or email_domain.endswith("." + domain.lower())
            ):
                return email.strip()

    return ""


def _run_linkup_business_research(
    business_name: str,
    location: str,
) -> str:
    """
    One direct Linkup Standard API request for the selected business.

    This deliberately does NOT use a Strands research agent because we want
    to keep the selected-business research bounded to one standard request
    rather than allowing an agent to make multiple expensive/variable search
    calls.
    """
    query = f"""
Research this specific business only:

Business: {business_name}
Location: {location}

Use the company's official website and other authoritative public web sources
where useful.

Find the following information:

Business type:
Give a concise description of what this business actually does.

Business facts:
Give the most useful concrete public facts about the business, its services,
customers, operating model, locations, or other details relevant to an
automation freelancer.

Estimated scale (small/medium/large):
Estimate the business scale using public evidence.

Official website:
Give the official company website URL. If it cannot be identified, write
Not found.

Domain:
Give the bare official company domain, for example example.com.
If it cannot be identified, write Not found.

Website contact email:
Find an email address that is actually publicly listed by this business on
its official website, such as its Contact page, About page, footer, or clearly
official contact information. This may be a generic address such as
info@example.com or a named professional address. Do NOT invent or infer an
email address. If none is publicly listed, write Not found.

One manual, repetitive customer inquiry or lead-handling task this business likely does that could be automated:
Identify one concrete customer-facing or lead-handling workflow that Scout
could plausibly automate. Base it on the business's actual services and
publicly visible workflow evidence. Do not invent internal facts that are not
supported by the public information.

Return ONLY these labelled sections:

Business type:
Business facts:
Estimated scale (small/medium/large):
Official website:
Domain:
Website contact email:
One manual, repetitive customer inquiry or lead-handling task this business likely does that could be automated:

Do not add a conversational introduction or conclusion.
"""

    response = linkup_client.search(
        query=query,
        depth="standard",
        output_type="sourcedAnswer",
        include_images=False,
        include_inline_citations=False,
    )

    return response.answer


async def research_business(
    business_name: str,
    location: str,
) -> dict:
    """
    Research one selected business with Linkup Standard, then enrich contact
    information with Hunter.

    Return a structured dictionary while preserving the existing plain-text
    research_profile used by the demo builder and Claude outreach generator.
    """
    raw_answer = await asyncio.to_thread(
        _run_linkup_business_research,
        business_name,
        location,
    )

    fields = _parse_research_fields(raw_answer)

    business_type = fields.get(
        "Business type",
        "Not enough public information found."
    )

    business_facts = fields.get(
        "Business facts",
        "Not enough public information found."
    )

    estimated_scale = fields.get(
        "Estimated scale (small/medium/large)",
        "Not enough public information found."
    )

    website = _normalise_website(
        fields.get("Official website", "")
    )

    domain = _normalise_domain(
        fields.get("Domain", "")
    )

    if not domain and website:
        domain = _normalise_domain(website)

    website_email = _extract_website_email_from_linkup(
        fields.get("Website contact email", ""),
        raw_answer,
        domain,
    )

    automation_opportunity = fields.get(
        "One manual, repetitive customer inquiry or lead-handling task this business likely does that could be automated",
        "Not enough public information was found to identify a specific automation opportunity."
    )

    # Hunter is an enrichment layer only.
    # If Hunter fails, is unavailable, or finds no suitable personal contact,
    # website_email remains the final recipient.
    hunter_contact = {}

    if domain:
        hunter_contact = await asyncio.to_thread(
            find_best_contact,
            business_name,
            domain,
            automation_opportunity,
        )

    contact_email = hunter_contact.get("contact_email") or ""
    final_recipient_email = contact_email or website_email

    research_profile = f"""Business type:
{business_type}

Business facts:
{business_facts}

Estimated scale (small/medium):
{estimated_scale}

Official website:
{website or "Not found"}

Domain:
{domain or "Not found"}

Contact email (found by Linkup on the public website):
{website_email or "Not found"}

One manual, repetitive customer inquiry or lead-handling task this business likely does that could be automated:
{automation_opportunity}
"""

    research_profile = sanitize_plain_text(research_profile)

    return {
        "research_profile": research_profile,
        "business_type": business_type,
        "business_facts": business_facts,
        "estimated_scale": estimated_scale,
        "website": website,
        "domain": domain,
        "website_email": website_email or None,
        "automation_opportunity": automation_opportunity,
        "contact_email": contact_email or None,
        "contact_name": hunter_contact.get("contact_name"),
        "contact_title": hunter_contact.get("contact_title"),
        "contact_seniority": hunter_contact.get("contact_seniority"),
        "contact_department": hunter_contact.get("contact_department"),
        "contact_confidence": hunter_contact.get("contact_confidence"),
        "contact_verification_status": hunter_contact.get("contact_verification_status"),
        "contact_source": hunter_contact.get("contact_source"),
        "recipient_email": final_recipient_email or None,
    }


# ---------------------------------------------------------------------------
# Stage 3: Build the REAL demo
# ---------------------------------------------------------------------------
DEMO_LEAD_SYSTEM_PROMPT = """Given a business's name and research about them, invent ONE realistic,
plausible customer inquiry this business might receive, along with a matching realistic customer name and fake email address.

Respond with ONLY this exact format, nothing else:
NAME: <a realistic customer name, e.g., Sarah Mitchell>
EMAIL: <a realistic fake email, e.g., sarah.mitchell@outlook.com>
INQUIRY: <the inquiry text, 1-3 sentences regarding pricing or booking>
"""

demo_lead_agent = Agent(
    model=model,
    tools=[],
    system_prompt=DEMO_LEAD_SYSTEM_PROMPT,
    callback_handler=None
)


async def invent_demo_lead(
    business_name: str,
    research_profile: str
) -> tuple[str, str, str]:
    prompt = (
        f"Business: {business_name}\n\n"
        f"Research findings:\n{research_profile}"
    )

    response = await demo_lead_agent.invoke_async(prompt)

    name = "Sarah Mitchell"
    email = "sarah.mitchell@outlook.com"

    inquiry = (
        f"Hi, I would like to inquire about your availability and package "
        f"options for an upcoming booking with {business_name}."
    )

    for line in str(response).strip().split("\n"):
        line = line.strip()

        if line.startswith("NAME:"):
            parsed_name = line.replace("NAME:", "").strip()
            if parsed_name:
                name = parsed_name

        elif line.startswith("EMAIL:"):
            parsed_email = line.replace("EMAIL:", "").strip()
            if parsed_email:
                email = parsed_email

        elif line.startswith("INQUIRY:"):
            parsed_inquiry = line.replace("INQUIRY:", "").strip()
            if parsed_inquiry:
                inquiry = parsed_inquiry

    return name, email, inquiry


DEMO_REPLY_SYSTEM_PROMPT = """You are drafting an automated reply email as if you ARE the business
being pitched to, replying to a customer's inquiry just submitted through your contact form.

Given the business's name, research about them, the customer's name, and their inquiry,
write a short, warm, professional reply in the voice of that business, referencing the
customer's specific inquiry. Keep it under 100 words.

IMPORTANT: Do NOT use markdown formatting like asterisks (**bold** or *italic*). Output pure plain text only.

Respond in this format:
SUBJECT: <subject line>
BODY: <email body>
"""

demo_reply_agent = Agent(
    model=model,
    tools=[],
    system_prompt=DEMO_REPLY_SYSTEM_PROMPT,
    callback_handler=None
)


async def draft_demo_reply(
    business_name: str,
    research_profile: str,
    customer_name: str,
    inquiry: str
) -> tuple[str, str]:
    prompt = (
        f"Business: {business_name}\n\n"
        f"Research findings:\n{research_profile}\n\n"
        f"Customer name: {customer_name}\n"
        f"Customer inquiry: {inquiry}"
    )

    response = await demo_reply_agent.invoke_async(prompt)

    res_str = str(response).strip()

    subject = f"Thank you for reaching out to {business_name}!"

    body = (
        f"Hi {customer_name},\n\n"
        f"Thank you for reaching out to {business_name}.\n\n"
        f"We received your inquiry regarding:\n"
        f"\"{inquiry}\"\n\n"
        f"Our team is reviewing your details and will follow up with you shortly.\n\n"
        f"Best regards,\n"
        f"{business_name} Customer Support"
    )

    if "SUBJECT:" in res_str and "BODY:" in res_str:
        try:
            parts = res_str.split("BODY:", 1)

            subject_part = parts[0].replace("SUBJECT:", "").strip()
            body_part = parts[1].strip()

            if subject_part:
                subject = subject_part

            if body_part:
                body = body_part

        except Exception:
            pass

    return subject, body


# ---------------------------------------------------------------------------
# Playwright demo-build helpers
# ---------------------------------------------------------------------------
def _airtable_html(name: str, email: str, inquiry: str) -> str:
    """Static mockup of the Airtable grid view."""
    from datetime import datetime, timezone

    created = datetime.now(timezone.utc).strftime(
        "%b %-d, %Y %-I:%M %p"
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f9fafb; color: #1d1f25; font-size: 13px; }}
      .topbar {{ height: 46px; background: #ffffff; border-bottom: 1px solid #e3e6eb; display: flex; align-items: center; padding: 0 16px; gap: 10px; }}
      .topbar .base-icon {{ width: 24px; height: 24px; border-radius: 6px; background: linear-gradient(135deg, #6b5ce7, #2d7ff9); display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 12px; }}
      .topbar .base-name {{ font-weight: 600; font-size: 14px; color: #1d1f25; }}
      .topbar .crumb {{ color: #8b94a3; font-size: 12px; }}
      .tabs {{ height: 40px; background: #ffffff; border-bottom: 1px solid #e3e6eb; display: flex; align-items: flex-end; padding: 0 16px; gap: 4px; }}
      .tab {{ padding: 8px 14px; font-size: 13px; color: #6b7280; border-radius: 6px 6px 0 0; }}
      .tab.active {{ color: #1d1f25; font-weight: 600; background: #f3f4f8; border: 1px solid #e3e6eb; border-bottom: 1px solid #f3f4f8; }}
      .toolbar {{ height: 44px; background: #ffffff; border-bottom: 1px solid #e3e6eb; display: flex; align-items: center; padding: 0 16px; gap: 18px; }}
      .toolbar .view-pill {{ display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #1d1f25; padding: 5px 10px; border-radius: 6px; background: #f3f4f8; }}
      .toolbar .view-pill .grid-icon {{ color: #2d7ff9; }}
      .toolbar .divider {{ width: 1px; height: 20px; background: #e3e6eb; }}
      .toolbar .tool {{ font-size: 12.5px; color: #6b7280; display: flex; align-items: center; gap: 5px; }}
      .toolbar .search {{ margin-left: auto; font-size: 12.5px; color: #8b94a3; background: #f3f4f8; padding: 5px 12px; border-radius: 6px; }}
      table {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
      thead th {{ text-align: left; background: #f7f8fa; border: 1px solid #e3e6eb; padding: 7px 12px; font-size: 12.5px; font-weight: 600; color: #4b5563; white-space: nowrap; }}
      thead th .col-icon {{ color: #9aa2b1; margin-right: 6px; font-weight: 400; }}
      tbody td {{ border: 1px solid #e3e6eb; padding: 8px 12px; color: #1d1f25; vertical-align: top; background: #ffffff; }}
      .row-num {{ width: 36px; color: #9aa2b1; background: #f7f8fa !important; text-align: center; font-size: 12px; }}
      .col-name {{ min-width: 150px; font-weight: 500; }}
      .col-email {{ min-width: 190px; color: #2d7ff9; }}
      .col-inquiry {{ min-width: 320px; color: #4b5563; }}
      .col-status {{ min-width: 110px; }}
      .col-created {{ min-width: 130px; color: #6b7280; white-space: nowrap; }}
      .status-pill {{ display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 12px; }}
      .status-new {{ background: #d9f2e3; color: #1a7f4e; }}
      .status-archived {{ background: #eceef2; color: #6b7280; }}
      .new-row td {{ background: #fffdf0 !important; }}
    </style>
    </head>
    <body>
      <div class="topbar">
        <div class="base-icon">SC</div>
        <span class="base-name">Scout Demo CRM</span>
        <span class="crumb">/ Leads</span>
      </div>
      <div class="tabs">
        <div class="tab active">Leads</div>
        <div class="tab">Businesses</div>
        <div class="tab">Outreach Log</div>
      </div>
      <div class="toolbar">
        <div class="view-pill"><span class="grid-icon">&#9638;</span> Grid view</div>
        <div class="divider"></div>
        <div class="tool">Filter</div>
        <div class="tool">Group</div>
        <div class="tool">Sort</div>
        <div class="search">Search...</div>
      </div>
      <table>
        <thead>
          <tr>
            <th class="row-num">#</th>
            <th>Name</th>
            <th>Email</th>
            <th>Inquiry</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          <tr class="new-row">
            <td class="row-num">1</td>
            <td class="col-name">{name}</td>
            <td class="col-email">{email}</td>
            <td class="col-inquiry">{inquiry}</td>
            <td class="col-status"><span class="status-pill status-new">New</span></td>
            <td class="col-created">{created}</td>
          </tr>
        </tbody>
      </table>
    </body>
    </html>
    """


def _submit_demo_form(
    page,
    name: str,
    email: str,
    inquiry: str,
    screenshot_path: str
):
    page.goto(
        TALLY_FORM_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_selector(
        "input",
        timeout=15000
    )

    page.get_by_label("Name").fill(name)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Inquiry").fill(inquiry)

    page.screenshot(
        path=screenshot_path,
        full_page=True,
        timeout=60000
    )

    page.get_by_role("button", name="Submit").click()
    page.wait_for_timeout(2000)


def _build_html_screenshot(
    page,
    html_content: str,
    screenshot_path: str
):
    page.set_content(html_content)
    page.wait_for_timeout(500)
    page.screenshot(
        path=screenshot_path,
        timeout=60000
    )


def _email_html(subject: str, body: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 40px 20px; }}
            .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #cbd5e1; box-shadow: 0 4px 12px rgba(0,0,0,0.08); overflow: hidden; color: #1e293b; }}
            .header {{ background: #f8fafc; color: #0284c7; padding: 18px 24px; font-weight: 600; font-size: 14px; border-bottom: 1px solid #e2e8f0; }}
            .content {{ padding: 24px; color: #334155; line-height: 1.6; font-size: 14px; white-space: pre-wrap; }}
            .footer {{ background: #f8fafc; padding: 14px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <span style="color: #64748b; font-weight: 400;">Subject:</span> {subject}
            </div>
            <div class="content">{body}</div>
            <div class="footer">Automated Customer Response Demo • Agents for Humans</div>
        </div>
    </body>
    </html>
    """


def _slack_html(
    business_name: str,
    customer_name: str,
    customer_email: str,
    inquiry: str
) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 40px 20px; }}
            .slack-card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #cbd5e1; box-shadow: 0 4px 12px rgba(0,0,0,0.08); overflow: hidden; color: #1e293b; }}
            .slack-header {{ background: #f8fafc; color: #4a154b; padding: 18px 24px; font-weight: 600; font-size: 14px; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-between; }}
            .channel-tag {{ background: #f4ede4; color: #4a154b; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }}
            .slack-body {{ padding: 24px; color: #334155; line-height: 1.6; font-size: 14px; }}
            .alert-title {{ font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 8px; }}
            .field-group {{ background: #f8fafc; padding: 14px 18px; border-radius: 8px; margin-top: 12px; border: 1px solid #e2e8f0; border-left: 4px solid #2eb67d; }}
            .field-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
            .field-val {{ font-size: 14px; color: #1e293b; margin-top: 2px; }}
            .inquiry-box {{ margin-top: 8px; font-style: italic; color: #475569; }}
            .slack-footer {{ background: #f8fafc; padding: 14px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="slack-card">
            <div class="slack-header">
                <span>Slack Notification</span>
                <span class="channel-tag"># leads-incoming</span>
            </div>
            <div class="slack-body">
                <div class="alert-title">🚨 New Potential Lead Captured for {business_name}!</div>
                <p style="margin: 0 0 12px 0;">A prospective client just submitted your contact form.</p>

                <div class="field-group">
                    <div class="field-label">Prospect Details</div>
                    <div class="field-val"><strong>{customer_name}</strong> ({customer_email})</div>
                    <div class="inquiry-box">"{inquiry}"</div>
                </div>
            </div>
            <div class="slack-footer">
                ⚡ Automated Slack Alert Demo • Agents for Humans
            </div>
        </div>
    </body>
    </html>
    """


def build_demo_screenshots_sync(
    name: str,
    email: str,
    inquiry: str,
    form_screenshot: str,
    airtable_screenshot: str,
    email_subject: str,
    email_body: str,
    email_screenshot: str,
    business_name: str,
    slack_screenshot: str,
) -> None:
    """Build all 4 screenshots using one shared Chromium instance."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS
        )

        try:
            page = browser.new_page()

            try:
                _submit_demo_form(
                    page,
                    name,
                    email,
                    inquiry,
                    form_screenshot,
                )
            finally:
                page.close()

            page = browser.new_page()

            try:
                _build_html_screenshot(
                    page,
                    _airtable_html(name, email, inquiry),
                    airtable_screenshot,
                )
            finally:
                page.close()

            page = browser.new_page()

            try:
                _build_html_screenshot(
                    page,
                    _email_html(email_subject, email_body),
                    email_screenshot,
                )
            finally:
                page.close()

            page = browser.new_page()

            try:
                _build_html_screenshot(
                    page,
                    _slack_html(
                        business_name,
                        name,
                        email,
                        inquiry,
                    ),
                    slack_screenshot,
                )
            finally:
                page.close()

        finally:
            browser.close()


async def build_real_demo(
    business_name: str,
    research_profile: str
) -> dict:
    os.makedirs("screenshots", exist_ok=True)

    safe_name = (
        business_name
        .replace(" ", "_")
        .replace("/", "_")
    )

    name, fake_email, inquiry = await invent_demo_lead(
        business_name,
        research_profile,
    )

    form_screenshot = (
        f"screenshots/{safe_name}_form.png"
    )

    airtable_screenshot = (
        f"screenshots/{safe_name}_airtable.png"
    )

    email_screenshot = (
        f"screenshots/{safe_name}_email.png"
    )

    slack_screenshot = (
        f"screenshots/{safe_name}_slack.png"
    )

    subject, body = await draft_demo_reply(
        business_name,
        research_profile,
        name,
        inquiry,
    )

    record_id = save_lead_now(
        name,
        fake_email,
        inquiry,
    )

    await asyncio.to_thread(
        cleanup_stray_new_leads,
        record_id
    )

    await asyncio.to_thread(
        build_demo_screenshots_sync,
        name,
        fake_email,
        inquiry,
        form_screenshot,
        airtable_screenshot,
        subject,
        body,
        email_screenshot,
        business_name,
        slack_screenshot,
    )

    archive_lead_now(record_id)

    send_slack_lead_notification(
        business_name,
        name,
        fake_email,
        inquiry,
    )

    return {
        "lead_name": name,
        "lead_email": fake_email,
        "inquiry": inquiry,
        "form_screenshot": form_screenshot,
        "airtable_screenshot": airtable_screenshot,
        "email_screenshot": email_screenshot,
        "slack_screenshot": slack_screenshot,
    }


# ---------------------------------------------------------------------------
# Stage 4: Short & High-Converting Pitch Drafting
# ---------------------------------------------------------------------------
# IMPORTANT:
# This prompt intentionally remains the existing outreach architecture.
# The research/contact pipeline above changes, but the Claude outreach
# generation itself is left intact.
OUTREACH_SYSTEM_PROMPT = """You are an elite B2B automation freelancer writing a quick, high-converting cold email to a business owner.

Keep the email SHORT, warm, and natural (under 100 words total).

Structure:
1. Short, friendly opening referencing their business.
2. Mention that manual customer follow-ups and lead logging often take up hours of time.
3. State that you built a quick functional automation prototype for them (referencing the 4 attached screenshots: Tally Contact Form, Airtable CRM Record, Auto-reply Email, and Slack Team Notification).
4. Direct soft CTA: Ask if they have 5 minutes for a quick demo call or want to automate other manual tasks.

RULES:
- Do NOT use markdown formatting like asterisks (**bold** or *italic*). Output pure plain text only.
- Keep sentences short and direct.
- End the sign-off strictly with:
Best regards,
[User Name]

Respond in this format:
SUBJECT: <subject line>
BODY: <email body>
"""

outreach_agent = Agent(
    model=model,
    tools=[],
    system_prompt=OUTREACH_SYSTEM_PROMPT,
    callback_handler=None
)


async def draft_outreach_pitch(
    business_name: str,
    research_profile: str
) -> tuple[str, str]:
    prompt = (
        f"Business Name: {business_name}\n"
        f"Research Profile:\n{research_profile}"
    )

    response = await outreach_agent.invoke_async(prompt)

    res_str = str(response).strip()

    subject = (
        f"Quick automation concept for {business_name}"
    )

    body = (
        f"Hi,\n\n"
        f"I came across {business_name} and put together "
        f"a quick live prototype to automate your client "
        f"intake and follow-ups.\n\n"
        f"I attached 4 quick screenshots showing how it works:\n"
        f"1. Contact form where customers submit details\n"
        f"2. Airtable database recording leads instantly\n"
        f"3. Instant custom auto-reply email to the client\n"
        f"4. Slack notification sent directly to your team\n\n"
        f"This saves 5-10 hours a week on repetitive "
        f"follow-ups. Would you be open to a 5-minute "
        f"call this week to see it live?\n\n"
        f"Best regards,\n"
        f"[User Name]"
    )

    if "SUBJECT:" in res_str and "BODY:" in res_str:
        try:
            parts = res_str.split("BODY:", 1)

            subject_part = (
                parts[0]
                .replace("SUBJECT:", "")
                .strip()
            )

            body_part = parts[1].strip()

            if subject_part:
                subject = subject_part

            if body_part:
                body = body_part

        except Exception:
            pass

    return subject, body