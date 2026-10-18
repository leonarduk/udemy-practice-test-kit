---
name: yt-promo
description: Clean up the text of a "Steve's Coding" YouTube course-promo video — rewrite the title and description, and produce a corrected English .srt caption file from YouTube's auto-generated transcript, flagging compliance and accuracy problems in the voiceover. Use when the user types /yt-promo, pastes a youtube.com/watch link and asks to "edit the text", "fix the captions/subtitles", "do the description", or says "now do <youtube link>" after an earlier one.
user-invocable: true
---

# /yt-promo — title, description and captions for a course promo video

The user (channel "Steve's Coding") makes short (~1–1.5 min) promo videos for
their Udemy certification practice-test courses (Java SE 21/25, Python
PCEP/PCAP, …). Each video has a narrated voiceover, two sample questions from
a mock exam, and a call to action. The uploaded text is usually poor: the
title is sometimes just the Udemy URL, the description is one line or empty,
and YouTube's auto-captions mangle technical terms. This skill fixes all three.

Never change anything on YouTube yourself — Studio needs the user's sign-in,
and editing public content needs their go-ahead. Deliver text and a file.

Handle several links in one request by repeating the steps per video.

## 1. Pull the video's text (built-in browser)

Open the link with `mcp__Claude_Browser__preview_start` (url) — if `navigate`
is refused, `preview_start` with the url usually works. Then run this with
`mcp__Claude_Browser__javascript_tool`. Fetching the caption `baseUrl`
directly returns an empty body, so open the transcript panel and scrape it:

```js
await new Promise(r=>setTimeout(r,2500));
const p = window.ytInitialPlayerResponse;
const info = {id:p?.videoDetails?.videoId, title:p?.videoDetails?.title,
  author:p?.videoDetails?.author, len:p?.videoDetails?.lengthSeconds,
  desc:p?.videoDetails?.shortDescription};
document.querySelector('#description-inline-expander #expand, tp-yt-paper-button#expand')?.click();
await new Promise(r=>setTimeout(r,800));
// innerText alone misses some transcript buttons; match label text too
const b=[...document.querySelectorAll('button, yt-button-shape button, ytd-button-renderer')]
  .find(x=>/transcript/i.test((x.innerText||'')+(x.getAttribute('aria-label')||'')));
b?.click();
await new Promise(r=>setTimeout(r,5000));
const segs=[...document.querySelectorAll('ytd-transcript-segment-renderer, transcript-segment-view-model')];
JSON.stringify(info)+'\n'+segs.map(s=>s.innerText.replace(/\s+/g,' ')).join('\n')
```

If `info` is filled but there are no caption tracks
(`p.captions` missing), the video is probably minutes old and YouTube hasn't
made the auto-captions yet — check `microformat.playerMicroformatRenderer.uploadDate`.
Meanwhile read the Udemy course page (public) for the description's facts;
check for captions with
`curl -s -A "Mozilla/5.0" "<watch url>&hl=en" | grep -o '"captionTracks"'`
and re-run the scrape when it matches. The first scrape on a fresh tab often
finds no transcript button even when captions exist — re-run once before
concluding there are none.

If `info` comes back `{}` and no transcript button is found, read the page with
`get_page_text`: a **"Private video"** page means the browser pane isn't
signed in to the channel. Never sign in yourself. Ask the user to either sign
in to YouTube in the browser pane themselves, set the video to Unlisted while
you work, or paste the auto-transcript from Studio (Subtitles → English
(automatic) → ⋮ → Download .srt) together with the current title and
description.

Check `info.id` matches the requested video (a stale page can be returned).
If no segments come back, wait and re-run the scrape part once; if still
nothing, tell the user the video has no transcript and do title/description
only.

The Udemy course URL is normally in the description or the title — keep it
exactly as given.

## 2. Title

`<Certification> (<exam code>) Practice Tests: <N> Exam-Style Questions with Explanations`
— or a close variant that fits the course. Under ~70 characters where
possible. Never a bare URL.

## 3. Description

Follow this shape (it is what the user accepted for the earlier videos):

```
<One or two sentences: who it's for, which exam, what it gives you.>

👉 Enrol here: <udemy url>

What you get:
✅ <N> exam-style questions
✅ <tests / timing / pass mark — only figures the voiceover states>
✅ <domain coverage>
✅ <how answers are explained>

In this video, two sample questions from <Mock Exam 1 / test name>:
<m:ss> <topic: one-line hook>
<m:ss> <topic: one-line hook>

Get exam-ready. Enrol in the course today.

#<5–6 relevant hashtags>
```

The timestamps are chapter-style links to where each sample question starts
in the transcript. Use only facts the voiceover states — don't invent
question counts, durations or pass marks. British spelling ("Enrol").

## 4. Corrected captions (.srt)

Write `<course-slug>-promo-captions.en.srt` to the session scratchpad,
send it with `SendUserFile` (`display: "attach"`).

- Start times come from the transcript segments; each cue ends where the next
  starts; the last cue ends at `lengthSeconds`.
- Split long segments into cues of ≤2 lines, ~42 chars per line, ≤~7 s.
  Interpolated split times are estimates — say so.
- Keep `[music]` as its own cue only if it has its own gap in the timeline;
  drop it when it sits mid-sentence.
- Fix punctuation and sentence boundaries; make the captions read as written
  English while saying what the narrator says.
- Replace "real exam questions" / "a real question" with "exam-style" (see 5).

Common ASR errors seen in these videos — check every one:

| Heard | Correct |
|---|---|
| bite | `byte` |
| sign type | signed type |
| -28 | -128 (byte range, Integer cache) |
| JP | JEP |
| fulllength | full-length |
| Java SE21 / SE25 | Java SE 21 / SE 25 |
| 1 Z0-830 | 1Z0-830 (and 1Z0-831 etc.) |
| PCE or 30, PC or 30 | PCEP-30 |
| PCAP or 31 | PCAP-31 |
| optal literal | octal literal |
| zero division error | `ZeroDivisionError` |
| integer (the class) | `Integer` |
| Enroll | Enrol |
| Everyone checked | every one checked |
| RA tools | RAG, tools |
| bin (Spring) | bean |
| match if missing | `matchIfMissing` |
| illegal state exception | `IllegalStateException` |
| Spring Boot for.1 | Spring Boot 4.1 (flag — version unclear) |
| its difference (of a PR) | its diff |
| the.3% | the 0.3% |
| halfcent | half-cent |

Not every course is a vendor certification (e.g. Spring Boot / Spring AI has
no exam code) — then use `<Topic> Practice Tests: <N> Scenario-Based
Questions` and leave the exam code out of title and hashtags.

Also verify the *arithmetic and code* the narration describes — the transcript
can drop characters from literals (e.g. "07" for `0o17` when the narration
says 1 × 8 + 7 = 15). Write what the maths implies and flag it.

## 5. Flag, don't silently fix, voiceover problems

The captions can be corrected; the audio can't. Report these in a
"Check before publishing" section:

- **"Real exam questions" / "a real question"** — implies leaked/braindump
  content from the actual exam, which breaks the certification vendor's rules
  and Udemy's practice-test policy. Recommend "exam-style" in the voiceover.
- **Technically wrong code or claims** — e.g. `017` is a SyntaxError in
  Python 3 (needs `0o17`); a wrong byte range. Ask the user to check what is
  shown on screen.
- **Figures that disagree with the user's other promos or the official exam**
  (durations, question counts, pass marks) — point out the inconsistency, don't
  assert the right number unless you've verified it.

## 6. Reply format

1. One line: which video (title as found, length) and what's wrong with its
   current text.
2. `## Title`, `## Description` (in a fenced block for copy-paste).
3. A short "what I fixed in the captions" list or table.
4. `## Check before publishing` with the section 5 flags and a reminder that
   split timings are estimates.
5. Upload path: **YouTube Studio → Subtitles → English → Add → Upload file →
   With timing**, then unpublish the auto-generated track.

Close the turn with `wrap_up` (recap only, nothing pending).
