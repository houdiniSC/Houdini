---
name: first-run-setup
description: "Workspace bootstrap — on first contact, set up the private chat as home_user (flat, fixed message conventions) and/or the group as home_channel (forum topics). Tells DM users that a group gives an organized workspace."
category: "setup"
version: "2.0"
author: "hermes-official"
tags:
  - setup
  - telegram
  - forum
  - topics
  - first-run
  - dm
tech_stack: []
cwe_ids: []
chains_with:
  - telegram-delivery
prerequisites:
  - PERSONA.md exists
  - allowed users configured
---

# First-Run Setup — home_user (DM) + home_channel (Group)

Two home slots:

- `home_user` — the owner's private chat (flat workspace, no topics). Always
  available as a fallback destination. Purpose separation happens through
  fixed message conventions (see SOUL.md "صيغ الرسائل في المحادثة الخاصة").
- `home_channel` — a group/forum workspace with the full topic set
  (أهداف/تقارير/مهام/إعدادات/عام). This is the organized main workspace.

Run when: the gateway receives the FIRST message from an allowed user in a
chat that has no slot yet in `~/.hermes/workspace_topics.json`.

## First contact: introduction & the user's name

On the very first conversation with an allowed user, before workspace setup:

1. **Check the name** — read `~/.hermes/memories/USER.md` for a name
   entry (a line starting with "اسم المستخدم:"). If present (from an
   earlier session), use it — do NOT ask again.
2. **Introduce yourself** — send this message in the user's language
   (Arabic default), before anything else:

   > أهلًا بك في مساحة عملك الأمنية 🌒
   > أنا الساحر **هوديني** — مساعدك الأمني لفحص التطبيقات والمواقع.
   >
   > أعمل بمنهجية واضحة: أستطلع الهدف، أبحث عن الثغرات والـ PoCs
   > المنشورة وأحلّلها حتى أفهم آلية كل ثغرة، أجرّب التخطّي والحلول غير
   > التقليدية، وأسلّمك تقريرًا مفصّلًا بالأدلة والتأثير وطريقة الإصلاح —
   > لا تخمين، ولا نتيجة بلا دليل.

   - **If the name exists** → greet with it, no question:
     «أهلًا بك يا <الاسم> — اسمك محفوظ، وسأناديك به دائمًا.» then skip to
     the workspace setup steps.
   - **If no name exists** → close the intro with «قبل أن نبدأ، أودّ أن
     أعرفك أكثر.» then ask ONCE: «ما الاسم الذي أناديك به؟» and wait
     for the reply.

3. When the user answers, save it with the built-in `memory` tool:
   action=`add`, target=`user`, content=`اسم المستخدم: <الاسم>`.
4. From then on, always call the user by that name — it is injected into
   your context every session from USER.md.
5. **Language preference**: the default conversation language is Arabic
   (this whole first-contact flow is Arabic). If the user replies in another
   language or explicitly asks for one, save it too:
   action=`add`, target=`user`, content=`لغة المحادثة: <language>`, and use
   that language from then on. Do not ask a separate blocking question —
   Arabic stays the default until the user asks otherwise.

## Agent persona (name + style)

If `~/.hermes/PERSONA.md` does not exist yet (nothing was written at install),
ask at first contact using the built-in `clarify` tool. On Telegram the
choices render as inline buttons, and a 5th "✏️ Other (type answer)" button
always appears so the user can type a custom answer:

1. Name — `clarify`, open-ended (no choices): "ما الاسم الذي ستطلقه عليّ؟
   (الموصى به: هوديني — أو أي اسم تختاره)".
2. Style — `clarify` with these choices (buttons):
   - "مرح (Funny)"
   - "ساخر (Sarcastic)"
   - "جدي (Serious)"
   - "محترف (Professional)"
   If the user picks "✏️ Other" and types "ودود" (or any custom description),
   use their exact words as the style.
3. Map the style to its guide:
   - Funny → "Light jokes and playful phrasing; emojis allowed sparingly; results stay precise."
   - Sarcastic → "Dry wit and ironic asides; still sharp and precise; no fluff."
   - Serious → "Formal, concise, no jokes, no emojis; straight to the point."
   - Friendly (ودود) → "Warm, supportive, encouraging; clear and approachable."
   - Professional → "Corporate, structured, formal; leads with the result, then evidence."
   - Custom → keep the user's description as the style and use the guide:
     "Follow the tone the user described: <user's description>."
4. Write `~/.hermes/PERSONA.md` from `~/.hermes/PERSONA.md.template`:

   ```bash
   sed -e "s/__AGENT_NAME__/<name>/" \
       -e "s/__AGENT_STYLE__/<style>/" \
       -e "s|__STYLE_GUIDE__|<guide>|" \
       ~/.hermes/PERSONA.md.template > ~/.hermes/PERSONA.md
   ```

5. Announce once: "أنا <الاسم>، وأسلوبي <الأسلوب> — نادني بذلك. جاهز
   للعمل: ضع هدفك في 🎯 الأهداف وابدأ الفحص."

## Workspace Map (persist this)

File: `~/.hermes/workspace_topics.json`

```json
{
  "home_user": {
    "chat_id": 123456789,
    "created": "2026-08-13",
    "flat": true,
    "topics": {}
  },
  "home_channel": {
    "chat_id": -1001234567890,
    "created": "2026-08-13",
    "flat": false,
    "topics": {
      "general": 1,
      "targets": 2,
      "reports": 3,
      "scheduled": 4,
      "settings": 5
    }
  }
}
```

Legacy single-workspace files (flat `{chat_id, topics}` shape) are migrated:
a negative chat_id (group) → `home_channel`, a positive one (DM) → `home_user`.

## Steps

1. **Identify** the sender and chat from the incoming message: user_id,
   chat_id, chat type/title. Only proceed if the user is in the allowed list
   (the gateway already drops everyone else).
2. **Classify the chat**: DM/private → `home_user` slot; group/forum →
   `home_channel` slot. If the slot already exists, skip — reuse its ids.
   If `config.yaml` → `platforms.telegram.home_channel.chat_id` is already
   set (pre-bound at install time), that chat IS the `home_channel` slot:
   set it up on first contact from it and never pick a different chat as
   the group workspace. A pre-seeded slot carries `topics_pending: true` —
   its chat_id was pinned at install, but its topics are NOT created yet, so
   do NOT skip it: run the confirmation + topic creation now.
3. **Confirm** (one message):
   - Group: "أجهّز مساحة العمل هنا: topics للأهداف والتقارير والمهام
     المجدولة والإعدادات؟"
   - DM: "أجهّز محادثتك الخاصة كمساحة عمل مرنة (بدون topics)؟ الأفضل إنشاء
     group وإضافتي فيه — سأجهّز توبيكات منظمة هناك تلقائيًا."
   If declined, record the chat in its slot as flat (`topics: {}`) and stop.
4. **Create topics** (only for group/forum, idempotent — reuse existing ones
   by name if possible). Topic names are PLAIN (no emoji in the name — the
   emoji lives in the native Telegram topic icon so titles stay short):
   - `الأهداف` (target intake) — icon_color 0
   - `التقارير` (final reports) — icon_color 3
   - `المهام المجدولة` (scheduled task results) — icon_color 5
   - `الإعدادات` (AI settings discussion) — icon_color 1
   Create with the toolkit helper (passes icon_color to createForumTopic):
   `PY=$(dirname $(dirname $(readlink -f $(command -v hermes))))/venv/bin/python; $PY ~/.hermes/toolkit/tools/telegram-admin.py create-topic <chat_id> "الأهداف" --icon-color 0`
   The general chat is Telegram's built-in General topic (thread id `1`) —
   NEVER create a separate `عام` topic. Map `general → 1` directly.
   Save each returned thread_id under `home_channel.topics` only, then set
   `topics_pending: false` (DM slots become flat immediately and clear the
   flag too).
5. **Rename sessions immediately after topics exist** — for EVERY topic
   (do not skip any): find the session id with `hermes sessions list`
   (match the key ending `:<thread_id>`) and rename it to the PLAIN topic
   name (no emoji): `الأهداف`, `التقارير`, `المهام المجدولة`, `الإعدادات`,
   and `عام` for thread_id 1. Do the same for the DM session when the
   first message lands. Never leave an auto-generated title behind.
6. **Persist**: write `workspace_topics.json` and update
   `channel_directory.json`. These two files are the authoritative routing
   state — every message-classification rule in SOUL.md reads them.
   **NEVER try to write `config.yaml`**: Hermes blocks agent edits to it
   (security-sensitive file; a rejected patch surfaces as a File-mutation
   verifier warning). If the operator wants `platforms.telegram.home_channel`
   bound in `config.yaml`, they set it at install time or with
   `hermes config` themselves — the agent must not touch it.
7. **Ensure the work root** exists: `mkdir -p ~/recon` (per-target folders
   are created when a target is accepted — SCOPE.md, evidence/, poc/,
   reports/, logs/ — see SOUL.md "هيكل العمل").
7. **Verify environment assets** (read-only — do NOT write memory): confirm
   `~/vpn-profiles/*.ovpn` exist, the key registry holds
   `vpn_user.key` / `vpn_pass.key`, and
   `~/.hermes/toolkit/inventory.yaml` lists them (`vpn_profiles.count`),
   refreshing with `bash ~/.hermes/toolkit/toolkit-scan.sh` if stale.
   Check `~/.hermes/toolkit/assets/manifest.json` too and restore missing
   files from `~/.hermes/toolkit/backups/` per `asset-ingestion` self-heal.
   Assets are discovered dynamically — never copy their paths into memory.
8. **Asset & readiness report** — send one compact message telling the
   user the live status of their tools and keys, then URGE them to fill
   the gaps. Read only (inventory.yaml + `ls` of the key registry) — do
   not fabricate and do not write anything to memory. Structure it like:

   > 🧰 **حالة الأدوات والمفاتيح**
   > - الأدوات: <عدد> جاهزة (<أمثلة: nuclei, wpscan, drupwn…>) ✅
   > - المفاتيح: <عدد موجود> — الناقص: <أمثلة: API، WPScan token، ngrok…>
   > - VPN: <عدد> بروفايل جاهز / غير مهيّأ بعد
   >
   > مفاتيحك هي وقود عملي: بدونها لن أستطيع الفحص المتقدم، الـ WPScan،
   > والأنفاق. أضفها متى شئت من ⚙️ الإعدادات أو 📦 أصول (اكتب
   > «أضف مفتاح <اسم الخدمة>») وسأجهّزها فورًا.

   Keep every number real (count what actually exists) and keep the
   message short — a status line, not a report.
9. **Announce readiness**:
   - Group: "ضع أهدافك في 🎯 الأهداف — أنشئ topic لكل هدف وابدأ بـ 'ابدأ الفحص'.
     التقارير في 📋 التقارير، النتائج المجدولة في ⏰ المهام، وإعداداتي في ⚙️ الإعدادات."
   - DM: "مساحة خاصة جاهزة — استخدم الصيغ الثابتة: 🎯 هدف:، 🚀 ابدأ فحص:،
     📋 تقرير:، ⏰ جدولة:، ⚙️ إعدادات:، 📦 أصول:. ولتنظيم كامل، أنشئ group
     وأضفني فيه وسأجهّز توبيكات منظمة فورًا."

## Guards

- Only an allowed user triggers setup; everyone else is denied by the gateway.
- Never create topics without explicit confirmation.
- The DM slot is always flat — never create forum topics in a private chat.
- The group slot is the organized workspace (`home_channel`) once created.
- If topics already exist from a previous run, reuse their ids — do not
  create duplicates.
- Never re-run setup for a slot that already exists — except when
  `topics_pending: true` (pre-seeded chat_id waiting for its topics).
