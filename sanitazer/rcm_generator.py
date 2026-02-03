import pandas as pd

# Realistic SOC 2 Controls (English) - Fully English Input
audit_data = [
    {
        "Control Ref": "CC6.1-01",
        "Control Activity Description": "New employees at FinTech Corp are required to sign a Non-Disclosure Agreement (NDA) and complete Security Awareness Training before being granted access to production systems (e.g., AWS, ProdDB).",
        "Frequency": "Onboarding",
        "Owner": "HR Manager"
    },
    {
        "Control Ref": "CC6.3-01",
        "Control Activity Description": "User access reviews for critical systems (Jira, Salesforce, AWS) are performed quarterly by the Security Officer (John Doe) to verify that access levels remain appropriate. Inactive accounts are removed.",
        "Frequency": "Quarterly",
        "Owner": "Security Officer"
    },
    {
        "Control Ref": "CC6.6-01",
        "Control Activity Description": "The organization utilizes CrowdStrike Falcon on all endpoints. The antivirus software is configured to perform daily scans and update signatures automatically every 4 hours.",
        "Frequency": "Daily",
        "Owner": "IT Admin"
    },
    {
        "Control Ref": "CC8.1-01",
        "Control Activity Description": "All changes to the CoreApp source code stored in GitHub require a peer review and approval by a Lead Developer before being merged into the master branch.",
        "Frequency": "Per Change",
        "Owner": "DevOps Lead"
    },
    {
        "Control Ref": "A1.2-01",
        "Control Activity Description": "Full backups of customer databases (PostgreSQL) are performed daily at 02:00 UTC. Backups are encrypted and replicated to a secondary AWS region (us-east-1) for disaster recovery purposes.",
        "Frequency": "Daily",
        "Owner": "DB Admin"
    },
    {
        "Control Ref": "CC9.2-01",
        "Control Activity Description": "The Compliance Team reviews SOC 2 Type 2 reports of critical vendors (AWS, Slack, Google Workspace) annually to assess the effectiveness of their controls.",
        "Frequency": "Annually",
        "Owner": "Compliance Lead"
    }
]

df = pd.DataFrame(audit_data)
df.to_excel("controls.xlsx", index=False)
print("✅ SUCCESS: Generated English 'controls.xlsx'.")