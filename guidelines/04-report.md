# Layer 4 – Report

Layer 4 has two parts. The **batch editor** is an agent. The **PDF renderer** is a plain
script, `scripts/render_pdfs.py`.

## Part 1 – Batch editor (agent)

**Your job:** you receive the confirmed Layer 3 profiles for one batch. You do **no new web
research**. You only work with what is in front of you.

1. **Check consistency.** Suppliers with similar evidence should get similar scores. If a
   score is clearly out of line with the rubric in `03-deep-dive.md`, set an adjusted
   `final_score` and say why in `adjustment_note`. Otherwise `final_score` is the sum of the
   Layer 3 scores and `adjustment_note` is `null`.
2. **Rank** the suppliers within each segment (`garment` and `fabric`) by `final_score`,
   highest first. Break ties in this order: higher `ksa_export`, then higher `factory`.
3. **Write a one-line reason** per supplier (at most 25 words) saying why it ranks where it
   does.
4. **Write the batch overview,** 5–8 sentences:
   - how many suppliers were checked and how many passed
   - the strongest garment factories and fabric mills
   - common risks
   - what the buyer should do next, for example "request samples and SABER documents from
     the shortlist"

Return only the structured output.

## Part 2 – PDF renderer (script)

The script builds:

- **One profile PDF per confirmed supplier.** It shows:
  - header: English and Chinese name, segment, city, recommendation and score
  - summary
  - score table
  - company and registry facts
  - factory and capacity
  - quality and certificates
  - KSA export readiness
  - Chinese web presence
  - contacts
  - risks
  - sources
- **One batch summary PDF.** It contains:
  - the overview
  - one ranked table for garment factories and one for fabric mills
  - a table of rejected suppliers with their reasons

Rules for the content:

- **Gaps:** show "not found" for missing information. Never leave an empty space that looks
  like a mistake.
- **Self-reported claims:** label them "self-reported".
- **Sources:** list them at the end with their links.
- **Date and batch:** put the batch name and date on every page.
