# Going live on TikTok with Sokokali (moderator relay)

This setup is fully within TikTok's terms: Sokokali appears on your TikTok LIVE through TikTok's own LIVE Studio, and a moderator relays viewers' comments into Sokokali by hand. No unofficial TikTok API is used.

```
TikTok viewers ──comments──▶ Moderator (reads them on a phone or TikTok LIVE window)
                                   │ types/pastes into the dashboard "Moderator relay"
                                   ▼
                           Sokokali backend: filters, prioritizes, answers
                                   │
                                   ▼
                 Stage view window (presenter + voice) ──captured by──▶ TikTok LIVE Studio ──▶ TikTok LIVE
```

## Before your first stream

1. **LIVE access.** Make sure your TikTok account can go LIVE from a computer. See [Apply for LIVE access](https://www.tiktok.com/live/studio/help/article/Before-you-go-LIVE/Apply-for-LIVE-access?lang=en). Requirements (age 18+, followers, account standing) vary by region.
2. **Install TikTok LIVE Studio:** [tiktok.com/studio/download](https://www.tiktok.com/studio/download?lang=en). Setup help: [Install and start LIVE Studio](https://www.tiktok.com/live/studio/help/article/Before-you-go-LIVE/Install-and-start-LIVE-Studio?lang=en).
3. **Read TikTok's LIVE rules**, especially for AI-generated presenters: the [LIVE Safety Guide](https://www.tiktok.com/safety/en/tools-and-guides/live-safety-guide) and the community guidelines. Say clearly on the stream that Sokokali is an AI presenter. Keep the "predictions are not guarantees" messages on (they are built in).
4. **A good voice:** use **Microsoft Edge** for the stage view. On Windows it usually offers natural Kiswahili (Kenya) and English (Kenya) voices. Pick one in the dashboard's Avatar & voice panel.
5. Optional but recommended: put your Claude key in `.env` (`ANTHROPIC_API_KEY`) for natural replies, and set `SOKOKALI_SPORTS_PROVIDER=football_data` with `FOOTBALL_DATA_API_KEY` for **real** fixtures. Otherwise Sokokali talks about simulated matches, and the stage shows a "SIMULATED DATA" banner.

## Each stream

1. Start Sokokali: `docker compose up -d` (or `scripts\start-dev.ps1`).
2. Open the dashboard: http://localhost:8080.
3. In **Broadcast control**, choose **Audience: TikTok LIVE via moderator relay**, then **Start**.
4. Open the **Stage view**: the "Stage view ↗" link in the Avatar & voice panel.
   - Landscape: http://localhost:8080/?view=stage
   - Portrait (phone viewers): http://localhost:8080/?view=stage&layout=portrait
   - **Click once** on the stage window to enable the voice.
   - The dashboard stops speaking automatically while a stage view is open, so you never hear two voices.
5. In **TikTok LIVE Studio**, add a **window capture** source for the stage window and capture its audio (application or desktop audio). Choose the portrait layout if you stream vertically. Go LIVE.
6. **Moderator:** watch the TikTok LIVE comments (on a phone, or in LIVE Studio) and relay them in the dashboard's **Moderator relay** panel:
   - Type the viewer's username and their comment, then press **Enter**. Sokokali answers on air.
   - Several at once: open "Paste several comments at once" and paste lines like `wanjiku_254: Arsenal vs Chelsea nani atashinda?`.
   - Gifts, joins and follows: choose the type, then **Relay**. Sokokali thanks the viewer (gifts trigger a celebration, never priority).
7. **Pause** keeps comments queuing while Sokokali stops talking; **Stop** ends the show.

## What the moderator should know

- **Relay questions, not everything.** Sokokali still filters (duplicates, spam, abuse, phone numbers) and answers real questions first. Each relayed comment shows its result: queued with its priority, or why it was filtered.
- **Don't relay personal data or abuse.** If you do, Sokokali refuses it anyway, and it is not stored.
- **Pace:** Sokokali answers one question at a time, and questions older than 90 seconds are skipped. Relay the best questions, not all of them.
- **Trivia and polls** (from "Run now" or the automatic segments): relay answers like `wanjiku_254: B` or poll votes `brian: 1`. They count for the leaderboard without being "answered" on air.

## Later: automatic comments

When TikTok grants authorized access to LIVE events (apply via [TikTok for Developers](https://developers.tiktok.com/signup) and [developer support](https://developers.tiktok.com/portal/support?origin_site=doc-station)), only `backend/app/integrations/live/tiktok.py` needs implementing. The moderator relay can then be switched off.
