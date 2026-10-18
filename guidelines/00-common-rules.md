# Common rules (every agent, every layer)

These rules apply to all agents in the pipeline. The layer files (01–04) add the rules for each
specific job. If a layer file and this file disagree, this file wins.

## 1. What we are looking for

We source **clothing textiles from China for import into Saudi Arabia (KSA)**. There are two
segments, and every supplier belongs to exactly one:

| Segment   | Who                                         | Examples of products                                                                    |
|-----------|---------------------------------------------|-----------------------------------------------------------------------------------------|
| `garment` | Factories that make **finished clothing**   | shirts, trousers, jeans, suits, blazers, jackets, coats, dresses, blouses, skirts, abayas, thobes, workwear, uniforms, kids' woven wear |
| `fabric`  | Mills that make **woven fabric for clothing** | shirting, poplin, twill, denim, canvas, oxford, suiting (TR, wool blends), linen, rayon/viscose, spun polyester, chiffon, georgette, crepe, satin, nida, thobe fabric, abaya fabric |

### Always exclude

- **Not clothing:** home textiles (bedding, curtains, towels, table linen), furniture and
  upholstery fabric, carpets, shoes, bags, hats, scarves and other accessories, jewelry,
  non-woven fabric, technical or industrial textiles (filters, geotextiles, medical), yarn or
  fiber only, textile machinery, dyes and chemicals.
- **Knitting specialists:** suppliers whose **main** products are knitted. Knitted means
  jersey, interlock, rib, pique, fleece, French terry, velour, scuba, ponte, warp knit, tricot,
  knit mesh, sweaters, cardigans, knitwear, hosiery, socks, seamless wear, and T-shirts, polos
  and hoodies made from knit fabric. In Chinese: 针织, 经编, 纬编, 毛衫, 卫衣.
- **Mixed suppliers:** keep a supplier whose main line is woven (梭织 / 机织) even if it also
  has a small knit line. Mark it `mixed_knit_woven`. Exclude it if knit is half or more of
  what it sells, or if its description leads with knit.

## 2. Sources you must not use

Some websites have told AI tools not to access them. We respect that completely.

| Site | Rule |
|---|---|
| `cantonfair.org.cn` (all subdomains, including `365.cantonfair.org.cn`) | **Never open.** On **every** WebSearch call, pass `blocked_domains: ["cantonfair.org.cn"]`. Do not open its pages through caches, archives, translators, mirrors or proxies either. |
| `linkedin.com` | **Never open.** You may copy a LinkedIn URL that appears in search results. |
| `baidu.com` | Do not open (it blocks automated visitors). Use WebSearch instead. |
| `globalsources.com` | Do not open (it refuses automated visitors). |

On every site:

- Never log in, solve a CAPTCHA, or get around a paywall, block or "access denied" page.
  If a page refuses you or asks you to log in, move on to another source.
- Never contact anyone. Do not send emails, fill in forms or message suppliers.

## 3. Evidence rules

- **Every fact needs a source URL.** If you cannot point to a page, do not state it as a fact.
- **Never invent anything:** names, numbers, certificates, contacts or URLs. If you cannot
  find something, return `null`, an empty list, or "not found". An honest gap is useful. A
  guess is harmful.
- **Prefer primary sources:** the company's own website, official or registry pages,
  certification databases, third-party audit reports (SGS, BV, TÜV, Intertek). Marketplace
  listings are weaker.
- **Mark self-reported claims.** "We are a factory with 500 workers" on the company's own
  page is self-reported. A third-party audit saying the same is verified.
- **Note the date.** Write the year or Canton Fair session for anything time-sensitive.
  Recent sessions are the 136th (Oct 2024), 137th (Apr 2025), 138th (Oct 2025),
  139th (Apr–May 2026) and 140th (Oct–Nov 2026). Textiles and garments are in **Phase 3**.

## 4. Contact details

Collect only **business** contacts that the company publishes for sales: company email, sales
phone, WeChat ID, WhatsApp, website, LinkedIn URL, and the name and title of a published sales
contact. Do not collect personal data unrelated to the business, such as home addresses or
private social media. Record where you found each contact.

## 5. How to search

- Use the **WebSearch** tool (mode `standard`; use `extended` only when standard results
  are thin) and **WebFetch** to read pages. If you can't call these tools directly, load them
  with ToolSearch first.
- Search in **English and Chinese**. Useful Chinese terms: 广交会 (Canton Fair),
  梭织 (woven), 机织 (woven), 面料 (fabric), 服装厂 (garment factory), 工厂 / 生产厂家
  (factory), 贸易 / 进出口 / 商贸 (trading), 沙特 (Saudi), 中东 (Middle East).
- Good sources: company websites; `made-in-china.com` supplier pages, which show business
  type, audit reports, employees and trade shows; `alibaba.com` supplier pages; `1688.com`
  (domestic B2B); `tianyancha.com` company pages; certification databases (OEKO-TEX, GOTS,
  Textile Exchange); news sites.
- Keep it efficient. Stop researching a point once the evidence is clear.

## 6. Output

Return **only** the structured output your layer asks for. No extra commentary. Write text
fields in plain, simple English that a busy buyer can read quickly.
