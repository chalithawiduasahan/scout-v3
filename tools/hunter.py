import os
import re
import requests
from typing import Any, Dict, Optional


HUNTER_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"

# Roles that are generally more useful for a business automation outreach.
# These are only used as a ranking signal after Hunter has returned
# actual personal contacts.
HIGH_LEVEL_ROLE_KEYWORDS = [
    "founder",
    "co-founder",
    "owner",
    "chief executive",
    "ceo",
    "managing director",
    "executive director",
    "director",
    "partner",
    "principal",
    "general manager",
    "head of",
    "operations manager",
    "marketing manager",
    "sales manager",
    "business development",
]

SENIORITY_SCORE = {
    "executive": 300,
    "senior": 200,
    "junior": 50,
}


def _normalize_domain(value: Optional[str]) -> str:
    """Normalize a website/domain into a bare domain name."""
    if not value:
        return ""

    value = value.strip().lower()

    # Strip common surrounding punctuation.
    value = value.strip(" <>\"'")

    # Add a scheme so url parsing works even when the model returned
    # something like www.example.com instead of https://www.example.com.
    if "://" not in value:
        value = "https://" + value

    try:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        domain = parsed.netloc or parsed.path.split("/")[0]
    except Exception:
        domain = value

    domain = domain.split("@")[-1]
    domain = domain.split(":")[0]
    domain = domain.removeprefix("www.")

    return domain.strip().rstrip("/")


def _valid_email(value: Optional[str]) -> bool:
    if not value:
        return False

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            value.strip()
        )
    )


def _position_score(position: Optional[str]) -> int:
    """Give higher scores to senior roles likely to have buying authority."""
    if not position:
        return 0

    position_lower = position.lower()
    score = 0

    for keyword in HIGH_LEVEL_ROLE_KEYWORDS:
        if keyword in position_lower:
            # Earlier entries are generally more senior/useful, but any
            # recognized high-level role gets a meaningful boost.
            score = max(score, 150)

    return score


def _candidate_score(candidate: Dict[str, Any]) -> int:
    """
    Rank an actual Hunter personal contact.

    Decision maker status is the strongest signal, followed by seniority,
    role relevance, verification status, confidence, and having a real name.
    """
    score = 0

    if candidate.get("decision_maker") is True:
        score += 1000

    seniority = str(candidate.get("seniority") or "").lower()
    score += SENIORITY_SCORE.get(seniority, 0)

    score += _position_score(
        candidate.get("position")
        or candidate.get("position_raw")
    )

    verification = candidate.get("verification") or {}
    verification_status = str(
        verification.get("status") or ""
    ).lower()

    if verification_status == "valid":
        score += 100

    elif verification_status == "accept_all":
        score += 40

    confidence = candidate.get("confidence")
    try:
        score += int(confidence or 0)
    except (TypeError, ValueError):
        pass

    first_name = candidate.get("first_name")
    last_name = candidate.get("last_name")

    if first_name or last_name or candidate.get("full_name"):
        score += 20

    return score


def find_best_contact(
    business_name: str,
    domain: str,
    automation_opportunity: str = "",
) -> Dict[str, Any]:
    """
    Use Hunter Domain Search to find a suitable personal contact.

    IMPORTANT:
    - This function only returns a personal email.
    - It does NOT fall back to a generic Hunter email.
    - If no suitable personal contact is found, it returns an empty dict.
      The caller then uses the exact website email discovered by Linkup.

    Hunter's Domain Search endpoint is deliberately called only once with
    personal + decision-maker filters to keep the enrichment stage bounded.
    """
    api_key = os.getenv("HUNTER_API_KEY")

    if not api_key:
        print("Hunter enrichment skipped: HUNTER_API_KEY is not configured.")
        return {}

    normalized_domain = _normalize_domain(domain)

    if not normalized_domain:
        print(
            f"Hunter enrichment skipped for '{business_name}': "
            "no usable domain was found."
        )
        return {}

    params = {
        "domain": normalized_domain,
        "company": business_name,
        "type": "personal",
        "decision_maker": "true",
        "limit": 5,
    }

    headers = {
        "X-API-KEY": api_key,
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            HUNTER_DOMAIN_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=15,
        )
    except requests.RequestException as exc:
        print(
            f"Hunter enrichment request failed for '{business_name}': {exc}"
        )
        return {}

    if response.status_code != 200:
        print(
            f"Hunter enrichment returned HTTP {response.status_code} "
            f"for '{business_name}': {response.text[:500]}"
        )
        return {}

    try:
        payload = response.json()
    except ValueError:
        print(
            f"Hunter enrichment returned invalid JSON for '{business_name}'."
        )
        return {}

    data = payload.get("data") or {}
    emails = data.get("emails") or []

    if not isinstance(emails, list):
        return {}

    candidates = []

    for email_record in emails:
        if not isinstance(email_record, dict):
            continue

        email_value = str(email_record.get("value") or "").strip()

        if not _valid_email(email_value):
            continue

        # We only want genuine personal contacts from Hunter.
        if str(email_record.get("type") or "").lower() != "personal":
            continue

        # Do not use an explicitly invalid address.
        verification = email_record.get("verification") or {}
        verification_status = str(
            verification.get("status") or ""
        ).lower()

        if verification_status == "invalid":
            continue

        candidate = dict(email_record)
        candidate["_score"] = _candidate_score(candidate)
        candidates.append(candidate)

    if not candidates:
        print(
            f"Hunter found no suitable personal decision-maker for "
            f"'{business_name}' ({normalized_domain})."
        )
        return {}

    best = max(candidates, key=lambda item: item["_score"])

    first_name = str(best.get("first_name") or "").strip()
    last_name = str(best.get("last_name") or "").strip()

    contact_name = str(best.get("full_name") or "").strip()

    if not contact_name:
        contact_name = " ".join(
            part for part in [first_name, last_name] if part
        ).strip()

    contact_title = str(
        best.get("position")
        or best.get("position_raw")
        or ""
    ).strip()

    verification = best.get("verification") or {}

    return {
        "contact_email": str(best.get("value") or "").strip(),
        "contact_name": contact_name or None,
        "contact_title": contact_title or None,
        "contact_seniority": (
            str(best.get("seniority")).strip()
            if best.get("seniority") is not None
            else None
        ),
        "contact_department": (
            str(best.get("department")).strip()
            if best.get("department") is not None
            else None
        ),
        "contact_confidence": best.get("confidence"),
        "contact_verification_status": (
            str(verification.get("status")).strip()
            if verification.get("status") is not None
            else None
        ),
        "contact_source": "Hunter",
    }