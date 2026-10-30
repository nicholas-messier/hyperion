# iOS Shortcut Setup Guide: Local Queue & Batch Sync Workflow

This guide details the default offline-first symptom logging workflow for your iPhone:
- **Shortcut 1 ("Log Movement"):** 3-tap instant intake saving locally to your device with exact timestamps. Works 100% offline anywhere (airplane mode, travel, cell dead zones).
- **Shortcut 2 ("Sync Logs"):** 1-tap sync to upload all accumulated logs to Hyperion in bulk whenever you are home on Wi-Fi or every few days.

---

## Shortcut 1: "Log Movement" (Instant Offline Logging)

Open the **Shortcuts** app on your iPhone and tap **`+`** (New Shortcut). Name it **"Log Movement"**.

### Step 1: Bristol Consistency Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Bristol Scale (1-7)`
3. Add 7 items:
   - `1 - Hard lumps (Severe Constipation)`
   - `2 - Sausage, lumpy`
   - `3 - Sausage with cracks`
   - `4 - Smooth snake (Normal)`
   - `5 - Soft blobs`
   - `6 - Mushy / ragged (Diarrhea)`
   - `7 - Watery liquid`
4. Under each menu branch, add a **`Number`** action:
   - Place Number `1` through `7` in each respective section.
5. Directly below `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Consistency`
   - Value: `Menu Result` (as Number)

### Step 2: Pain Level Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Pain Level (1-10)`
3. Add items: `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`
4. Under each branch, add a **`Number`** action corresponding to the number (1 to 10).
5. Directly below `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Pain`
   - Value: `Menu Result` (as Number)

### Step 3: Blood Presence Menu
1. Add action: **`Choose from Menu`**
2. Set prompt to: `Blood in Stool?`
3. Add 3 items: `None`, `Some / Trace`, `A lot`
4. Under each branch, add a **`Text`** action:
   - Under `None`: Text `none`
   - Under `Some / Trace`: Text `some`
   - Under `A lot`: Text `alot`
5. Directly below `End Menu`, add action: **`Set Variable`**
   - Variable Name: `Blood`
   - Value: `Menu Result` (as Text)

### Step 4: Format Timestamp & Build Record
1. Add action: **`Date`** (Current Date).
2. Add action: **`Format Date`**:
   - Date Format: `Custom`
   - Format String: `yyyy-MM-dd HH:mm:ss`
   - Set Variable: `FormattedTime`
3. Add action: **`Dictionary`**:
   - Add Key `timestamp` (Text) -> Value: Variable `FormattedTime`
   - Add Key `bristol` (Number) -> Value: Variable `Consistency`
   - Add Key `pain` (Number) -> Value: Variable `Pain`
   - Add Key `blood` (Text) -> Value: Variable `Blood`
   - Add Key `notes` (Text) -> Value: `` (empty or optional text)

### Step 5: Append to Local File Queue
1. Add action: **`Append to File`**:
   - Append: `Dictionary`
   - File Path: `Shortcuts/ibd_offline_logs.json`
   - Make New Line: **On**
2. Add action: **`Show Notification`**:
   - Title: `IBD Tracker`
   - Message: `Logged! Bristol [Consistency], Pain [Pain]/10 (Saved to queue)`
   - Sound: Enabled

---

## Shortcut 2: "Sync Logs" (Upload to Hyperion)

Create a second shortcut in the Shortcuts app and name it **"Sync Logs"**.

1. Add action: **`Get File`**:
   - Document Path: `Shortcuts/ibd_offline_logs.json`
   - Error If Not Found: **Off**
2. Add action: **`If`**:
   - Condition: `File` *has any value*
3. Inside the `If` block:
   - Add action: **`Get Contents of URL`**:
     - URL: `http://192.168.0.16:8080/api/logs/batch`
     - Method: `POST`
     - Headers:
       - `Content-Type`: `text/plain`
     - Request Body: `File` (Select the `File` variable from Step 1)
   - Add action: **`Delete Files`**:
     - Input: `File` (Select the file from Step 1)
     - Confirm Before Deleting: **Off**
   - Add action: **`Show Notification`**:
     - Title: `IBD Tracker`
     - Message: `Synced all offline logs to Hyperion!`
4. In the `Otherwise` block:
   - Add action: **`Show Notification`**:
     - Title: `IBD Tracker`
     - Message: `No pending logs in queue.`
5. End `If`.

---

## Quick Access Setup on iPhone

1. **Lock Screen Widget:** Lock Screen > Customize > Add Widgets > Shortcuts > Select **Log Movement**.
2. **Action Button (iPhone 15 Pro / 16 / 16 Pro):** Settings > Action Button > Shortcut > Select **Log Movement**.
3. **Home Screen Icon:** In Shortcuts, tap `...` > Share icon > **Add to Home Screen**.
