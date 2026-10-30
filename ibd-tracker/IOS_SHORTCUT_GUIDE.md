# iOS Shortcut Setup Guide: 1-Tap IBD Symptom Logging

This guide walks you through setting up an Apple Shortcut on your iPhone for 3-tap symptom and bowel movement intake in **< 4 seconds**.

You can run this shortcut from your **Lock Screen widget**, **Home Screen icon**, **Action Button**, or by asking Siri (*"Hey Siri, log movement"*).

---

## Shortcut Workflow Overview

When triggered, the shortcut prompts for three inputs:
1. **Bristol Stool Consistency** (Menu 1 to 7)
2. **Pain Level** (Menu 1 to 10 or Number prompt)
3. **Blood Presence** (Menu: `None`, `Some`, `A lot`)

It sends a JSON payload to your Hyperion server (`http://<HYPERION_IP>:8080/api/log`) and displays a confirmation notification with your daily movement count (e.g., `Logged! BM #3 today.`).

---

## Step-by-Step Configuration in Apple Shortcuts

Open the **Shortcuts** app on your iPhone and tap **`+`** (New Shortcut). Name it **"Log Movement"** and choose an icon (like a medical cross or notebook).

### Step 1: Bristol Stool Consistency Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Bristol Scale (1-7)`
3. Add 7 items:
   - `1 - Hard lumps (Constipation)`
   - `2 - Sausage, lumpy`
   - `3 - Sausage with cracks`
   - `4 - Smooth snake (Normal)`
   - `5 - Soft blobs`
   - `6 - Mushy / ragged (Diarrhea)`
   - `7 - Watery liquid`
4. Under each menu branch, add a **`Number`** action:
   - Under `1 ...`: Number `1`
   - Under `2 ...`: Number `2`
   - Under `3 ...`: Number `3`
   - Under `4 ...`: Number `4`
   - Under `5 ...`: Number `5`
   - Under `6 ...`: Number `6`
   - Under `7 ...`: Number `7`
5. After `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Consistency`
   - Value: `Menu Result` (as Number)

---

### Step 2: Pain Level Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Pain Level (1-10)`
3. Add items: `1 (None)`, `2`, `3`, `4`, `5 (Moderate)`, `6`, `7`, `8`, `9`, `10 (Severe)`
4. Under each branch, add a **`Number`** action corresponding to the number (1 to 10).
5. After `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Pain`
   - Value: `Menu Result` (as Number)

*(Alternative: Use `Ask for Input` with type Number if you prefer numeric keyboard typing).*

---

### Step 3: Blood Presence Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Blood in Stool?`
3. Add 3 items:
   - `None`
   - `Some / Trace`
   - `A lot`
4. Under each branch, add a **`Text`** action:
   - Under `None`: Text `none`
   - Under `Some / Trace`: Text `some`
   - Under `A lot`: Text `alot`
5. After `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Blood`
   - Value: `Menu Result` (as Text)

---

### Step 4: HTTP Request (Intake API)
1. Add action: **`Get Contents of URL`**
2. Set URL to:
   ```
   http://<YOUR_HYPERION_HOST_OR_IP>:8080/api/log
   ```
   *(If accessing remotely via VPN, Tailscale, or reverse proxy, use your secure URL).*
3. Expand advanced settings:
   - **Method:** `POST`
   - **Headers:**
     - `Content-Type`: `application/json`
     - *(Optional if configured)* `X-API-Key`: `your-api-key`
   - **Request Body:** `JSON`
     - Add Key: `bristol` | Type: `Number` | Value: Variable `Consistency`
     - Add Key: `pain` | Type: `Number` | Value: Variable `Pain`
     - Add Key: `blood` | Type: `Text` | Value: Variable `Blood`

---

### Step 5: Parse Response & Confirmation Notification
1. Add action: **`Get Dictionary from Input`** (Input: `Contents of URL`).
2. Add action: **`Get Dictionary Value`**
   - Key: `message`
   - Set Variable: `ServerMessage`
3. Add action: **`Show Notification`**
   - Title: `IBD Tracker`
   - Message: `ServerMessage` (e.g. *"Logged successfully. Movement #3 today."*)
   - Sound: Enabled

---

## Quick Access Setup on iPhone

1. **Lock Screen Widget:** Go to your Lock Screen > Customize > Add Widgets > Shortcuts > Select **Log Movement**.
2. **Action Button (iPhone 15 Pro / 16 / 16 Pro):** Settings > Action Button > Shortcut > Select **Log Movement**.
3. **Home Screen Icon:** In the Shortcuts app, tap the dropdown next to the shortcut name > **Add to Home Screen**.
