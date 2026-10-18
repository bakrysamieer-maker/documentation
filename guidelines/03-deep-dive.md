# Layer 3 – Deep dive

**Your job:** research each supplier that passed Layer 2 in more depth:

- who they are in China (Chinese sources)
- where they work (factories and capacity)
- how good their quality evidence is
- whether they can export to **Saudi Arabia (KSA)**
- how to contact them

Then score them and write a short profile. Layer 4 turns your work into a PDF, so everything
you return must be accurate and sourced.

Read `00-common-rules.md` first. You receive Layer 1 and Layer 2 findings. Build on them; do
not redo what is already well sourced.

**You may overturn a PASS.** If you find strong evidence that the supplier is really a
trading company, has no factory of its own, is out of scope, or is closed, set
`final_verdict` to `REJECT` and explain why in `reject_reason`. Otherwise use `CONFIRMED`.

## A. Chinese identity and registry

1. **Find the Chinese legal name (中文名称).** Look on the company's Chinese website, its B2B
   pages, or in search results.
2. **Search the Chinese name** with words such as 企查查, 天眼查, 爱企查, 工商信息, 成立日期,
   注册资本, 参保人数 or 经营范围. Registry facts often appear in search results. You may
   open `tianyancha.com/company/...` pages if they load without a login.
3. **Record:**
   - established date
   - registered capital
   - company type
   - whether the business scope includes production (生产, 制造, 加工, 织造)
   - insured employees (参保人数)
   - registered address
   - status (存续 / 在业 = active; 注销 / 吊销 = closed)
   - unified social credit code, if shown
4. **Risk findings**, only if a source shows them:
   - 经营异常 (abnormal operation list)
   - 行政处罚 (penalties)
   - 失信 (dishonest debtor)
   - serious lawsuits

## B. Where they work

- Factory address or addresses, city and district, and industrial cluster. Common clusters:
  - Fabric: Shaoxing Keqiao, Wujiang Shengze, Changzhou, Weifang, Shijiazhuang
  - Garments: Humen (Dongguan), Xintang (Zengcheng) for jeans, Ningbo for menswear,
    Changshu, Jinjiang
- Plant area, number of plants, and other sites such as a showroom or overseas office.
- **Compare the registered address with the factory address.** An office-only address is a
  trader risk; note it.

## C. Capacity and products

- Workforce.
- Equipment: number and type of looms (air-jet, water-jet, rapier) for mills; sewing lines
  for garment factories.
- Monthly output, MOQ and lead time.
- Main products.
- Known customers or brands. Only list them when a source names them.

## D. Quality

- **Certifications:** for each, record the name, whether the holder name matches the company,
  and the source.
- **Check databases where you can:** OEKO-TEX label check, the GOTS public database,
  Textile Exchange (GRS/RCS). If a database can't be checked, say so. Don't guess.
- **Third-party audits:** SGS, BV, TÜV, Intertek.

## E. Chinese web presence

Look for:

- A Chinese website.
- A `1688.com` store, including badges such as 实力商家, 源头工厂 or 深度验厂.
- A WeChat official account (公众号).
- Chinese news coverage.

These help confirm the company is a real, established producer.

## F. Ability to export to KSA

Look for these signals and record each with its source:

- Export markets listed: Saudi Arabia, GCC, Middle East.
- Named Saudi or GCC customers, distributors or agents.
- **SASO / SABER** experience. Textiles and garments need SABER conformity certificates to
  enter KSA.
- Arab-market products: thobe or abaya fabric, nida, thobes, abayas, jalabiya, kandura.
- An Arabic website or catalog.
- Trade fairs in Saudi Arabia or the GCC (Riyadh, Jeddah, Dubai).
- Its own export licence (自营进出口权) or AEO customs status.
- Customs-data snippets in search results that show shipments to Saudi Arabia.

Rate `ksa_export.rating`:

| Rating | Meaning |
|---|---|
| `strong` | Direct proof of selling to KSA: named Saudi customers, SABER experience, Saudi trade fairs or customs data. |
| `moderate` | Middle East or GCC markets claimed, Arab-market products, or Dubai trade fairs, but no direct KSA proof. |
| `weak` | Exports elsewhere; no Middle East signals. |
| `unknown` | No export information found. |

## G. Contacts

Complete the contact list, following the contact rules in `00-common-rules.md`:

- emails
- phones
- WeChat
- WhatsApp
- LinkedIn URLs (from search results only; never open LinkedIn)
- website
- B2B profiles
- published sales contacts, with name and title

Prefer company channels. Give every contact its source URL and a short label such as
"sales", "general" or "export manager". If two sources disagree, keep both and say so in the
label.

## H. Scores

Use this rubric so scores are comparable across suppliers:

| Score | Range | Guide |
|---|---|---|
| `factory` | 0–30 | **26–30** verified own factory (audit or registry with employees) plus production photos. **18–25** strong but partly self-reported. **10–17** limited evidence. **0–9** doubtful. |
| `quality` | 0–25 | **21–25** several verified certificates or audits plus brand customers. **14–20** one verified certificate or audit. **7–13** self-reported certificates only. **0–6** none. |
| `ksa_export` | 0–25 | **strong** 20–25. **moderate** 12–19. **weak** 5–11. **unknown** 0–4. |
| `scale` | 0–10 | Capacity for its segment. A mill with 100+ looms or a garment factory with 300+ workers scores about 8–10. |
| `contactability` | 0–10 | **10**: direct email, phone and WeChat or WhatsApp found. Subtract for each missing channel. |

## I. Summary and recommendation

- `summary`: 3–5 plain sentences. Who they are, what they make, where, how big, and how
  ready for KSA.
- `strengths` and `risks`: short bullet-style lists.
- `recommendation`:
  - `shortlist`: total score 70 or more and no major risk
  - `consider`: 50–69, or 70 or more with a notable risk
  - `low_priority`: below 50
- `sources`: every URL you relied on, each with a short title.

**Effort:** about 10–20 searches or page reads per supplier. Spend the most effort on the
factory check, KSA export and contacts, because they matter most to the buyer.
