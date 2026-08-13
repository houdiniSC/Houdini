---
name: telegram-delivery
description: Deliver reports and files to Telegram — current-topic rule, absolute MEDIA paths, caption pairing, flood retry.
---

# Telegram Delivery

## Destination rule
- Deliver to the topic/chat the user is currently working in.
- If no explicit topic context: the group workspace (`home_channel`) when it
  exists, otherwise the private chat (`home_user`).
- Final reports and scheduled-task results go to `home_channel` (the group)
  when one exists, otherwise `home_user` (the DM).

## Send a file
- `hermes send --to "telegram:<chat>:<thread_id>" "<caption> — MEDIA:<absolute-path>"`
- The MEDIA path MUST be absolute (`/home/...` or `~/...`) — bare filenames are NOT matched
- ALWAYS pair the file with a caption (media-only sends can vanish under throttling)

## Flood / 429 handling
- On 429, back off with doubling delays (30s → 60s → 120s)
- Do not send parallel media bursts; queue them

## Never
- Never print bot tokens or API keys in chat
- Never send raw credential material; send masked summaries
