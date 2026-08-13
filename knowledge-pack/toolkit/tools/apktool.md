# apktool

- Category: APK decode / rebuild (resources + manifest)
- Usage: `apktool d app.apk -o app-src -f` | `apktool b app-src -o patched.apk`
- Install: `sudo apt-get install -y apktool` (Kali/Ubuntu) or release JAR from GitHub
- Notes: decode before jadx for manifest/smali review; rebuild + sign for repackaging tests
