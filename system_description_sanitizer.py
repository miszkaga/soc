"""
PHASE 0 (Pre-Pipeline): System Description Sanitizer
Algorithmically sanitizes the raw system description BEFORE any LLM processing.

WHY THIS MATTERS:
  Real SOC 2 system descriptions contain highly sensitive data:
  - Organisation legal names and trade names
  - Named vendors / subservice providers
  - Internal system / product names
  - Staff names, roles, and locations
  - IP addresses, URLs, e-mail addresses

  Sending this data to an external LLM API (e.g. OpenAI) creates a data-
  sovereignty and confidentiality risk.  This module removes sensitive content
  BEFORE any API call is made, so the LLM only ever sees anonymised tokens.

APPROACH (no external API calls):
  1. spaCy NER       – named entities: ORG, PERSON, GPE, LOC, PRODUCT
     Entities are detected on the ORIGINAL text for maximum accuracy, then
     replaced globally across the entire document.
     Falls back gracefully to regex-only if spaCy / the model is unavailable.
  2. Regex patterns  – structured artefacts: e-mail, IP, URL, phone

TOKENS PRODUCED:
  [ORGANIZATION_1], [ORGANIZATION_2], ...
  [PERSON_1], [PERSON_2], ...
  [LOCATION_1], [LOCATION_2], ...
  [PRODUCT_1], [PRODUCT_2], ...
  [EMAIL_1], [IP_ADDRESS_1], [URL_1], [PHONE_1], ...

OUTPUTS:
  none_ex_files/sanitized_system_description.txt   – safe to pass to LLMs
  none_ex_files/system_description_sensitive_map.json – reverse-lookup map

QUALITY TRADE-OFFS:
  Algorithmic sanitization is less precise than LLM-based sanitization:
  - May MISS entities that are contextually sensitive but not standard NER types
    (e.g. internal codenames that look like common words).
  - May OVER-sanitize tokens that spaCy mis-classifies as named entities.
  - Downstream LLM phases will work with anonymous tokens ([ORGANIZATION_1])
    instead of real names, so generated controls will be less tool-specific.
  These trade-offs are intentional: privacy protection takes precedence.
"""

import re
import json
import os
import sys
from typing import Dict, List, Tuple

sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
INPUT_FILE = "none_ex_files/system_description.txt"
OUTPUT_FILE = "none_ex_files/sanitized_system_description.txt"
MAP_FILE = "none_ex_files/system_description_sensitive_map.json"

# ---------------------------------------------------------------------------
# spaCy NER entity labels to sanitize and their token category names
# ---------------------------------------------------------------------------
SPACY_LABEL_MAP = {
    "ORG": "ORGANIZATION",
    "PERSON": "PERSON",
    "GPE": "LOCATION",       # Geo-political entity (countries, cities, states)
    "LOC": "LOCATION",       # Physical locations
    "PRODUCT": "PRODUCT",
    "FAC": "LOCATION",       # Facilities (buildings, airports)
    "WORK_OF_ART": "PRODUCT",
}

# spaCy entity labels that should NOT be sanitized
SPACY_SKIP_LABELS = {
    "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL",
    "LAW", "LANGUAGE", "NORP",  # nationalities, religions, political groups
}

# ---------------------------------------------------------------------------
# Generic tech / compliance terms that are always safe to keep.
# We KEEP (do not sanitize) any entity whose text.lower() is in this set.
# ---------------------------------------------------------------------------
SAFE_TERMS = {
    # Standards / frameworks / regulations
    "aicpa", "hipaa", "hitrust", "gdpr", "sox", "pci", "nist", "iso",
    "ssae", "tsp", "soc", "soc 2", "soc2", "ssae 21", "ssae21",
    "trust services criteria",
    # Trust Services categories
    "security", "availability", "confidentiality", "privacy",
    "processing integrity",
    "security, availability",
    "security, availability, and confidentiality",
    # Generic tech abbreviations
    "vpn", "mfa", "tls", "ssl", "aes", "api", "sdk", "sql", "nosql",
    "ldap", "saml", "oauth", "oidc", "dns", "http", "https", "ssh",
    "ftp", "smb", "smtp", "imap", "sftp", "rest", "soap", "json",
    "xml", "csv", "yaml", "html", "css",
    # Generic infrastructure terms (not proper names)
    "linux", "windows", "unix",
    # Sensitive data types / compliance acronyms
    "phi", "pii", "hipaa", "dicom", "ehr",
    # Common structural / corporate words
    "company", "inc.", "inc", "llc", "ltd", "corp", "corporation",
    "the company",
    # Generic computing terms that spaCy sometimes flags
    "hybrid cloud", "cloud", "microservices",
    # Generic role / department words
    "engineering", "operations", "management", "finance", "hr",
    "legal", "compliance", "clinical operations", "it security",
    # Document structure words
    "overview", "services", "infrastructure", "software",
}

# ---------------------------------------------------------------------------
# Regex-based patterns for structured sensitive artefacts.
# Applied AFTER NER so structural text is already anonymised.
# ---------------------------------------------------------------------------
REGEX_PATTERNS: List[Tuple[str, str]] = [
    # E-mail addresses
    ("EMAIL", r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    # IPv4 addresses (with optional CIDR)
    ("IP_ADDRESS", r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b'),
    # HTTP / HTTPS URLs
    ("URL", r'https?://[^\s<>"\']+'),
    # Bare www. URLs
    ("URL", r'www\.[a-zA-Z0-9\-]+\.[^\s<>"\']+'),
    # Phone numbers (US-style)
    ("PHONE", r'\b(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b'),
]

# ---------------------------------------------------------------------------
# Patterns that indicate a span is NOT a sensitive proper name.
# Entities matching any of these are skipped.
# ---------------------------------------------------------------------------
_SKIP_ENTITY_PATTERNS = [
    re.compile(r'^[IVX]+\.\s'),                 # Roman numeral section headers
    re.compile(r'\('),                           # Spans containing parentheses
    re.compile(r'\n'),                           # Multi-line spans
    re.compile(r'^\d'),                          # Starts with a digit
    re.compile(r'^[A-Z0-9]{2,6}$'),             # Short all-caps abbreviations (AKS, IAM, APM)
    re.compile(r'^[A-Z][A-Z0-9\s,]{4,}$'),      # All-caps section-header-like phrases
]


def _should_skip_entity(text: str) -> bool:
    """Return True if this entity should NOT be sanitized."""
    stripped = text.strip()

    # Too short to be a meaningful proper name
    if len(stripped) <= 2:
        return True

    # Too long – likely a sentence fragment picked up by NER
    if len(stripped) > 60:
        return True

    # Safe terms list (case-insensitive)
    if stripped.lower() in SAFE_TERMS:
        return True

    # Pattern-based exclusions
    for pattern in _SKIP_ENTITY_PATTERNS:
        if pattern.search(stripped):
            return True

    return False


class AlgorithmicSanitizer:
    """
    Builds a deterministic, reproducible sensitive-entity map and applies it
    to produce an anonymised copy of the system description.

    Algorithm:
      1. Run spaCy NER on the ORIGINAL text to collect all named entities.
         Entities are registered in self.entity_map (original -> token).
      2. Apply all entity replacements as global string substitutions
         (longest match first to prevent partial sub-string collisions).
      3. Apply regex patterns to catch remaining structured artefacts.
    """

    def __init__(self):
        self.entity_map: Dict[str, str] = {}   # original_text -> token
        self.counters: Dict[str, int] = {}     # category -> next_index
        self._nlp = None                       # lazy-loaded spaCy model

    # ------------------------------------------------------------------
    # spaCy loader (optional dependency)
    # ------------------------------------------------------------------
    def _load_spacy(self):
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy
            self._nlp = spacy.load("en_core_web_sm")
            return self._nlp
        except ImportError:
            print("⚠️  spaCy is not installed. Run: pip install spacy")
            return None
        except OSError:
            print("⚠️  spaCy model 'en_core_web_sm' not found. Run: python -m spacy download en_core_web_sm")
            return None

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------
    def _next_token(self, category: str) -> str:
        """Return the next sequential token for a given category."""
        n = self.counters.get(category, 0) + 1
        self.counters[category] = n
        return f"[{category}_{n}]"

    def _get_or_create_token(self, text: str, category: str) -> str:
        """Return the existing token for *text*, or create a new one."""
        key = text.strip()
        if key not in self.entity_map:
            self.entity_map[key] = self._next_token(category)
        return self.entity_map[key]

    # ------------------------------------------------------------------
    # Phase 1: Collect NER entities from original text
    # ------------------------------------------------------------------
    def _collect_ner_entities(self, text: str) -> None:
        """
        Run spaCy NER on *text* and register all relevant entities.
        Does NOT modify the text; only populates self.entity_map.
        """
        nlp = self._load_spacy()
        if nlp is None:
            print("⚠️  spaCy model unavailable – NER step skipped (regex-only mode).")
            return

        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in SPACY_SKIP_LABELS:
                continue
            category = SPACY_LABEL_MAP.get(ent.label_)
            if category is None:
                continue
            if _should_skip_entity(ent.text):
                continue
            self._get_or_create_token(ent.text, category)

    # ------------------------------------------------------------------
    # Phase 2a: Collect entities from structured numbered lists
    #   Catches proper names that spaCy misses in list contexts, e.g.:
    #   "2. Datadog:" or "3. Salesforce:"
    #   Pattern: line starts with a digit + period + space + ProperName + colon
    # ------------------------------------------------------------------
    _LIST_ITEM_RE = re.compile(
        r'^\d+\.\s+([A-Z][A-Za-z0-9 &\-]+?)(?:\s*:)',
        re.MULTILINE,
    )

    def _collect_list_entities(self, text: str) -> None:
        """
        Extract proper names from numbered-list item headers and register them
        as ORGANIZATION tokens (these are almost always vendor / product names).
        """
        for m in self._LIST_ITEM_RE.finditer(text):
            name = m.group(1).strip()
            if not _should_skip_entity(name):
                self._get_or_create_token(name, "ORGANIZATION")

    # ------------------------------------------------------------------
    # Phase 2: Apply NER replacements globally
    # ------------------------------------------------------------------
    def _apply_entity_map(self, text: str) -> str:
        """
        Replace all known entities throughout the text.
        Processes longest entries first to avoid partial-string collisions
        (e.g. 'Microsoft Azure' before 'Microsoft').
        """
        for original, token in sorted(
            self.entity_map.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            text = text.replace(original, token)
        return text

    # ------------------------------------------------------------------
    # Phase 3: Regex scan for structured artefacts
    # ------------------------------------------------------------------
    def _apply_regex(self, text: str) -> str:
        """Replace structured artefacts (emails, IPs, URLs, phones)."""
        for category, pattern in REGEX_PATTERNS:
            def replacer(m, cat=category):
                return self._get_or_create_token(m.group(0), cat)
            text = re.sub(pattern, replacer, text)
        return text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def sanitize(self, text: str) -> str:
        """
        Run the full sanitization pipeline on *text* and return the
        anonymised result.  self.entity_map is populated as a side-effect.

        Order:
          1. Collect NER entities from the ORIGINAL text (best accuracy).
          1b. Collect entities from structured numbered lists (catches vendors
              that NER misses, e.g. "2. Datadog:").
          2. Apply global string substitutions for all detected entities.
          3. Apply regex for remaining structured artefacts.
        """
        self._collect_ner_entities(text)
        self._collect_list_entities(text)
        text = self._apply_entity_map(text)
        text = self._apply_regex(text)
        return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("PHASE 0: SYSTEM DESCRIPTION SANITIZER (Algorithmic – No API Calls)")
    print("=" * 80)

    if not os.path.exists(INPUT_FILE):
        print(f"❌ Input file not found: {INPUT_FILE}")
        print("   Create none_ex_files/system_description.txt and re-run.")
        sys.exit(1)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    print(f"✓ Loaded system description ({len(raw_text)} characters)")

    sanitizer = AlgorithmicSanitizer()
    sanitized_text = sanitizer.sanitize(raw_text)

    # ------------------------------------------------------------------
    # Persist outputs
    # ------------------------------------------------------------------
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(sanitized_text)

    # Save map with original -> token direction for auditability / reversal
    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(sanitizer.entity_map, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_replacements = len(sanitizer.entity_map)
    print(f"\n✅ Sanitization complete: {total_replacements} unique sensitive entities replaced")
    if sanitizer.counters:
        for category, count in sorted(sanitizer.counters.items()):
            print(f"   {category}: {count} entit{'y' if count == 1 else 'ies'}")

    print(f"\n📄 Sanitized description -> {OUTPUT_FILE}")
    print(f"🗂️  Sensitive map         -> {MAP_FILE}")

    print("\n⚠️  QUALITY NOTE: Downstream LLM phases will work with anonymous tokens")
    print("   (e.g. [ORGANIZATION_1]) instead of real names. Generated controls")
    print("   will be structurally correct but less vendor-specific than when real")
    print("   names are used. This is the intentional privacy-quality trade-off.")
    print("=" * 80)


if __name__ == "__main__":
    main()
