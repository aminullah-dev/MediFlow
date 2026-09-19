# marketing/

Social marketing material for MediFlow, in Dari and Pashto, and the tooling
that regenerates it. None of this is imported by the application or included in
the Windows or macOS build.

| | |
|---|---|
| **[`working-method-prompt.md`](working-method-prompt.md)** | Paste into Claude to produce more content later. Holds the claim whitelist, the banned-claims list, the Dari/Pashto terminology, and the post and image formats. **Read this before writing any new copy.** |
| **[`posts-dari.md`](posts-dari.md)** · **[`posts-pashto.md`](posts-pashto.md)** | Six posts each, ready to publish, plus short WhatsApp-status lines. |
| **[`cards.toml`](cards.toml)** | The headline and supporting line for each card — the only place that text is written. |
| **`images/screens/`** | 16 screenshots of the running application: dashboard, reception, pharmacy and patients × Dari/Pashto × light/dark, at 2880×1800. |
| **`images/cards/`** | 24 typographic cards: six subjects × two languages × 1080×1080 (feed) and 1080×1920 (status). |
| **`tools/`** | The two generators and their shared PNG writer. |

## Before publishing anything

1. **Replace `[[تماس]]` / `[[اړیکه]]`** with a real WhatsApp number or link.
   Every post carries one. A post with nothing to act on is a post that does
   nothing.
2. **Have a Pashto speaker read `posts-pashto.md`.** It was written against a
   grammar reference and the application's own translation files, not by a
   native speaker. The file says so at the top.
3. **Add no claim that is not on the whitelist.** There are no deployment
   numbers, no approvals and no certifications to quote, and inventing one is
   not recoverable in a market this small.

## Regenerating

```bash
# Screenshots — boots the real application against a throwaway database
QT_QPA_PLATFORM=offscreen python marketing/tools/shoot.py

# Cards — reads cards.toml
python marketing/tools/make_cards.py
```

`shoot.py` puts its database in a temporary folder (`MEDIFLOW_DATA_DIR`) and
deletes it afterwards, so it can never touch a real installation. The clinic it
shows is invented in `tools/demo_clinic.py`: the patient names are common Afghan
given names used as placeholders, and no row describes a real person.

Both scripts write PNGs through an indexed 256-colour palette
(`tools/imaging.py`), which is about a third of the size with no visible
difference on flat interface art. For a printed asset, re-render without it.

## Design notes

Colours come straight from `mediflow/ui/theme.py` and the typeface is the
Vazirmatn shipped in `mediflow/ui/fonts/`, so a card and a screenshot sitting
next to each other in a feed are recognisably the same product.

Card text is laid out, never hand-positioned: the headline picks the largest
size at which every line fits, and the rule under it is placed from the measured
descent of the text above, so editing a line in `cards.toml` cannot push
anything off the canvas or draw a rule through a ی.

Pillow renders the Persian and Pashto through libraqm, which does the joining
and the bidi reordering. `make_cards.py` refuses to run without it rather than
emit cards whose letters are unjoined and backwards — a failure that looks
enough like a design choice to get published.
