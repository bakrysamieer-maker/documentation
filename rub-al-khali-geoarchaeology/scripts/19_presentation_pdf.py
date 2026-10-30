"""Step 19 - Arabic presentation of the findings (16:9 HTML deck -> PDF via Chromium).

All numbers are read from the pipeline outputs, so the deck cannot drift from the results.
Writes outputs/presentation/rub_al_khali_findings_ar.html and ..._ar.pdf
(rendered by scripts/render_pdf.js with the pre-installed Playwright Chromium).
"""
from __future__ import annotations

import html
import json
import re
import subprocess

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from common import CANDIDATES, INTERIM, OUTPUTS, PROCESSED, ROOT, read_raster

PRES = OUTPUTS / "presentation"
J = lambda name: json.loads((OUTPUTS / name).read_text())
aoi, sand, chg, anom, modern, score = (J("aoi_summary.json"), J("sand_mask_stats.json"),
                                       J("sand_change_stats.json"), J("anomaly_stats.json"),
                                       J("modern_infrastructure_stats.json"), J("score_info.json"))
s2 = J("s2_corridor_scenes.json")
cand = pd.read_csv(CANDIDATES / "top20_candidates.csv")
n_term = len(gpd.read_file(PROCESSED / "wadi_termini.geojson"))
n_course = len(gpd.read_file(PROCESSED / "projected_courses.geojson"))
dh, _ = read_raster(INTERIM / "dune_height_30m.tif")
sm, _ = read_raster(INTERIM / "sand_mask_30m.tif")
v = dh[::3, ::3][(sm[::3, ::3] == 1) & np.isfinite(dh[::3, ::3])]
dh_p50, dh_p90, dh_p99 = np.percentile(v, [50, 90, 99])
del dh, sm, v
with rasterio.open(INTERIM / "s1_g90.tif") as src:
    coh = src.read(list(src.descriptions).index("coh12") + 1)
m90, _ = read_raster(INTERIM / "corridor_mask_g90.tif")
coh_med = float(np.nanmedian(coh[m90 == 1]))
TOTAL_GB = 10.4          # all network transfer in this session (container counters), incl. re-reads

# Left-to-right islands for the Latin/numeric runs only (numbers, ranges, codes, file names).
# Arabic units stay in the RTL flow, so "150 كم" reads correctly; a leading >= or ~ is kept inside
# the island because those signs would otherwise be mirrored in right-to-left text.
_RUN = re.compile(r"[≥≤~]?\s?[0-9A-Za-z](?:[0-9A-Za-z.,:/%°×'_\-–+ ]*[0-9A-Za-z%°_/])?")
L = lambda s: _RUN.sub(lambda m: f'<span class="ltr">{m.group(0)}</span>', s)
fmt = lambda x, d=0: f"{x:,.{d}f}"
COUNTRY = {"Oman": "عُمان", "Saudi Arabia": "السعودية"}
REFS = {"Shisr": "شصر", "Umm Al Heesh lakes": "بحيرات أم الحيش", "Hamidan buried structure": "تركيب الحميدان",
        "Muqshin village": "قرية مقشن", "Muqshin": "مقشن", "Umm as Samim sabkha": "سبخة أم السميم"}
CLUE_AR = {"1": "١ معادن الينابيع", "3": "٣ نهاية وادٍ", "5": "٥ منخفض مائي", "2/4": "٢/٤ مسار",
           "4": "٤ شذوذ هندسي", "6": "٦ رمال رقيقة"}


def clues(s):
    if not isinstance(s, str) or not s:
        return "—"
    codes = [p.strip().split(" ")[0] for p in s.split(";")]
    return "، ".join(CLUE_AR.get(c, c) for c in codes)


def near(s):
    m = re.match(r"(.+) \((\d+) km\)", s)
    return f"{REFS.get(m.group(1), m.group(1))} ({L(m.group(2) + ' كم')})" if m else s


dates = s2["chosen_dates"]
w = score["weights"]
bear = "، ".join(f"{b:.0f}°" for b in anom["shisr_track_bearings"])
trk = gpd.read_file(PROCESSED / "shisr_tracks.geojson").query("part == 'detected'")
trk_km = f"{trk['segment_km'].min():.1f}–{trk['segment_km'].max():.1f}"
trk_mod = f"{trk['mapped_modern_fraction'].min() * 100:.0f}–{trk['mapped_modern_fraction'].max() * 100:.0f}%"
cc = cand["country_approx"].value_counts().to_dict()

# ------------------------------------------------------------------ slides
S = []

S.append(f"""
<section class="slide title-slide">
  <div class="kicker">نتائج أولية · دراسة مكتبية بالاستشعار عن بُعد</div>
  <h1>فحص جنوب الربع الخالي ببيانات الأقمار الصناعية المجانية</h1>
  <p class="subtitle">مواقع مرشَّحة لمستوطنات قديمة حيث تنتهي أودية ظفار في الرمال</p>
  <p class="meta">ممر شصر – بحيرات أم الحيش · سلطنة عُمان والمملكة العربية السعودية · أكتوبر {L('2026')}</p>
  <div class="callout warn"><b>⚠ تنبيه:</b> كل ما في هذا العرض <b>مواقع مرشَّحة</b> لمراجعة المختصين وليست اكتشافات.
  الدراسة مكتبية فقط في منطقة حدودية حساسة، ولا تتضمن أي تخطيط لزيارات ميدانية.</div>
</section>""")

S.append(f"""
<section class="slide">
  <h2>الفرضية والقرائن الست</h2>
  <p class="lead">تفترض الفرضية أن مستوطنات قديمة — ربما مرتبطة بقوم عاد المذكورين في القرآن الكريم — قد تقع عند الحافة
  الجنوبية للربع الخالي، حيث تنتهي الأودية المنحدرة شمالاً من هضبة ظفار وحضرموت في الرمال. حوّلنا كل قرينة إلى طبقة قابلة للقياس:</p>
  <table class="grid">
    <thead><tr><th>القرينة</th><th>ما قسناه</th><th>البيانات</th></tr></thead>
    <tbody>
      <tr><td>١ جنّات وعيون</td><td>رواسب ينابيع أحفورية (كربونات وجبس)</td><td>ASTER (لم يتوفر بعد) ← مؤشر بديل من Sentinel-2</td></tr>
      <tr><td>٢ أعلام حجرية على الطرق والمرتفعات</td><td>خطوط ومحاذاة، وصفوف الأحجار الثلاثية</td><td>Sentinel-2 · إحداثيات المواقع المنشورة (لم تتوفر بعد)</td></tr>
      <tr><td>٣ أودية تنفتح شمالاً على الرمال</td><td>نهايات الأودية تحت الكثبان ومجاريها المدفونة المتوقعة</td><td>نموذج الارتفاع Copernicus</td></tr>
      <tr><td>٤ طرق القوافل</td><td>مسارات تنطلق من شصر وامتدادها في الرمال؛ أشكال مستطيلة ودائرية</td><td>Sentinel-2 بدقة {L('20 م')}</td></tr>
      <tr><td>٥ مياه جوفية نحو أم الحيش والمعترضة</td><td>منخفضات على «سطح ما تحت الكثبان» وأسطح رطبة</td><td>نموذج الارتفاع + Sentinel-2</td></tr>
      <tr><td>٦ دفن سطحي فقط</td><td>رمال رقيقة أو حديثة</td><td>نموذج الارتفاع · Landsat {L('1972')} · Sentinel-1</td></tr>
    </tbody>
  </table>
</section>""")

S.append(f"""
<section class="slide two">
  <div class="text">
    <h2>منطقة الدراسة</h2>
    <ul>
      <li>ممر بعرض {L('150 كم')} يبدأ من شصر ({L('18.255° ش، 53.649° ق')}) باتجاه {L(f"{aoi['corridor_bearing_deg']}°")}
      نحو بحيرات أم الحيش ({L('20.70° ش، 54.73° ق')}) بطول {L(f"{aoi['shisr_to_umm_al_heesh_km']} كم")}.</li>
      <li>مروحة بنصف قطر {L('140 كم')} شمال غرب شصر لتغطية المسارات الداخلة إلى الرمال ومنطقة مَيتان.</li>
      <li>المساحة المحللة: {L(fmt(aoi['area_km2']['corridor']) + ' كم²')}؛ صندوق التنزيل: خطوط الطول
      {L('52.35–55.50° ق')} ودوائر العرض {L('17.80–21.15° ش')}.</li>
      <li>أدنى نقطة في نموذج الارتفاع المنعَّم شمال {L('19.5° ش')} تقع على بعد {L('8 كم')} من موقع سبخة أم السميم المنشور
      ({L('61 م')} فوق سطح البحر) — تأكيد مستقل لمنخفض المعترضة – أم السميم.</li>
      <li>الحدود الدولية تقريبية (Natural Earth بمقياس {L('1:10m')}).</li>
    </ul>
  </div>
  <figure><img src="figures/overview.png" alt="خريطة منطقة الدراسة"><figcaption>صورة Sentinel-2 (شتاء {L('2024–2025')}) · الأحمر: الممر المحلل · المتقطع الأبيض: الحدود</figcaption></figure>
</section>""")

S.append(f"""
<section class="slide">
  <h2>التحقق من الإحداثيات المنشورة على صور Sentinel-2 بدقة {L('10 م')}</h2>
  <div class="three">
    <figure><img src="figures/check_shisr.png" alt=""><figcaption><b>شصر:</b> الإحداثي يقع وسط القرية، وتحيط به حقول ري محوري ومسارات حديثة —
    أشباه حديثة لقرينتي «الدوائر» و«المسارات المتشعبة من شصر».</figcaption></figure>
    <figure><img src="figures/check_umm_al_heesh.png" alt=""><figcaption><b>أم الحيش:</b> بحيرة وأرض رطبة على بعد {L('0.3–1.5 كم')} شمال الإحداثي.
    ماؤها الحالي مصدره بئر نفطية استكشافية مسرّبة (Kazak وآخرون {L('2025')}) — ماء حديث لا يدل على عيون قديمة.</figcaption></figure>
    <figure><img src="figures/check_muqshin_s2.png" alt=""><figcaption><b>مقشن:</b> إحداثي ويكيبيديا الإنجليزية يقع على رمال جرداء؛ القرية الفعلية
    ووادٍ نباتي على حافة الرمال عند {L('19.560° ش، 54.885° ق')} — أي على بعد نحو {L('30 كم')}.</figcaption></figure>
  </div>
</section>""")

S.append(f"""
<section class="slide">
  <h2>البيانات المستخدمة (مجانية بالكامل)</h2>
  <table class="grid">
    <thead><tr><th>المصدر</th><th>التاريخ</th><th>الدقة</th><th>الاستخدام</th></tr></thead>
    <tbody>
      <tr><td>نموذج الارتفاع Copernicus GLO-30 / GLO-90</td><td>{L('2011–2015')}</td><td>{L('30 / 90 م')}</td><td>الأودية، الكثبان، المنخفضات</td></tr>
      <tr><td>Sentinel-2 L2A (Collection 1)، {L('17')} مربعاً</td><td>{L(dates['late'])} و{L(dates['early'])}</td><td>{L('10–20 م')}</td><td>الرمال، المعادن (بديل)، الخطوط</td></tr>
      <tr><td>Sentinel-1 (البيانات الموسمية العالمية، Kellndorfer {L('2022')})</td><td>{L('2019–2020')}</td><td>{L('~90 م')}</td><td>خشونة السطح وحركة الرمال</td></tr>
      <tr><td>Landsat-1 MSS، {L('7')} مشاهد</td><td>{L('1972–1973')}</td><td>{L('60 م')}</td><td>تغير الغطاء الرملي خلال {L(str(chg['years']))} سنة</td></tr>
      <tr><td>OpenStreetMap عبر Overture Maps</td><td>{L('2026')}</td><td>متجهات</td><td>أقنعة المنشآت الحديثة</td></tr>
    </tbody>
  </table>
  <div class="callout"><b>لم يتوفر في هذه الجلسة:</b> بيانات ASTER (تحتاج حساب Google Earth Engine أو NASA Earthdata) وإحداثيات المواقع الأثرية المنشورة
  (نطاقات Zenodo وOSF محجوبة في إعدادات الشبكة). حُضِّرت الشيفرة لتعمل فور إتاحتها.</div>
  <p class="small">حجم البيانات المنقولة في الجلسة كلها نحو {L(f'{TOTAL_GB} GB')} (يشمل إعادة قراءة Sentinel-2 لإزالة خطوط التماس)، ولم يتجاوز أي تنزيل منفرد {L('5 GB')}.</p>
</section>""")

steps = ["تحديد الممر والتحقق من الإحداثيات", "تنزيل البيانات المفتوحة وتوحيد الإسقاط (UTM 40N)",
         "بناء طبقات القرائن الست", "أقنعة المنشآت الحديثة والمزارع وخطوط المسح الزلزالي",
         f"درجة مرجّحة لكل خلية {L('1 كم')}", "أعلى 20 موقعاً مع تفسيرات طبيعية لكل منها", "خريطة تفاعلية بأوزان قابلة للتعديل، وهذا العرض"]
S.append(f"""
<section class="slide">
  <h2>المنهجية</h2>
  <ol class="flow">{''.join(f'<li><span class="num">{i}</span>{s}</li>' for i, s in enumerate(steps, 1))}</ol>
  <ul class="cols">
    <li>تاريخ واحد لكل مدار للقمر Sentinel-2 مع مطابقة إشعاعية للمدار الثاني، لأن خلط التواريخ أنتج «خطوط تماس» زائفة.</li>
    <li>استبعاد حواف المزارع وحدود مربعات Sentinel-2 قبل رصد الخطوط، لأنها كانت تطغى على المسارات الباهتة.</li>
    <li>كل خطوة شيفرة Python قابلة لإعادة التشغيل في مجلد المشروع، وجميع المصادر موثقة.</li>
  </ul>
</section>""")

S.append(f"""
<section class="slide two">
  <div class="text">
    <h2>القرينة ٣: أودية تختفي تحت الكثبان</h2>
    <ul>
      <li><b>{L(str(n_term))}</b> نهاية وادٍ تدخل الرمال (حوض تجميع {L('≥ 20 كم²')}، وحوض علوي خالٍ من الرمال بنسبة {L('≥ 70%')}، ويظل الوادي تحت الرمال {L('2.7 كم')} على الأقل).</li>
      <li><b>{L(str(n_course))}</b> مجرى مدفوناً متوقعاً حتى {L('40 كم')}، محسوباً على «سطح ما تحت الكثبان» (أرضيات ما بين الكثبان) لا على قمم الكثبان.</li>
      <li>تتركز النهايات على جبهة الرمال القطرية من الجنوب الغربي إلى الشمال الشرقي، ومجموعة ثانية حيث تدخل أودية شرقية حقول الكثبان قرب أم الحيش.</li>
      <li class="caveat">هذه ظواهر هيدرولوجية طبيعية؛ وجودها شرط ملائم للاستيطان لكنه ليس دليلاً عليه.</li>
    </ul>
    <div class="legend"><span><i class="sw" style="background:#2a78d6"></i>وادٍ (حوض {L('≥ 50 كم²')})</span>
    <span><i class="sw" style="background:#e34948"></i>نهاية وادٍ تحت الكثبان</span>
    <span><i class="ln dash" style="border-color:#5be0ff"></i>مجرى مدفون متوقع</span></div>
  </div>
  <figure><img src="figures/drainage.png" alt=""></figure>
</section>""")

S.append(f"""
<section class="slide">
  <h2>القرينة ٦: أين الرمال رقيقة أو حديثة؟</h2>
  <div class="three">
    <figure><img src="figures/dune_height.png" alt=""><figcaption><b>ارتفاع الكثبان</b> فوق سطح ما تحتها: الوسيط {L(f'{dh_p50:.1f} م')}، المئين 90: {L(f'{dh_p90:.0f} م')}، المئين 99: {L(f'{dh_p99:.0f} م')}.</figcaption></figure>
    <figure><img src="figures/sand_change.png" alt=""><figcaption><b>{L('1972–1973')} مقابل {L('2024–2025')}:</b>
    <i class="sw" style="background:#eb6834"></i>رمال اكتسبت <i class="sw" style="background:#2a78d6"></i>رمال انحسرت <i class="sw" style="background:#1baf7a"></i>رمال ثابتة.
    إزاحة الكثبان: وسيط {L(f"{chg['median_shift_m']:.0f} م")} في {L(str(chg['years']))} سنة (مؤشر فقط).</figcaption></figure>
    <figure><img src="figures/radar_mobility.png" alt=""><figcaption><b>حركة الرمال بالرادار</b> (١ − ترابط Sentinel-1 لـ {L('12')} يوماً): وسيط الترابط {L(f'{coh_med:.2f}')}؛ الداكن = رمال نشطة.</figcaption></figure>
  </div>
  <p class="small">الرمال تغطي {L(f"{sand['sand_fraction_of_corridor'] * 100:.1f}%")} من الممر. صور MSS لعام {L('1972')} فيها تشوّه خطوط أفقية من المستشعر، لذا قورنت كل منطقة بنفسها (مطابقة توزيعات) وتبقى نتائج التغير نسبية؛
  والكتل المستطيلة الحادة في خريطة التغير تتبع حدود مشاهد Landsat، فهي على الأرجح تشوّه في المعالجة وليست تغيراً حقيقياً.</p>
</section>""")

S.append(f"""
<section class="slide two">
  <div class="text">
    <h2>القرينتان ٢ و٤: المسارات والأشكال الهندسية</h2>
    <ul>
      <li>رُصد {L(fmt(anom['segments']))} مقطعاً خطياً بدقة {L('20 م')} في الممر.</li>
      <li>اتجاهات ضعيفة تتلاقى في شصر: <b>{L(bear)}</b> — لكل منها {L(trk_km)} كم فقط من المقاطع، و{L(trk_mod)} منها على طرق حديثة مُخرَّطة. امتدت خطوطها {L('40 كم')} داخل الرمال.</li>
      <li>خطوط مستقيمة متوازية شرق–غرب بتباعد {L('2–2.5 كم')} على بعد نحو {L('45 كم')} شمال-شمال شرق شصر: نمط خطوط مسح زلزالي نفطي — إيجابية كاذبة مُعلَّمة.</li>
      <li>{L(str(anom['corners']))} «زاوية قائمة» فقط في كامل الممر: الجدران والمباني القديمة أصغر من دقة {L('10–20 م')}.</li>
      <li>{L(str(anom['circles']))} شكلاً دائرياً، منها {L(str(anom['circles_near_modern']))} عند مزارع أو منشآت حديثة.</li>
      <li>محاذاة الأحجار الثلاثية: تحتاج إحداثيات منشورة لم تتوفر بعد.</li>
    </ul>
    <div class="legend"><span><i class="ln" style="border-color:#1baf7a"></i>مسار من شصر (المتقطع: الامتداد)</span>
    <span><i class="ln" style="border-color:#eda100"></i>مقطع خطي مرصود</span><span><i class="ln" style="border-color:#e34948"></i>طريق حديث مُخرَّط</span>
    <span><i class="ln dash" style="border-color:#9a9a9a"></i>خط مستقيم طويل (زلزالي محتمل)</span></div>
  </div>
  <figure><img src="figures/shisr_tracks.png" alt=""></figure>
</section>""")

S.append(f"""
<section class="slide">
  <h2>القرينتان ١ و٥: المعادن والمنخفضات المائية</h2>
  <div class="two-figs">
    <figure><img src="figures/pale_crust.png" alt=""><figcaption><b>مؤشر «القشرة الفاتحة» (بديل):</b> سطح فاتح يمتص الأشعة تحت الحمراء القصيرة وغير مصبوغ بالحديد.
    لا يميز الكربونات عن الجبس أو الكالكريت أو أملاح السبخات، لذا وُزن بنصف القيمة ولا يمكنه وحده «إثبات» قرينة الينابيع.</figcaption></figure>
    <figure><img src="figures/groundwater_lows.png" alt=""><figcaption><b>المنخفضات المائية:</b> منخفضات مغلقة على سطح ما تحت الكثبان، وانخفاض إقليمي، وأسطح رطبة.
    أبرزها سبخات بين الكثبان شرق أم الحيش (جهة منخفض المعترضة) — مناطق تصريف طبيعي للمياه الجوفية.</figcaption></figure>
  </div>
  <p class="small">عند توفر حساب Earth Engine يُستبدل المؤشر البديل بمؤشرات ASTER: الكالسيت ({L('2.33 ميكرومتر')})، والكربونات والكبريتات من الأشعة الحرارية، ودرجة الحرارة الليلية.</p>
</section>""")

wrows = "".join(f"<tr><td>{a}</td><td class='num'>{L(f'{100 * w[k] / sum(w.values()):.0f}%')}</td></tr>" for k, a in [
    ("wadi_terminus", "٣ نهاية وادٍ تحت الكثبان"), ("spring_minerals", "١ معادن الينابيع (بديل × 0.5)"),
    ("groundwater_lows", "٥ منخفض على مسار المياه الجوفية"), ("tracks_alignments", "٢/٤ مسارات ومحاذاة"),
    ("geometric_anomalies", "٤ شذوذ هندسي"), ("thin_sand", "٦ رمال رقيقة أو حديثة")])
S.append(f"""
<section class="slide two">
  <div class="text">
    <h2>الدرجة المرجَّحة وأعلى 20 موقعاً مرشحاً</h2>
    <table class="grid compact"><thead><tr><th>القرينة</th><th>الوزن</th></tr></thead><tbody>{wrows}</tbody></table>
    <ul class="small">
      <li>تُحجب المنشآت الحديثة بمسافة {L('300 م')}، وتُستبعد المزارع، وتُضرب خلايا خطوط المسح الزلزالي في {L('0.5')}.</li>
      <li>يفصل بين المواقع {L('5 كم')} على الأقل. التوزيع: {L(str(cc.get('Oman', 0)))} في عُمان و{L(str(cc.get('Saudi Arabia', 0)))} في السعودية (تقريبياً).</li>
      <li>يمكن تعديل الأوزان والأقنعة مباشرة في الخريطة التفاعلية فيُعاد الترتيب فوراً.</li>
    </ul>
    <div class="legend"><span><i class="sw" style="background:linear-gradient(90deg,#cde2fb,#3987e5,#0d366b)"></i>الدرجة (منخفضة ← مرتفعة)</span></div>
  </div>
  <figure><img src="figures/score_candidates.png" alt=""></figure>
</section>""")

rows = "".join(
    f"<tr><td>{L(r['candidate_id'])}</td><td class='num'>{L(f'{r.lat:.4f}')}</td><td class='num'>{L(f'{r.lon:.4f}')}</td>"
    f"<td>{COUNTRY.get(r['country_approx'], r['country_approx'])}</td><td class='num'>{L(f'{r.score:.3f}')}</td>"
    f"<td>{clues(r['clues_satisfied'])}</td><td>{near(r['nearest_reference'])}</td></tr>" for _, r in cand.iterrows())
S.append(f"""
<section class="slide">
  <h2>جدول أعلى 20 موقعاً مرشحاً (وليست اكتشافات)</h2>
  <table class="grid dense"><thead><tr><th>الرمز</th><th>العرض °ش</th><th>الطول °ق</th><th>الدولة</th><th>الدرجة</th><th>القرائن المتحققة ({L('≥ 0.5')})</th><th>أقرب مرجع</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <p class="small">لكل موقع صورة تفصيلية ({L('4×4 كم')}) وقائمة تفسيرات طبيعية أو حديثة في ملف {L('top20_candidates.csv')} وفي الخريطة التفاعلية. قرينة المعادن لا تبلغ {L('0.5')} لأن مؤشرها البديل محدود عمداً.</p>
</section>""")

examples = {
    "C01": ("سبخة واسعة بين الكثبان ذات قشرة ملحية، والأشكال «الدائرية» المرصودة أنماط ملحية. تقع في جهة منخفض المعترضة حيث تصرَّف المياه الجوفية طبيعياً. "
            "مكان من هذا النوع قد يحوي رواسب بحيرات قديمة، لكن لا يظهر أي أثر بشري بهذه الدقة.",
            "سبخة طبيعية؛ تبخّر وتسرّب حديث؛ رواسب بحيرات قديمة."),
    "C03": ("كثبان هلالية على صفيحة رملية قرب نهاية وادٍ، ويمر بها خط الاتجاه الشمالي من شصر. المقاطع الخطية المرصودة هي حواف أوجه الانزلاق للكثبان.",
            "حواف الكثبان؛ مسارات سيارات حديثة غير مُخرَّطة؛ رواسب مروحة الوادي."),
    "C11": ("كثبان قبابية ونجمية على سهل منبسط في المروحة الشمالية الغربية، قرب نهاية وادٍ ومجراه المدفون المتوقع، في الجوار العام لمنطقة مَيتان التي نُشرت فيها مواقع من العصر الحجري الحديث. "
            "الخطوط المرصودة أوجه انزلاق للكثبان.",
            "أوجه انزلاق الكثبان؛ رواسب الوادي الطرفية."),
}
for cid, (desc, nat) in examples.items():
    r = cand.set_index("candidate_id").loc[cid]
    S.append(f"""
<section class="slide">
  <h2>مثال: الموقع المرشح {L(cid)} — {L(f'{r.lat:.3f}° ش، {r.lon:.3f}° ق')} ({COUNTRY.get(r['country_approx'], '')})</h2>
  <figure class="wide"><img src="figures/candidate_{cid}.png" alt=""><figcaption>من اليمين إلى اليسار: الخطوط المرصودة على نطاق الأحمر ({L('20 م')}) · تظليل نموذج الارتفاع مع نهايات الأودية (▲) والمجرى المدفون المتوقع · صورة Sentinel-2 بالألوان الطبيعية ({L('10 م')}). المربع المتقطع = خلية {L('1 كم')}.</figcaption></figure>
  <div class="two-notes">
    <div><b>القراءة:</b> {desc}</div>
    <div class="nat"><b>تفسيرات طبيعية أو حديثة محتملة:</b> {nat}</div>
  </div>
  <p class="small">الدرجة {L(f'{r.score:.3f}')} · القرائن المتحققة: {clues(r['clues_satisfied'])}</p>
</section>""")

S.append(f"""
<section class="slide">
  <h2>أبرز النتائج</h2>
  <ol class="findings">
    <li><b>لا دليل قاطع</b> في البيانات المجانية ({L('10–90 م')}) على مستوطنات أو مبانٍ مدفونة؛ النتائج مواقع مرشحة لمراجعة المختصين فقط.</li>
    <li>تتجمع المواقع المرشحة في <b>ثلاث بيئات</b>: (أ) جبهة الرمال على بعد {L('30–90 كم')} شمال شصر حيث تنتهي الأودية وتمر اتجاهات المسارات الضعيفة؛
    (ب) المروحة الشمالية الغربية قرب {L('53° ق، 18.6° ش')} في الجوار العام لمواقع مَيتان المنشورة؛ (ج) سبخات بين الكثبان شرق أم الحيش.</li>
    <li>القرائن الأقوى <b>طبيعية</b> (نهايات الأودية، المنخفضات، الرمال الرقيقة)، أما القرائن «البشرية» (المسارات والأشكال الهندسية) فضعيفة وتطغى عليها أشباه حديثة: مسارات السيارات، والري المحوري، وخطوط المسح الزلزالي.</li>
    <li>بحيرة أم الحيش الحالية تغذيها بئر مسرّبة حديثة؛ أما السبخات حولها فتدل على منطقة تصريف طبيعي للمياه الجوفية.</li>
    <li>تتسق النتائج مع دراسة Dellmour وآخرين في Nature ({L('2026')}): ارتبط الاستيطان القديم بتلاقي الماء والحجر الصالح لصنع الأدوات عند أطراف الصحراء، ولم تُعثر على آثار في عمق الربع الخالي.</li>
    <li>لا يمكن للاستشعار عن بُعد وحده إثبات نسبة أي موقع إلى قوم عاد؛ التأريخ والنسبة يحتاجان إلى دراسة أثرية متخصصة. كما أن مطابقة شصر لمدينة «أوبار» نفسها موضع خلاف.</li>
  </ol>
</section>""")

S.append(f"""
<section class="slide two-even">
  <div><h2>القيود</h2><ul>
    <li>دقة {L('10–20 م')} لا تُظهر الجدران والمباني والأحجار الثلاثية.</li>
    <li>غياب ASTER: قرينة الينابيع مقيسة بمؤشر بديل غير محدد.</li>
    <li>لا مواقع تدريب منشورة متاحة، فلم يُدرَّب نموذج التعلم الآلي.</li>
    <li>نموذج الارتفاع يقيس سطح الكثبان؛ «سطح ما تحت الكثبان» تقدير.</li>
    <li>صور {L('1972')} مشوهة بخطوط المستشعر؛ نتائج تغير الرمال نسبية.</li>
    <li>رصد المسارات الباهتة منخفض الحساسية؛ كثير منها لم يُرصد.</li>
    <li>الأوزان اجتهادية ويمكن تغييرها؛ ولا يوجد تحقق ميداني (ولن يُجرى ضمن هذا العمل).</li>
  </ul></div>
  <div><h2>مخاطر الإيجابيات الكاذبة</h2><ul>
    <li>السبخات والقشور الملحية والجبس الطبيعي.</li>
    <li>الكالكريت ورواسب البحيرات القديمة (طبيعية لكنها مهمة بيئياً).</li>
    <li>مراوح الأودية ورواسبها الطرفية.</li>
    <li>أوجه انزلاق الكثبان وندوب التذرية.</li>
    <li>فواصل الصخور الجيرية المتعامدة والحفر الكارستية.</li>
    <li>مسارات السيارات الحديثة غير المُخرَّطة المتشعبة من شصر.</li>
    <li>خطوط المسح الزلزالي النفطي وخطوط الأنابيب والكهرباء.</li>
    <li>مزارع الري المحوري حول شصر.</li>
    <li>البئر المسرّبة في أم الحيش.</li>
  </ul></div>
</section>""")

S.append(f"""
<section class="slide">
  <h2>الخطوات التالية (مكتبية فقط)</h2>
  <ol class="findings">
    <li>تشغيل مؤشرات ASTER عبر Google Earth Engine بإضافة مفتاح حساب خدمة باسم {L('EE_SERVICE_ACCOUNT_JSON')} في إعدادات البيئة (لا يُلصق المفتاح في المحادثة).</li>
    <li>إتاحة نطاقات {L('zenodo.org')} و{L('osf.io')} و{L('files.osf.io')} لجلب إحداثيات Dellmour {L('2026')} ({L('125')} موقعاً)، ثم تدريب النموذج والتحقق المكاني منه ورسم محاذاة الأحجار الثلاثية.</li>
    <li>مراجعة المواقع المرشحة على صور عالية الدقة (أرشيف Google Earth وBing) من قِبل مختصين في الآثار والجيومورفولوجيا.</li>
    <li>عرض النتائج على الجهات المختصة (وزارة التراث والسياحة في عُمان، وهيئة التراث في السعودية) قبل أي متابعة. لا زيارات ميدانية ضمن هذا العمل.</li>
  </ol>
  <div class="callout"><b>المخرجات في مجلد المشروع:</b> الخريطة التفاعلية {L('outputs/maps/rub_al_khali_candidates.html')} ·
  جدول المواقع {L('outputs/candidates/top20_candidates.csv')} · الصور التفصيلية {L('outputs/candidates/snapshots/')} · التقرير {L('reports/report.md')} · الشيفرة {L('scripts/')}</div>
</section>""")

refs = [
    "Dellmour, R. et al. (2026). Stone and water governed early human settlement of the desert. Nature. doi:10.1038/s41586-026-11180-5",
    "Kazak, E.S. et al. (2025). Origin of Umm Al Heesh lake in the Rub' Al Khali desert, Saudi Arabia. Scientific Reports 15, 34850.",
    "Neville, A.S. et al. (2014). Five buried crater structures imaged on reflection seismic data in Saudi Arabia. GeoArabia 19(1), 17–44.",
    "Matter, A. et al. (2015). Lake and sabkha deposits of the southern Rub' al-Khali, Saudi Arabia and Oman. Quaternary International 382, 120–131.",
    "Maiorano, M.P. et al. (2020). Living and moving in Maitan. Proceedings of the Seminar for Arabian Studies 50.",
    "Al Kindi, M. et al. (2021). Geo-archaeological survey around Maitan, Oman. Historical Biology 33(9), 1534–1555.",
    "Rose, J.I. et al. (2011). The Nubian Complex of Dhofar, Oman. PLoS ONE 6(11), e28239.",
    "Blom, R.G., Crippen, R., Elachi, C. et al. JPL remote sensing of Ubar/Shisr caravan tracks (1990s; IGARSS 2000).",
    "USGS Open-File Report 82-387: brine reconnaissance, eastern Rub al Khali (Uruq al Mu'taridah – Umm as Samim).",
    "Kellndorfer, J. et al. (2022). Global seasonal Sentinel-1 interferometric coherence and backscatter. Scientific Data 9, 73.",
    "Ninomiya, Y. (2002, 2003). ASTER TIR and SWIR mineral indices.",
    "Copernicus DEM (ESA, © DLR/Airbus); Sentinel-1/2 (ESA/Copernicus); Landsat (USGS/NASA); OpenStreetMap contributors via Overture Maps; Natural Earth.",
]
S.append(f"""
<section class="slide">
  <h2>المصادر</h2>
  <ul class="refs" dir="ltr">{''.join(f'<li>{html.escape(r)}</li>' for r in refs)}</ul>
</section>""")

N = len(S)
S = [s.replace('<section class="slide', f'<section data-n="{i}" class="slide', 1) for i, s in enumerate(S, 1)]

font = (ROOT / "data" / "reference" / "fonts" / "NotoSansArabic[wdth,wght].ttf").as_uri().replace("[", "%5B").replace("]", "%5D")
CSS = """
@font-face { font-family: "Noto Sans Arabic"; src: url("FONT") format("truetype"); font-weight: 100 900; }
@page { size: 1280px 720px; margin: 0; }
:root { --ink: #0b0b0b; --ink2: #52514e; --muted: #898781; --surface: #fcfcfb; --panel: #f3f2ee; --line: #e1e0d9;
  --accent: #2a78d6; --warn: #d03b3b; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #d9d6cf; }
body { font-family: "Noto Sans Arabic", "DejaVu Sans", sans-serif; color: var(--ink); direction: rtl; }
.slide { width: 1280px; height: 720px; position: relative; overflow: hidden; background: var(--surface);
  padding: 44px 56px 56px; page-break-after: always; break-after: page; margin: 0 auto; }
.slide::after { content: "مواقع مرشَّحة — ليست اكتشافات · دراسة مكتبية فقط"; position: absolute; bottom: 18px; right: 56px;
  font-size: 13px; color: var(--muted); }
.slide::before { content: attr(data-n) " / NTOTAL"; position: absolute; bottom: 18px; left: 56px; font-size: 13px;
  color: var(--muted); direction: ltr; }
h1 { font-size: 46px; line-height: 1.35; margin: 0 0 14px; font-weight: 700; }
h2 { font-size: 29px; line-height: 1.35; margin: 0 0 16px; font-weight: 700; }
p, li { font-size: 18px; line-height: 1.65; color: var(--ink); }
ul, ol { margin: 0; padding-right: 22px; padding-left: 0; }
li { margin-bottom: 6px; }
.ltr { direction: ltr; unicode-bidi: isolate; }
.lead { font-size: 18px; color: var(--ink2); margin: 0 0 14px; }
.small, .small li { font-size: 14.5px; color: var(--ink2); line-height: 1.6; }
.caveat { color: var(--ink2); font-style: italic; }
.title-slide { display: flex; flex-direction: column; justify-content: center; padding: 70px 90px;
  background: linear-gradient(135deg, #fcfcfb 55%, #f6e7dc); }
.kicker { font-size: 18px; color: var(--accent); font-weight: 600; margin-bottom: 14px; }
.subtitle { font-size: 26px; color: var(--ink2); margin: 0 0 10px; }
.meta { font-size: 18px; color: var(--muted); margin: 0 0 30px; }
.callout { background: var(--panel); border-right: 5px solid var(--accent); padding: 14px 18px; border-radius: 6px;
  font-size: 16.5px; line-height: 1.65; margin-top: 14px; }
.callout.warn { border-right-color: var(--warn); font-size: 18px; }
table.grid { width: 100%; border-collapse: collapse; font-size: 15.5px; }
table.grid th { text-align: right; color: var(--ink2); font-weight: 600; border-bottom: 2px solid var(--line); padding: 8px 10px; }
table.grid td { border-bottom: 1px solid var(--line); padding: 8px 10px; vertical-align: top; line-height: 1.5; }
table.grid.compact td, table.grid.compact th { padding: 5px 8px; font-size: 15px; }
table.grid.dense td, table.grid.dense th { padding: 3px 7px; font-size: 12.5px; line-height: 1.35; }
td.num { text-align: left; font-variant-numeric: tabular-nums; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 34px; align-items: start; }
.two .text { min-width: 0; }
.two figure { margin: 0; height: 620px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.two figure img { max-width: 100%; max-height: 585px; object-fit: contain; border-radius: 4px; }
.two-even { display: grid; grid-template-columns: 1fr 1fr; gap: 44px; }
.two-even li { font-size: 16.5px; }
figure { margin: 0; }
figcaption { font-size: 13.5px; color: var(--ink2); line-height: 1.55; margin-top: 6px; }
.three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; }
.three figure img { width: 100%; max-height: 430px; object-fit: contain; border-radius: 4px; background: #fff; }
.two-figs { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
.two-figs img { width: 100%; max-height: 430px; object-fit: contain; }
figure.wide img { width: 100%; max-height: 360px; object-fit: contain; }
.two-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 12px; font-size: 16.5px; line-height: 1.65; }
.two-notes .nat { background: var(--panel); padding: 10px 14px; border-radius: 6px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 12px; font-size: 14px; color: var(--ink2); }
.sw { display: inline-block; width: 14px; height: 10px; border-radius: 2px; margin-left: 6px; vertical-align: middle; }
.ln { display: inline-block; width: 22px; border-top: 3px solid; margin-left: 6px; vertical-align: middle; }
.ln.dash { border-top-style: dashed; }
ol.flow { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin: 6px 0 24px; }
ol.flow li { background: var(--panel); border-radius: 8px; padding: 12px 10px; font-size: 14.5px; line-height: 1.5; min-height: 132px;
  position: relative; margin: 0; }
ol.flow .num { display: block; font-size: 22px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }
ul.cols li { font-size: 16.5px; }
ol.findings li { font-size: 17px; margin-bottom: 10px; }
ul.refs { padding-left: 22px; padding-right: 0; }
ul.refs li { font-size: 13.5px; line-height: 1.5; text-align: left; font-family: "DejaVu Sans", sans-serif; color: var(--ink2); }
@media screen { .slide { margin: 16px auto; box-shadow: 0 1px 4px rgba(0,0,0,.15); } }
""".replace("FONT", font).replace("NTOTAL", str(N))

doc = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rub' al-Khali Findings (Arabic)</title><style>{CSS}</style></head><body>{''.join(S)}</body></html>"""
out_html = PRES / "rub_al_khali_findings_ar.html"
out_html.write_text(doc, encoding="utf-8")
out_pdf = PRES / "rub_al_khali_findings_ar.pdf"
subprocess.run(["node", str(ROOT / "scripts" / "render_pdf.js"), str(out_html), str(out_pdf), str(PRES / "slides_png")],
               check=True)
print("wrote", out_pdf, f"{out_pdf.stat().st_size / 1e6:.1f} MB,", N, "slides")
