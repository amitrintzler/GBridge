# Enabling Outlook sync — register a free Microsoft app (≈3 minutes, once)

GBridge writes to Outlook through the **Microsoft Graph API**. To use it,
GBridge needs a Microsoft "app registration" — a free, one-time setup in the
Azure portal that produces an **Application (client) ID** (a GUID). You paste
that GUID into GBridge and you're done.

> **Why isn't this built in?** GBridge ships no client ID of its own yet, so
> each user registers their own app. This keeps the project free of a central
> Microsoft account and means your sign-in is strictly between you and
> Microsoft. (A future release may ship a shared ID to skip this step.)
>
> **You do *not* need this for Google-only sync.** It's only required to push
> data *into* Outlook (Microsoft 365 / Graph path).

---

## Step 1 — Open App registrations

1. Go to **<https://portal.azure.com>** and sign in with the Microsoft account
   you want to sync (personal `@outlook.com`/`@hotmail.com` or a work/school
   account).
2. In the top search bar type **"App registrations"** and open it.
   (It lives under **Microsoft Entra ID**, formerly Azure Active Directory.)

## Step 2 — Register the app

1. Click **+ New registration**.
2. **Name:** `GBridge` (anything you like).
3. **Supported account types:** choose
   **"Accounts in any organizational directory and personal Microsoft
   accounts"**.
   (This is the `common` setting GBridge uses by default, so both personal and
   work accounts work.)
4. **Redirect URI:** change the dropdown to **"Public client/native (mobile &
   desktop)"** and enter:
   ```
   http://localhost
   ```
5. Click **Register**.

## Step 3 — Copy the Application (client) ID

On the app's **Overview** page, copy the **Application (client) ID** — it
looks like:

```
3fa85f64-5717-4562-b3fc-2c963f66afa6
```

That's the GUID you give to GBridge.

## Step 4 — Allow public-client sign-in

1. In the left menu click **Authentication**.
2. Scroll to **Advanced settings → Allow public client flows**.
3. Set it to **Yes**, then **Save**.

(This lets GBridge sign you in from a desktop app without a client secret.)

## Step 5 — Add the Graph permissions

1. In the left menu click **API permissions → + Add a permission**.
2. Choose **Microsoft Graph → Delegated permissions**.
3. Search for and tick each of:
   - `Contacts.ReadWrite`
   - `Calendars.ReadWrite`
   - `Tasks.ReadWrite`
4. Click **Add permissions**.

For a **personal** Microsoft account you're done — you'll approve these the
first time you sign in. For a **work/school** account, your IT admin may need
to click **"Grant admin consent"** on this page (or you can, if you have the
rights).

## Step 6 — Tell GBridge

Run this once, pasting your GUID from Step 3:

```bash
gbridge outlook auth --client-id 3fa85f64-5717-4562-b3fc-2c963f66afa6
```

A browser opens; sign in and approve the three permissions. The token is
stored in your OS keychain (never in a file).

Then enable Outlook write-back by setting the mode in
`config.json` (in your GBridge config folder):

```json
{ "outlook_mode": "graph" }
```

## Step 7 — Verify

```bash
gbridge doctor          # Microsoft app ID + sign-in should now show [x]
gbridge outlook push --dry   # preview what would be written — no changes
gbridge outlook push         # actually write to Outlook
```

Open Outlook and confirm a contact/event you recognize appears. That's the
full chain proven end-to-end.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Microsoft client_id is not configured` | You skipped Step 6 — run `gbridge outlook auth --client-id <GUID>`. |
| Sign-in page shows an error about the reply URL | Step 2.4 — the redirect URI must be **`http://localhost`** under **Public client/native**. |
| "AADSTS65001 / consent required" | Step 5 — add the three delegated permissions; for work accounts, grant admin consent. |
| Sign-in works but push fails with 403 | The permissions in Step 5 weren't approved — re-run `gbridge outlook auth` and approve them. |
| `gbridge outlook push` says everything failed | Make sure `outlook_mode` is `graph` (Step 6) and you've run a `gbridge sync` first. |
