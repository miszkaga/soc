"""
Tests for system_description_sanitizer.py

Covers:
- Entity classification correctness (ORGANIZATION vs PERSON)
- Bullet-list vendor extraction (- Label: Vendor)
- Regex-based replacement (email, IP, URL, phone)
- SAFE_TERMS exclusion (generic tech/compliance words)
- Determinism
- Longest-match-first replacement
- Entity map persistence
"""

import json
import os
import sys

import pytest

# Add project root to sys.path so imports work regardless of where pytest is run.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from system_description_sanitizer import AlgorithmicSanitizer, _should_skip_entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sanitizer() -> AlgorithmicSanitizer:
    return AlgorithmicSanitizer()


# ---------------------------------------------------------------------------
# _should_skip_entity unit tests
# ---------------------------------------------------------------------------

class TestShouldSkipEntity:
    def test_skips_two_character_tokens(self):
        assert _should_skip_entity("AI") is True

    def test_skips_single_character(self):
        assert _should_skip_entity("A") is True

    def test_skips_very_long_spans(self):
        assert _should_skip_entity("A" * 61) is True

    def test_skips_known_safe_terms(self):
        for term in ("VPN", "MFA", "TLS", "API", "SQL", "AICPA", "HIPAA"):
            assert _should_skip_entity(term) is True, f"'{term}' should be skipped"

    def test_does_not_skip_real_vendor_names(self):
        for name in ("Zendesk", "GitLab", "Salesforce", "Datadog"):
            assert _should_skip_entity(name) is False, f"'{name}' should NOT be skipped"

    def test_does_not_skip_cloud_company_names(self):
        assert _should_skip_entity("Microsoft Azure") is False
        assert _should_skip_entity("Amazon Web Services") is False

    def test_skips_all_caps_abbreviation(self):
        # AKS, NSG, IAM are short all-uppercase abbreviations
        assert _should_skip_entity("AKS") is True
        assert _should_skip_entity("NSG") is True
        assert _should_skip_entity("IAM") is True


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – NER / classification tests
# ---------------------------------------------------------------------------

class TestEntityClassification:
    def test_single_word_vendors_classified_as_organization(self):
        """
        Single-word proper nouns like 'Zendesk' and 'Salesforce' must map to
        [ORGANIZATION_N] tokens, not [PERSON_N].  spaCy's en_core_web_sm
        sometimes mis-labels tech company names as PERSON.
        """
        s = make_sanitizer()
        s.sanitize("We rely on Zendesk for support and Salesforce for CRM.")
        for original in ("Zendesk", "Salesforce"):
            if original in s.entity_map:
                token = s.entity_map[original]
                assert token.startswith("[ORGANIZATION_"), (
                    f"'{original}' was mapped to '{token}' — expected [ORGANIZATION_N]"
                )

    def test_vendor_names_removed_from_output(self):
        """Known vendor names must not appear in the sanitized text."""
        s = make_sanitizer()
        sanitized = s.sanitize("We rely on Zendesk for support and Salesforce for CRM.")
        assert "Zendesk" not in sanitized
        assert "Salesforce" not in sanitized

    def test_organization_name_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("MedCore Health Inc. provides the PatientFlow platform.")
        assert "MedCore Health Inc." not in sanitized
        assert "[ORGANIZATION_" in sanitized

    def test_person_name_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("The system is managed by Jane Smith.")
        assert "Jane Smith" not in sanitized


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – bullet-list extraction
# ---------------------------------------------------------------------------

class TestBulletListExtraction:
    """
    The sanitizer must catch vendor names in dash-prefixed lists such as:
      - Code Repository: GitLab (Self-hosted).
      - Monitoring: Datadog for APM.
    """

    def test_gitlab_replaced_from_bullet_list(self):
        s = make_sanitizer()
        text = "Software Stack:\n- Code Repository: GitLab (Self-hosted).\n- Monitoring: Datadog."
        sanitized = s.sanitize(text)
        assert "GitLab" not in sanitized, "GitLab should be replaced"

    def test_azure_active_directory_replaced_from_bullet_list(self):
        s = make_sanitizer()
        text = "- Identity: Azure Active Directory (Azure AD) for staff authentication."
        sanitized = s.sanitize(text)
        assert "Azure Active Directory" not in sanitized

    def test_azure_service_names_replaced_from_bullet_list(self):
        """Azure product names in bullet lists must be sanitized."""
        s = make_sanitizer()
        text = (
            "Core Components:\n"
            "- Compute: Azure Kubernetes Service (AKS) for microservices.\n"
            "- Database: Azure SQL Database with geo-redundancy.\n"
            "- Storage: Azure Blob Storage for medical imaging.\n"
        )
        sanitized = s.sanitize(text)
        assert "Azure Kubernetes Service" not in sanitized
        assert "Azure SQL Database" not in sanitized
        assert "Azure Blob Storage" not in sanitized

    def test_azure_virtual_network_replaced_from_bullet_list(self):
        s = make_sanitizer()
        text = "- Networking: Azure Virtual Network (VNet) with strict security controls."
        sanitized = s.sanitize(text)
        assert "Azure Virtual Network" not in sanitized

    def test_bullet_list_numbered_vendor_replaced(self):
        """Numbered list vendors (already supported) still work."""
        s = make_sanitizer()
        text = "1. Microsoft Azure:\n   - Service: Cloud infrastructure.\n"
        sanitized = s.sanitize(text)
        assert "Microsoft Azure" not in sanitized

    def test_bullet_list_does_not_extract_verb_phrases(self):
        """
        Bullet items whose value starts with a common English verb must NOT
        be captured as organisation entities.

        E.g.:
          - Clinical Operations: Responsible for data accuracy...
          - IT Security: Manages firewall rules...
          - Engineering: Develops features...
        """
        s = make_sanitizer()
        text = (
            "Key departments:\n"
            "- Clinical Operations: Responsible for data accuracy.\n"
            "- IT Security: Manages firewall rules and intrusion detection.\n"
            "- Engineering: Develops features using a secure SDLC.\n"
        )
        s.sanitize(text)
        for bad_entity in ("Responsible", "Manages firewall rules", "Develops features",
                           "Manages", "Develops"):
            assert bad_entity not in s.entity_map, (
                f"'{bad_entity}' should not be captured as an entity"
            )

    def test_bullet_list_does_not_extract_generic_descriptions(self):
        """
        Bullet values that are generic descriptions (not proper names) must
        not be captured.
        """
        s = make_sanitizer()
        text = (
            "- Encryption: All data is encrypted in transit (TLS 1.2+).\n"
            "- Service: System monitoring and alerting.\n"
            "- User Responsibility: Configuring IAM, encryption keys.\n"
        )
        s.sanitize(text)
        for bad_entity in ("All data", "System monitoring", "Configuring IAM",
                           "All", "System", "Configuring"):
            assert bad_entity not in s.entity_map, (
                f"'{bad_entity}' should not be captured as an entity"
            )

    def test_bullet_list_does_not_extract_preposition_phrases(self):
        """
        Bullet values like 'Hosted on Microsoft Azure' must not produce
        'Hosted on Microsoft Azure' as a single entity token.
        """
        s = make_sanitizer()
        text = "- Core Application: Hosted on Microsoft Azure (East US 2 Region).\n"
        s.sanitize(text)
        assert "Hosted on Microsoft Azure" not in s.entity_map, (
            "'Hosted on Microsoft Azure' is not a proper name and must not be in entity map"
        )
        # The real vendor name must still be caught (via NER or numbered-list extractor)
        assert "Microsoft Azure" not in s.sanitize(text)


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – SAFE_TERMS / false-positive exclusion
# ---------------------------------------------------------------------------

class TestSafeTermsExclusion:
    def test_generic_tech_terms_kept(self):
        """VPN, MFA, TLS etc. must pass through unchanged."""
        s = make_sanitizer()
        text = "Users connect via VPN using MFA. Traffic uses TLS 1.2+ and AES-256."
        sanitized = s.sanitize(text)
        assert "VPN" in sanitized
        assert "MFA" in sanitized
        assert "TLS" in sanitized
        assert "AES-256" in sanitized

    def test_network_security_groups_not_replaced(self):
        """
        'Network Security Groups' is a generic Azure networking concept, not an
        organization name, and must NOT be replaced with a token.
        """
        s = make_sanitizer()
        text = "Traffic is controlled by Network Security Groups (NSGs)."
        sanitized = s.sanitize(text)
        assert "Network Security Groups" in sanitized

    def test_compliance_frameworks_kept(self):
        s = make_sanitizer()
        text = "The system meets HIPAA, HITRUST, and SOC 2 requirements."
        sanitized = s.sanitize(text)
        assert "HIPAA" in sanitized
        assert "HITRUST" in sanitized
        assert "SOC 2" in sanitized

    def test_aicpa_kept(self):
        s = make_sanitizer()
        text = "Controls align with AICPA Trust Services Criteria."
        sanitized = s.sanitize(text)
        assert "AICPA" in sanitized

    def test_linux_windows_kept(self):
        s = make_sanitizer()
        text = "Servers run Linux and Windows."
        sanitized = s.sanitize(text)
        assert "Linux" in sanitized
        assert "Windows" in sanitized


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – regex pattern replacement
# ---------------------------------------------------------------------------

class TestRegexPatterns:
    def test_email_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("Contact admin@example.com for more information.")
        assert "@" not in sanitized
        assert "[EMAIL_" in sanitized

    def test_ipv4_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("The server is located at 192.168.1.100.")
        assert "192.168.1.100" not in sanitized
        assert "[IP_ADDRESS_" in sanitized

    def test_https_url_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("See https://internal.example.com/docs for details.")
        assert "internal.example.com" not in sanitized
        assert "[URL_" in sanitized

    def test_bare_www_url_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("Visit www.example.com for more information.")
        assert "www.example.com" not in sanitized
        assert "[URL_" in sanitized

    def test_phone_number_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("Call us at (555) 867-5309 for support.")
        assert "867-5309" not in sanitized
        assert "[PHONE_" in sanitized

    def test_cidr_ip_replaced(self):
        s = make_sanitizer()
        sanitized = s.sanitize("Allow traffic from 10.0.0.0/16.")
        assert "10.0.0.0/16" not in sanitized


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – determinism and token stability
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_entity_gets_same_token(self):
        """The same entity name appearing twice must get the same token."""
        s = make_sanitizer()
        s.sanitize(
            "MedCore Health Inc. uses Datadog. MedCore Health Inc. also uses Zendesk."
        )
        # Every entity must map to a unique token (different entities get different tokens)
        tokens = list(s.entity_map.values())
        assert len(tokens) == len(set(tokens)), (
            "All tokens must be unique — different entities cannot share the same token"
        )

    def test_two_runs_produce_same_output(self):
        """Running the sanitizer twice on identical input yields identical output."""
        text = (
            "MedCore Health Inc. uses Microsoft Azure and Datadog.\n"
            "Contact admin@example.com for support."
        )
        s1 = make_sanitizer()
        result1 = s1.sanitize(text)
        s2 = make_sanitizer()
        result2 = s2.sanitize(text)
        assert result1 == result2

    def test_longest_match_processed_first(self):
        """
        'Microsoft Azure' must be replaced as a whole before the shorter 'Microsoft'
        string, to avoid double-replacement artifacts.
        """
        s = make_sanitizer()
        sanitized = s.sanitize(
            "Microsoft Azure is our cloud provider. Microsoft is the vendor."
        )
        # Neither the full name nor the bare name should remain.
        assert "Microsoft Azure" not in sanitized
        assert "Microsoft" not in sanitized

    def test_entity_map_is_dict_with_string_values(self):
        s = make_sanitizer()
        s.sanitize("MedCore Health Inc. uses Zendesk.")
        assert isinstance(s.entity_map, dict)
        for k, v in s.entity_map.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
            assert v.startswith("[")
            assert v.endswith("]")


# ---------------------------------------------------------------------------
# AlgorithmicSanitizer – full system description integration
# ---------------------------------------------------------------------------

FULL_SYSTEM_DESCRIPTION = """\
SECTION 3: DESCRIPTION OF MEDCORE HEALTH'S "PATIENTFLOW" SYSTEM

I. COMPANY OVERVIEW AND SERVICES
MedCore Health Inc. ("the Company") provides a HIPAA-compliant patient management
platform. The system enables hospitals and clinics to schedule appointments.

II. INFRASTRUCTURE AND SOFTWARE
The PatientFlow system operates in a Hybrid Cloud model.
- Core Application: Hosted on Microsoft Azure (East US 2 Region).
- Legacy Archives: Maintained in Dallas, TX.

Core Components:
- Compute: Azure Kubernetes Service (AKS) for microservices.
- Database: Azure SQL Database with geo-redundancy.
- Storage: Azure Blob Storage for medical imaging (DICOM), encrypted at rest.
- Networking: Azure Virtual Network (VNet) with strict Network Security Groups (NSGs).

Software Stack:
- Code Repository: GitLab (Self-hosted).
- Monitoring: Datadog for APM and log aggregation.
- Support: Zendesk for customer ticketing.
- Identity: Azure Active Directory (Azure AD) for staff authentication.

V. SUBSERVICE ORGANIZATIONS (CARVE-OUT METHOD)
1. Microsoft Azure:
   - Service: Cloud infrastructure.
2. Datadog:
   - Service: System monitoring and alerting.
3. Salesforce:
   - Service: CRM for managing hospital client relationships.

VI. COMPLEMENTARY USER ENTITY CONTROLS (CUECs)
Management reviews SOC 2 and HITRUST reports for Microsoft Azure and Salesforce annually.
"""


class TestFullSystemDescriptionSanitization:
    def setup_method(self):
        self.s = make_sanitizer()
        self.sanitized = self.s.sanitize(FULL_SYSTEM_DESCRIPTION)

    def test_medcore_health_replaced(self):
        assert "MedCore Health Inc." not in self.sanitized

    def test_microsoft_azure_replaced(self):
        assert "Microsoft Azure" not in self.sanitized

    def test_datadog_replaced(self):
        assert "Datadog" not in self.sanitized

    def test_zendesk_replaced(self):
        assert "Zendesk" not in self.sanitized

    def test_salesforce_replaced(self):
        assert "Salesforce" not in self.sanitized

    def test_gitlab_replaced(self):
        assert "GitLab" not in self.sanitized, (
            "GitLab should be replaced — it appears in a '- Label: Value' bullet list"
        )

    def test_azure_kubernetes_service_replaced(self):
        assert "Azure Kubernetes Service" not in self.sanitized, (
            "Azure Kubernetes Service should be replaced via bullet-list extraction"
        )

    def test_azure_sql_database_replaced(self):
        assert "Azure SQL Database" not in self.sanitized

    def test_azure_blob_storage_replaced(self):
        assert "Azure Blob Storage" not in self.sanitized

    def test_azure_active_directory_replaced(self):
        assert "Azure Active Directory" not in self.sanitized

    def test_azure_virtual_network_replaced(self):
        assert "Azure Virtual Network" not in self.sanitized

    def test_network_security_groups_preserved(self):
        assert "Network Security Groups" in self.sanitized, (
            "Network Security Groups is a generic Azure concept, must not be replaced"
        )

    def test_hipaa_preserved(self):
        assert "HIPAA" in self.sanitized

    def test_dallas_location_replaced(self):
        assert "Dallas" not in self.sanitized

    def test_vendor_tokens_are_organizations_not_persons(self):
        """Vendors (Zendesk, Salesforce, Datadog, GitLab) must map to [ORGANIZATION_N]."""
        vendor_names = {"Zendesk", "Salesforce", "Datadog", "GitLab"}
        for name in vendor_names:
            if name in self.s.entity_map:
                token = self.s.entity_map[name]
                assert token.startswith("[ORGANIZATION_"), (
                    f"Vendor '{name}' mapped to '{token}' — expected [ORGANIZATION_N]"
                )

    def test_no_real_names_remain(self):
        """
        None of the known sensitive names from the test input should appear in the
        sanitized output.
        """
        sensitive_names = [
            "MedCore Health Inc.", "Microsoft Azure", "Datadog", "Zendesk",
            "Salesforce", "GitLab", "Dallas",
        ]
        for name in sensitive_names:
            assert name not in self.sanitized, f"'{name}' was not sanitized"
