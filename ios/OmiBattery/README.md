# OmiBattery (iPhone) / Omi電池

One tap: open the app → it scans, connects, reads the standard Battery Level (0x180F/0x2A19), shows %, and **disconnects
immediately**. Never pairs, never holds the connection, so the Mac sync keeps working. Last reading is remembered.
Also available as a Shortcut action / Siri phrase ("Omi電池で電池を見る") → put it on the Action button, Back Tap, or Home Screen.

Why native, not Web Bluetooth: iOS Safari has no Web Bluetooth; Bluefy etc. need a third-party browser and a device
chooser on every read. The native app is one tap.

## Install (free Apple ID is enough)
1. Mac: open `ios/OmiBattery/OmiBattery.xcodeproj` in Xcode.
2. Xcode → Settings → Accounts → add your Apple ID (if not yet).
3. Target **OmiBattery** → Signing & Capabilities → Team: *your name (Personal Team)*.
4. Connect the iPhone by USB, select it as the run destination, press **Run** (⌘R).
5. iPhone first time: Settings → General → VPN & Device Management → trust your developer certificate;
   Settings → Privacy & Security → **Developer Mode** on (restart) if asked.
6. Open "Omi電池" → allow Bluetooth.
Free-team apps expire after 7 days: just press Run again from Xcode.

If the pendant isn't found: it may be mid-sync with the Mac (only one connection at a time) — wait a minute and tap Refresh.
Regenerate the project after editing `project.yml`: `xcodegen generate`.
