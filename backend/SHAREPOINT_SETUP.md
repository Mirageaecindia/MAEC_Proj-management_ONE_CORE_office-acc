# SharePoint Integration Setup Guide

## Prerequisites (Manual Admin Steps Required)

**IMPORTANT**: The following steps **must be performed by an Azure AD / Microsoft 365 administrator** in your organization. The coding tool cannot perform these steps automatically.

### 1. Register an Azure AD Application

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** (formerly Azure AD) → **App registrations** → **New registration**
2. Name: `MAEC Project Management` (or your preferred name)
3. Supported account types: **Accounts in this organizational directory only** (Single tenant)
4. Redirect URI: **Web** → `http://localhost:8000` (for local dev) or your production URL
5. Click **Register**

### 2. Configure API Permissions

1. In the app registration, go to **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**
2. Search for and select:
   - `Sites.ReadWrite.All` (recommended for full access)
   - OR `Sites.Selected` (for tighter scope - requires additional config in SharePoint Admin Center)
3. Click **Add permissions**
4. **CRITICAL**: Click **Grant admin consent for [Your Organization]** - this requires Global Admin rights
5. Verify status shows green checkmarks with "Granted for [Your Organization]"

### 3. Create Client Secret

1. Go to **Certificates & secrets** → **New client secret**
2. Description: `MAEC SharePoint Integration`
3. Expiry: Choose appropriate (e.g., 12 months, 24 months)
4. Copy the **Value** immediately - you won't see it again!

### 4. Get Tenant ID

1. In Azure Portal → **Microsoft Entra ID** → **Overview**
2. Copy **Tenant ID** (Directory ID)

### 5. Get SharePoint Site ID

**Option A: Using Graph Explorer (easiest)**
1. Go to [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)
2. Sign in with admin account
3. Run: `GET https://graph.microsoft.com/v1.0/sites/mirageace.sharepoint.com:/sites/Automation`
4. Copy the `id` from the response (format: `mirageace.sharepoint.com,<guid>,<guid>`)

**Option B: Using PowerShell**
```powershell
Connect-SPOService -Url https://mirageace-admin.sharepoint.com
Get-SPOSite -Identity https://mirageace.sharepoint.com/sites/Automation
```

### 6. Get SharePoint Drive ID (Optional)

1. In Graph Explorer, run: `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives`
2. Find the drive with `name: "Documents"` or `name: "Shared Documents"`
3. Copy its `id`

### 7. Configure Backend Environment

1. Copy `.env.example` to `.env` in the backend directory:
   ```bash
   cd backend
   cp .env.example .env
   ```

2. Edit `.env` with your values:
   ```env
   AZURE_CLIENT_ID=<your-client-id-from-step-1>
   AZURE_CLIENT_SECRET=<your-client-secret-from-step-3>
   AZURE_TENANT_ID=<your-tenant-id-from-step-4>
   SHAREPOINT_SITE_ID=<your-site-id-from-step-5>
   SHAREPOINT_DRIVE_ID=<your-drive-id-from-step-6-or-leave-blank>
   SHAREPOINT_TARGET_PATH=Project_Mirage_Manage/delivery/Project
   ```

3. Install new dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 8. Verify Integration

1. Start the backend: `uvicorn main:app --reload`
2. Start the frontend
3. Log in as BU Head
4. Create a project with at least one SharePoint discipline selected
5. Check the response for `sharepoint_status: "provisioned"` and a valid `sharepoint_site_url`
6. **Verify in SharePoint**: Navigate to `https://mirageace.sharepoint.com/sites/Automation/Shared Documents/Project_Mirage_Manage/delivery/Project/` and confirm the project folder and discipline subfolders exist

## Troubleshooting

| Error | Cause | Resolution |
|-------|-------|------------|
| `AADSTS70011` / `Invalid scope` | Wrong scope or missing admin consent | Ensure `Sites.ReadWrite.All` is granted and admin consent given |
| `403 Forbidden` on folder create | App lacks permission on site | For `Sites.Selected`, configure in SharePoint Admin Center; for `Sites.ReadWrite.All`, ensure admin consent granted |
| `Site not found` | Wrong site ID | Verify site ID format: `hostname,guid,guid` |
| `Drive not found` | Wrong drive ID or not resolved | Leave `SHAREPOINT_DRIVE_ID` blank to auto-resolve |
| `Token acquisition failed` | Wrong client ID/secret/tenant | Verify all three values match Azure AD app registration |

## Security Notes

- **Never commit `.env` to version control** - it's in `.gitignore`
- Rotate client secrets periodically
- Use `Sites.Selected` instead of `Sites.ReadWrite.All` for production (requires SharePoint Admin Center configuration)
- Monitor Azure AD sign-in logs for the app's activity

## Folder Structure Created

For a project "MAEC-2026-001" with HVAC and Electrical disciplines:
```
Shared Documents/
└── Project_Mirage_Manage/
    └── delivery/
        └── Project/
            └── MAEC-2026-001/
                ├── 01_HVAC_Discipline/
                └── 02_Electrical_Discipline/
```