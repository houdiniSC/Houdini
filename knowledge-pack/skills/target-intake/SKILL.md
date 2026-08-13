---
name: target-intake
description: "Target intake in the 🎯 الأهداف topic — accept a link/email/APK, create a dedicated forum topic per target, and NEVER scan there. Scanning starts only inside the target's own topic on an explicit start phrase."
category: "setup"
version: "1.0"
author: "houdini"
tags:
  - targets
  - topics
  - intake
  - authorization
tech_stack: []
cwe_ids: []
chains_with:
  - first-run-setup
  - recon-playbook
  - report-template
prerequisites:
  - first-run-setup completed (home_channel topics exist)
---

# Target Intake — one topic per target

## When to run
A message arrives in the **🎯 الأهداف** topic (or uses the DM prefix
`🎯 هدف: <value>`) containing a target: URL/domain, email, or APK file.

## Rules
- 🎯 الأهداف is **intake only** — never scan, never run tools, never start
  recon there.
- Every target gets its **own forum topic** named `🎯 <target>` (sanitized:
  strip protocol/paths from URLs, use the domain; for APK use the filename
  without extension). Reuse an existing topic for the same target — no
  duplicates.
- Recon/scanning happens **only inside that target's topic**, and **only
  after the user gives an explicit start phrase** («ابدأ الفحص», «افحص»,
  «start scan»).
- Until the start phrase: no tool calls and no network activity for that
  target — just create the topic and wait.

## Steps
1. Identify the target from the message (URL → hostname; email → domain;
   APK → filename without extension). Skip invalid entries with a polite
   refusal.
2. Create the topic with the bundled admin tool (read the chat_id from
   `~/.hermes/workspace_topics.json` → `home_channel.chat_id`):

   ```bash
   ~/.hermes/hermes-agent/venv/bin/python \
     ~/.hermes/toolkit/tools/telegram-admin.py create-topic \
     -1004306190198 "🎯 <target>"
   ```

   The tool prints the new `message_thread_id` on stdout — capture it. If it
   fails with a 400 about topic creation, tell the user to disable
   BotFather → Bot Settings → Threads Settings → "Disallow users to create
   new threads" (or make the bot a group admin), then retry.
3. Record it in `~/.hermes/workspace_topics.json` under
   `home_channel.topics` (key = `target:<target>`, value = the returned
   thread_id); keep `topics_pending: false`. Update `channel_directory.json`
   too.
4. Create the work folder `~/recon/<target>/` (SCOPE.md is written when the
   scan starts — never before).
5. Reply in 🎯 الأهداف with the ACTUAL topic link/id you just created:
   - Group: «جهّزت topic مخصص للهدف 🎯 <target> — افتحه واكتب «ابدأ الفحص»
     لبدء الفحص.»
   - DM: «تمت إضافة الهدف. اكتب 🚀 ابدأ فحص: <target> لبدء الفحص.»

## Guards
- Only confirm the topic after the tool actually printed a thread_id — never
  claim a topic was created otherwise.
- Never run tools for a target before the start phrase.
- If a scan request arrives in 🎯 الأهداف: refuse politely and redirect to
  the target's own topic.
- Never scan two targets in one topic.
- Duplicate target → point to the existing topic instead of creating a new one.
