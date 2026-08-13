# frida

- Category: runtime instrumentation (hooking, pinning bypass, memory dump)
- Usage: `frida-ps -U` | `objection -g com.target.app explore` | `frida -U -f com.target.app -l script.js`
- Install: `pip install frida-tools objection` + matching `frida-server` pushed to the device
- Notes: version of frida-server must match frida client; `objection patchapk` embeds the gadget for non-root flows
