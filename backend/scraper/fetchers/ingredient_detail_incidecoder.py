"""INCIDecoder ingredient detail extractor.

Fetches https://incidecoder.com/ingredients/<slug> and parses out:
  - description (plain-English)
  - functions (CosIng + colloquial tags)
  - id_rating ('superstar' | 'goodie' | None)
  - irritancy_score, comedogenicity_score (0-5 if shown)
  - cas_number, ec_number (Quick Facts box)
  - synonyms

Server-rendered HTML, so simple httpx + regex suffices.
"""
from __future__ import annotations

import html as html_module
import re

import httpx

UA = "Wand-Bot/0.1 (skincare aggregator; contact: hello@wand.app)"
TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_module.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _extract_id_rating(html: str) -> str | None:
    """ID-Rating shown as <div class="ourtake ..."><word>"""
    m = re.search(r'<div class="ourtake[^"]*"[^>]*>\s*([a-z]+)\s*</div>', html, re.IGNORECASE)
    if m:
        v = m.group(1).strip().lower()
        if v in ("superstar", "goodie", "icky", "loaded"):
            return v
    return None


def _extract_quick_facts(html: str) -> dict:
    """Pull (CAS, EC, IUPAC, INN) from the bold-label Quick Facts box."""
    facts: dict[str, str] = {}
    for label, key in [
        (r"CAS\s*#", "cas_number"),
        (r"EC\s*#", "ec_number"),
        (r"Chemical/IUPAC Name", "iupac_name"),
        (r"Ph\.?\s*Eur\.?\s*Name", "inn_name"),
    ]:
        m = re.search(rf"{label}\s*:\s*</b>\s*([^<|\n]+?)(?:\s*\||<|$)", html, re.IGNORECASE)
        if m:
            facts[key] = m.group(1).strip()
    syn = re.search(r'Also-called-like-this:\s*</span>\s*<span[^>]*>\s*([^<]+)', html, re.IGNORECASE)
    if syn:
        facts["synonyms"] = syn.group(1).strip()
    return facts


def _extract_functions(html: str) -> list[str]:
    """Function tags are anchors under /ingredient-functions/."""
    funcs = re.findall(r'href=["\']/ingredient-functions/([^"\']+)["\'][^>]*>([^<]+)<',
                       html, re.IGNORECASE)
    seen = set()
    out = []
    for _slug, label in funcs:
        l = label.strip().lower()
        if l and l not in seen:
            seen.add(l)
            out.append(label.strip())
    return out


def _extract_description(html: str) -> str | None:
    """The ingredient narrative lives in #showmore-section-details > .content > <p>."""
    m = re.search(
        r'id="showmore-section-details".*?<div class="content">(.*?)</div>',
        html, re.DOTALL,
    )
    if not m:
        return None
    body = m.group(1)
    paras = re.findall(r"<p[^>]*>(.*?)</p>", body, re.DOTALL)
    if not paras:
        return None
    text = " ".join(_strip_tags(p) for p in paras[:3])
    return text[:2000] or None


def _extract_score(html: str, label: str) -> int | None:
    """Pull integer 0-5 next to a label like 'Comedogenic' or 'Irritancy'."""
    m = re.search(rf"{label}[^0-9<]*<[^>]+>\s*([0-5])", html, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


async def fetch_incidecoder(inci_name: str) -> dict | None:
    """Return a dict of normalized + raw fields, or None if not found."""
    slug = _slugify(inci_name)
    url = f"https://incidecoder.com/ingredients/{slug}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": UA}) as client:
            resp = await client.get(url)
    except httpx.HTTPError:
        return None

    if resp.status_code == 404:
        return {"source_url": url, "fetch_status": "not_found"}
    if resp.status_code >= 400:
        return {"source_url": url, "fetch_status": "failed",
                "error_message": f"HTTP {resp.status_code}"}

    html = resp.text
    facts = _extract_quick_facts(html)
    return {
        "source": "incidecoder",
        "source_url": url,
        "fetch_status": "success",
        "inci_name": inci_name,
        "cas_number": facts.get("cas_number"),
        "ec_number": facts.get("ec_number"),
        "iupac_name": facts.get("iupac_name"),
        "description": _extract_description(html),
        "functions": _extract_functions(html),
        "id_rating": _extract_id_rating(html),
        "comedogenicity": _extract_score(html, "Comedogenic"),
        "irritancy": _extract_score(html, "Irritancy"),
        "raw_facts": facts,
    }
