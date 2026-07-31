# research-graph — Tasarım Dokümanı

**Tarih:** 2026-07-31
**Durum:** Tasarım onaylandı, uygulama planı bekliyor
**Kaynak artefakt:** `output/agentic-workflow-3x2_CLAUDE_v5_claude_revised.html` (v5.1, 110 KB, kendi kendine yeten tek dosya)

---

## 1. Amaç

LinkedIn'de paylaşılacak bir graph engineering postunun arkasına, okuyucunun gerçekten
klonlayıp kendi araştırmasında koşturabileceği bir kit koymak. Mevcut interaktif diyagram
sayfanın yüzü; kit ise diyagramın iddialarını **makineyle doğrulayan** katman.

**Tek cümlelik konum:** Graph engineering kurallarını söyleyen değil, **zorlayan** araç.

---

## 2. Pazar bulgusu (2026-07-31 itibarıyla)

"Graph engineering" terimi bu ayın içinde doğdu. Ölçüm günü 31 Temmuz:

| Repo | Açılış | Yaş | ★ |
|---|---|---|---|
| `deerwork-ai/deer-workflow` | 26 Tem | 5 gün | 366 |
| `codejunkie99/graph-engineering` | 23 Tem | 8 gün | 222 |
| `ZacharyZhang-NY/Kigi-CLI` | 17 Tem | 14 gün | 54 |
| `CodeGraphContext/GraphARC` | 27 Tem | 4 gün | 13 |
| `ChaoYue0307/awesome-graph-engineering` | 19 Tem | 12 gün | 12 |
| `InjayTseng/graph-engineering-on-research` | 28 Tem | 3 gün | 6 |

Komşu terim çıpası: "context engineering" 2025 ortasında patladı, bugün ilgili repolar
13.7k–17.5k ★ seviyesinde. Terim dalgalarına erken girmenin getirisi yüksek.

### 2.1 Farklılaşma

`codejunkie99/graph-engineering` (222★, saf markdown) terimin **ders kitabını** yazmış ve
tanımını kurmuş: *knowledge graphs = ajanların hatırladığı, task graphs = ajanların çalıştığı.*
Dört kural koyuyor ama hiçbirini zorlamıyor:

| Onların kuralı (tavsiye) | Bizim karşılığımız (kod) |
|---|---|
| "Delete fake edges" | Katman 1 lint: tip uyumu + ölü düğüm |
| "Verify at every stage" | Katman 2: şema + köken + bayatlık |
| "Separate verifier contexts" | `reviewer_id ≠ producer_id` kontrolü |
| "The stop rule", "the human gate" | revizyon bütçesi + gate exit kodu |

**Onlar ders kitabı, biz derleyiciyiz.** README'de açık atıf verilecek; rakip değil
tamamlayıcı konum.

### 2.2 Arbor (RUC-NLPIR, 983★, arXiv 2606.11926)

Farklı problem: Arbor **daha iyi sonuç bulmak** için otonom optimizasyon ajanı (hipotez
ağacı, held-out validation, LiteLLM ile çok sağlayıcı). Biz **bulunan sonuca güvenilir mi**
sorusunu cevaplıyoruz. Arbor'ın Coordinator'ı kendi dallarını kendi vetliyor — bağımsız
denetim yok. Doğal konum: *"Arbor koşar, research-graph denetler."* README'de bir cümlelik
"see also"; adaptör yazılmayacak (YAGNI).

**Uyarı:** research-graph "araştırma ajanı hattı" gibi konumlanırsa Arbor'la aynı sahaya
girer ve ezilir. Doğrulama/denetim ekseninde kalmak zorunlu.

### 2.3 Aletheia ile ilişki

`huguryildiz/Aletheia` tek-ajan araştırma disiplini (markdown-only, bilinçli olarak script
yok). research-graph çok-ajanlı rol ayrımı ve çalıştırılabilir doğrulama. Karar: **bağımsız
repo**, atıf zorlanmayacak. (Sonradan bir satırlık "see also" eklenebilir.)

---

## 3. Alınan kararlar

| Konu | Karar |
|---|---|
| Hedef | Çalıştırılabilir starter kit (spesifikasyon veya salt görsel değil) |
| Repo | Bağımsız, Aletheia'dan ayrı |
| Taşıyıcı | Harness-nötr: markdown prompt'lar + Python verifier |
| Graph ekseni | İkisi birden — KG, süreç grafının bir alt düğümü |
| Kapsam | Tam hat, tek seferde (18 artifact, 6 rol, 9 gate, örnek koşu) |
| İsim | `research-graph` (repo) / `rgraph` (CLI) |
| Rol derinliği | 6 rol, tam yazılmış |
| Kurulum | Otomatik tespit + sayfadan tek satırlık `--preset` komutu |
| Web yapılandırıcı | Evet — diyagram `assignment.yaml` üretir |
| Dağıtım | Vercel (statik) |

`research-graph` GitHub'da org/repo olarak, PyPI'da paket olarak boş — kontrol edildi.
Maliyeti: "graph engineering" arama trafiğini doğrudan yakalamıyor. Telafi: GitHub
topics'e `graph-engineering` eklenecek, README ilk paragrafta terim geçecek.

---

## 4. Mimari

Üç dosya, üç ayrı sorumluluk. **Ayrım kitin belkemiği:**

```
graph.yaml       →  mimari      (hangi node, hangi kenar, hangi gate)
assignment.yaml  →  cüzdan      (hangi rolü kim koşuyor)
providers.yaml   →  kayıt       (hangi sağlayıcı var, ne yapabiliyor)
```

Aynı graf herkesin kendi abonelik kombinasyonuyla koşar. Yeni sağlayıcı eklemek
`providers.yaml`'a birkaç satır; **kod değişmez**, çünkü `rgraph` hiçbir sağlayıcıyı
tanımaz — yalnızca kimlik dizesi taşır.

### 4.1 graph.yaml

```yaml
nodes:
  - {id: retrieval, kind: agent, role: roles/retrieval.md,
     produces: [corpus_snapshot, kg_snapshot, evidence_matrix]}
  - {id: E1, kind: gate, gate: challenge, reviewer: independent}

edges:
  - {from: retrieval, to: E1, kind: handoff, carries: evidence_matrix}
  - {from: E1, to: retrieval, kind: return, carries: evidence_gap, budget: 3}
```

`kind` dört değer: `agent · store · gate · human`. Kenar üç: `handoff · return · read_only`.
Genelleştirme burada kesiliyor — daha fazlası "her şeye uyan hiçbir şey" olur.

### 4.2 assignment.yaml

```yaml
retrieval:    {provider: claude-code, model: sonnet-5}
planning:     {provider: claude-code, model: opus-5}
execution:    {provider: claude-code, model: sonnet-5}
verification: {provider: codex,       model: gpt-5.6}
synthesis:    {provider: claude-code, model: fable-5}
reviewer:     {provider: grok,        model: grok-5}
```

### 4.3 providers.yaml

```yaml
claude-code: {kind: cli, invoke: claude, identity: "claude-code/{model}",
              capabilities: [filesystem, shell, read_files]}
codex:       {kind: cli, invoke: codex,  identity: "codex/{model}",
              capabilities: [filesystem, shell, read_files]}
grok:        {kind: web, url: grok.com,  identity: "grok/{model}",
              capabilities: [manual]}
gemini:      {kind: cli, invoke: gemini, identity: "gemini/{model}",
              capabilities: [filesystem, shell, read_files]}
ollama:      {kind: cli, invoke: "ollama run", identity: "ollama/{model}",
              capabilities: [filesystem, shell, read_files]}
```

---

## 5. Verifier — iki katman

Kitin dayandığı tek iddia, diyagramın kendi cümlesi:

> *"Passing a gate requires registered, versioned artifacts rather than a textual
> assertion alone."*

Verifier tam olarak bunu yapar. **Bilimsel doğruluğu yargılamaz** — diyagramın claim
boundary'si bunu zaten dışlıyor, README'de aynen tekrarlanacak.

### Katman 1 — statik (koşu olmadan, sadece `graph.yaml`)

| Kontrol | Ne yakalar |
|---|---|
| Tip uyumu — kenarın taşıdığı artifact kaynak node'un ürettiklerinde mi | Var olmayan çıktıyı bekleyen aşama |
| Asiklik — `handoff` kenarları DAG mı; döngü yalnızca `return`'de | Gizli sonsuz döngü |
| Sınırlılık — her `return` kenarının bütçesi var mı | Sonsuz düzeltme sarmalı |
| Erişilebilirlik — gate'in istediği artifact'e yol var mı | Asla geçilemeyecek gate |
| Ölü düğüm — üretip kimseye vermeyen node | Dekoratif kutu ("fake edge") |

### Katman 2 — dinamik (bir `run/` dizini üzerinde)

| Kontrol | Ne yakalar |
|---|---|
| Varlık | Yarım bırakılmış aşama |
| Şema (JSON Schema) | Uydurma/eksik alan |
| Köken — `produced_by`, `inputs[]` (upstream hash), `content_hash` | Kaynağı bilinmeyen sonuç |
| **Bayatlık** — upstream değiştiyse downstream gate geçersizleşir | Protokol donduktan sonra sessizce değişen veri |
| **Hakem bağımsızlığı** — challenge gate'lerde `reviewer_id ≠ producer_id` | Kendi işini kendi onaylayan ajan |
| Revizyon bütçesi | Sonsuz döngü |

Bayatlık ve hakem bağımsızlığı kitin asıl satış noktası: ikisi de prompt'la önlenemez,
ikisi de dosya hash'iyle yakalanır.

### 5.1 Bağımsızlık seviyeleri

`gates.yaml` her gate'in hangi seviyeyi istediğini söyler:

**"Independent" kelimesi kullanılmayacak** — sahte güven yaratıyor. Yerine doğrulanabilir
üç seviye:

| Seviye | Kural | Ne zaman sağlanır |
|---|---|---|
| `CONTEXT ONLY` | ayrı oturum, aynı model ve sağlayıcı | tek abonelikle |
| `SEPARATE MODEL` | aynı sağlayıcı, farklı model | tek abonelik, çok modelli |
| `SEPARATE PROVIDER` | farklı sağlayıcı | iki abonelik |

`CONTEXT ONLY` her zaman şu uyarıyla basılır:

```
Review separation
  Level : CONTEXT ONLY
  Note  : Reviewer uses a separate session, but the same model
          and provider. Correlated errors may remain.
```

`rgraph` hangisinin sağlandığını **gizlemez**, `release_manifest`'e yazar.

### 5.2 Dürüstlük sınırı (README'de açıkça yazılacak)

`reviewer_id ≠ producer_id` kontrolü kriptografik değil, **disiplin mekanizmasıdır**.
Kararlı bir kullanıcı yalan yazabilir — o zaman yalnızca kendini kandırmış olur.
Aletheia'nın "discipline as instructions, not enforcement" dürüstlüğüyle aynı çizgi.

---

## 6. Roller ve yetenek eşleştirmesi

Altı rol, tam yazılmış. Her rol dosyası **çalıştırılabilir bir sözleşme**: ürettiği
artifact'ler, şema referansları, zorunlu alanlar, kabul kriteri, revizyon bütçesi.
Tek gövde üç kullanım: düz md olarak yapıştır · Claude subagent olarak koş · Codex skill
olarak koş.

**Roller eşit değil** — frontmatter'daki `requires` alanı `providers.yaml`'daki
`capabilities` ile eşleştirilir:

| Rol | Gereken yetenek | Web-only sağlayıcı (ör. Grok) |
|---|---|---|
| Retrieval | filesystem | ⚠ manuel |
| Planning | filesystem | ⚠ manuel |
| **Execution** | **filesystem + shell** | **✗ atanamaz** |
| Verification | filesystem + shell | ✗ atanamaz |
| Synthesis | filesystem | ⚠ manuel |
| **Reviewer** | read_files | **✓ ideal** |

`rgraph setup` ve web yapılandırıcı uyumsuz atamayı engeller ve sebebini yazar.

---

## 7. KG'nin süreç grafına bağlanması

`kg_snapshot` artifact'i E1 gate'inde makineyle denetlenir:

| Alan | E1 fidelity audit'in yaptığı |
|---|---|
| `entities[]`, `claims[]` | şema doğrulaması |
| `edges[].source_id` | her iddia kenarı gerçekten var olan bir kaynağa bağlı mı |
| `edges[].locator` | sayfa/bölüm çıpası var mı — "bu makalede geçiyor" reddedilir |
| `sources[].doi` + `retracted` | DOI çözülüyor mu, geri çekilmiş mi |
| `contradictions[]` | çelişen iddialar işaretli mi, yoksa sessizce mi seçilmiş |

Uydurma atıfın **giriş noktasında** yakalanması; `codejunkie99`'un "delete fake edges"
kuralının KG tarafındaki karşılığı, bu kez kod olarak.

---

## 8. Sağlayıcı katmanları

Orkestrasyon değişir, **doğrulama sabit kalır** — `rgraph` dosya sistemine bakar,
artifact'i kimin ürettiği onu ilgilendirmez.

| | Ne gerekiyor | Bağımsızlık | Kime |
|---|---|---|---|
| **0 · Manuel** | hiçbir şey — web arayüzü, kopyala-yapıştır | ayrı sohbet | herkes |
| **1 · Tek CLI** | Claude Code **ya da** Codex | ayrı subagent/oturum | tek abonelik |
| **2 · İki CLI** | Claude Code **+** Codex | **ayrı sağlayıcı** | iki abonelik, API yok |
| **3 · API** | API anahtarları (LiteLLM) | ayrı sağlayıcı, tam otomasyon | ileri kullanıcı |

### 8.1 Abonelik ≠ API (README'de netleştirilecek)

| | Ne veriyor | Ne vermiyor |
|---|---|---|
| Claude Pro/Max | claude.ai + Claude Code CLI | Anthropic API kredisi |
| ChatGPT Plus/Pro | chatgpt.com + Codex CLI | OpenAI API kredisi |
| API anahtarı | programatik çağrı | — (ayrı ödeme) |

**Katman 2 kitin en özgün konfigürasyonu:** iki abonelik dışında maliyet yok, gerçek
çapraz-sağlayıcı denetim. Doğrulanmış çağrı biçimi (2026-07-31, yerel makine):

```bash
codex exec -c model="gpt-5.6" - < roles/reviewer.md     # codex-cli 0.144.6
claude -p --model opus-5 < roles/planning.md            # Claude Code 2.1.220
```

`codex exec` prompt'u stdin'den okur, `-c model=` ile model seçilir. Giriş bir kez:
`codex login` (tarayıcı → ChatGPT hesabı), `codex login status` ile doğrulanır.

**Sınır (README'de yazılacak):** abonelik CLI'larında oran limitleri var ve orkestrasyon
otomatik değil — kullanıcı adımlar arasında geçiş yapar. Tam otomasyon Katman 3'te.

Katman 3 için kendi çok-sağlayıcı katmanımızı yazmayacağız; **LiteLLM'e delege edilecek**
(Arbor'ın çözümü, yüzlerce sağlayıcı bedavaya gelir).

---

## 9. CLI yüzeyi

**Tüm CLI çıktısı İngilizce.** (Bu spec Türkçe; repo, README, rol dosyaları ve tüm
terminal metni İngilizce olacak.)

### 9.0 Tasarım ilkeleri

CLI **dekoratif değil, yaşayan araştırma hattını** gösterir. Kullanıcı her an beş şeyi
görmeli: **mevcut aşama · sorumlu araç · üretilen artifact · gate sonucu · sonraki eylem.**

- Durum sözlüğü: `PASS · FAIL · WAIT · READY · STALE · BLOCKED · CAVEAT`
- Renk kullanılabilir, **ama anlam yalnızca renge bağlanmaz** (erişilebilirlik + log/CI)
- Model düşünce akışı, token metrikleri ve uzun loglar ana ekrana **basılmaz** →
  `--verbose` veya log dosyası
- Gate çıktısı yalnızca sonucu değil, **neyi kanıtlamadığını** da yazar

**Banner yerleşimi:**

| Komut | Banner |
|---|---|
| `rgraph` (argümansız), `rgraph setup` | ✓ blok logo + motif |
| `status · next · check · revise · trace · review` | ✗ doğrudan bilgi |

Motif işlevsel: düğüm → gate dizisi, altında sınırlı geri dönüş kenarı — tek satırda
kitin tezi. Karşılama ve ekran-görüntüsü değeri korunur, günlük `next`/`check` döngüsünde
yolda durmaz.

**Banner — tam çıktı** (5 satır yükseklik, 48 sütun genişlik, 80'lik terminalde sığar):

```
  ████  █████ █████ █████ █████ ████  █████ █   █
  █  █  █     █     █     █   █ █  █  █     █   █
  ████  ████  █████ ████  █████ ████  █     █████
  █ █   █         █ █     █   █ █ █   █     █   █
  █  █  █████ █████ █████ █   █ █  █  █████ █   █

  █████ ████  █████ █████ █   █
  █     █  █  █   █ █   █ █   █
  █  ██ ████  █████ █████ █████
  █   █ █ █   █   █ █     █   █
  █████ █  █  █   █ █     █   █

  ○──▶○──▶◆──▶○──▶◆        contract-gated agentic research
  │            │           v0.1.0 · graph engineering, verified
  └────────────┘
```

Blok font `█` (U+2588) ile çizilir; gereken harfler: `R E S A C H G P`. Motifte
`○` düğüm, `◆` gate, alttaki kapalı kenar sınırlı geri dönüş döngüsü.

Kompakt varyant (dar terminal / `--no-banner` alternatifi) `RGRAPH`, 36 sütun:

```
  ████  █████ ████  █████ █████ █   █
  █  █  █     █  █  █   █ █   █ █   █
  ████  █  ██ ████  █████ █████ █████
  █ █   █   █ █ █   █   █ █     █   █
  █  █  █████ █  █  █   █ █     █   █
```

**Bağımlılık:** `jsonschema` + `rich` (renk, tablo, okunabilir hata çıktısı).

### 9.0.1 Komut seti

| Komut | Ne zaman |
|---|---|
| `rgraph demo` | bir kez, merak — üç senaryo |
| `rgraph setup` | bir kez, kurulumda — tespit + atama |
| `rgraph status` | "neredeyim" — özet hat (`--verbose` 12 birimi açar) |
| `rgraph next` | sıradaki iş — envanter + onaylı çalıştırma |
| `rgraph check <GATE>` | gate doğrulama + statik lint |
| `rgraph revise <GATE>` | FAIL sonrası dönüş |
| `rgraph trace <claim>` | iddiadan ham veriye zincir |
| `rgraph review` | insan yayın kararı |

### 9.0.2 `rgraph status` — özet hat

Web diyagramının tamamı terminale sıkıştırılmaz. Challenge gate'ler ve insan gate'leri
birim hattıyla **hizalı ayrı satırlarda** gösterilir (12 birimin detayı `--verbose`):

```
RESEARCH RUN  rg-20260731-001
Question      Is method X better than method Y?
Mode          GUIDED
Protocol      FROZEN
Revision      2 of 3 attempts remain

PIPELINE
  RETRIEVE ---> PLAN ---> EXECUTE ---> VERIFY ---> WRITE
    PASS        PASS       READY        WAIT       WAIT
  gate:E1     gate:T1     gate:T2      gate:V1    gate:M1
    PASS        PASS       ----         ----       ----
  human:H1    human:H4
  APPROVED    APPROVED

Progress      4 / 12 units complete
Artifacts     6 valid, 0 stale, 2 pending
Last gate     H1 PASS
Next unit     05 Experiment execution
```

### 9.0.3 `rgraph next` — onaylı çalıştırma

Orkestratör komutu **kullanıcıya kopyalatmaz, doğrudan çalıştırır** — ama önce ne
yapacağını tam olarak gösterir ve onay ister:

```
UNIT 05 / EXPERIMENT EXECUTION
------------------------------

Provider       codex / gpt-5.6
Inputs
  run/frozen_protocol.yaml       VALID
  run/code_commit.json           VALID
Will produce
  run/raw_results.jsonl
  run/run_manifest.json
Required gate
  V1 Reproducibility check
Estimated use
  20 runs, seeds 41-60

No command has been executed.

[E] Execute   [D] Dry run   [S] Stop
```

Web-only sağlayıcı atanmışsa (`kind: web`) aynı ekran manuel adımları basar: yeni oturum
aç → rol dosyasını yapıştır → çıktıyı şu yola kaydet → `rgraph check`.

### 9.0.4 Gate FAIL çıktısı

Yalnızca FAIL değil: **neden · nasıl düzeltilir · nereye dönülür · gate'in neyi
kanıtlamadığı.**

```
GATE E1 / SOURCE SUPPORT                     FAIL
-------------------------------------------------

2 of 14 claims need revision.

  c-04  SOURCE NOT RESOLVED
        DOI: 10.1234/fake.2024
        Fix: replace or remove source s-02

  c-09  SUPPORT LOCATOR MISSING
        Source exists, but no page, section, table, or passage
        supports this claim.
        Fix: add a direct locator or narrow the claim

What this gate checked
  [PASS] Source identity
  [FAIL] Direct-support locator
  [----] Scientific correctness was not determined

Return to       Unit 02 / Evidence mapping
Revision budget 2 -> 1

Run next:
  rgraph revise E1
```

`[----] Scientific correctness was not determined` satırı **her gate çıktısında** durur —
claim boundary'yi tek seferlik bir README cümlesi olmaktan çıkarıp her ekrana taşır.

### 9.0.5 STALE zinciri

Bayatlama kitin en özgün yakalaması; ayrı ve açık basılır:

```
STALE CHAIN DETECTED
  run/data_manifest.json changed after H4 protocol freeze
  Invalidated: V1, T2, M1  (must re-run before they can pass)
```

### 9.0.6 `rgraph trace <claim>`

```
CLAIM c-03
"Method X improved the target metric by 12 percent."

+-- manuscript.md
|   `-- Results, paragraph 2
+-- claim_evidence_map.json
|   `-- c-03 -> result-r17
+-- statistical_report.json
|   +-- estimate : 12.0 percent
|   +-- 95% CI   : [8.1, 15.9]
|   `-- n        : 20
+-- raw_results.jsonl
|   `-- run_20260731_017
+-- run_manifest.json                 HASH VALID
+-- frozen_protocol.yaml              FROZEN
`-- reviewer_report.json              CONTEXT-ONLY PASS

Assurance
  Provenance chain is complete.
  Scientific validity still requires human review.
```

### 9.0.7 Tamamlanma ekranı

```
RUN COMPLETE WITH CAVEATS
-------------------------

Units         12 / 12 complete
Gates         8 PASS, 1 PASS WITH CAVEATS
Artifacts     18 valid, 0 stale
Review        CONTEXT ONLY
Human release NOT APPROVED

The manuscript is ready for human review.
It has not been approved for publication.

Next:
  rgraph review
```

### 9.1 Kurulum akışı

```
$ rgraph setup

Bulundu:  codex ✓ (giriş yapılmış)   claude ✗ (kurulu değil)

Önerilen atama — tek sağlayıcın var:
  üretici roller → codex/gpt-5.6
  hakem          → codex/gpt-5.6 (ayrı oturum)
  Bağımsızlık: distinct_context

Kabul ediyor musun? [E/h]
```

İki CLI bulunursa bağımsızlığı en yükseğe çıkaran atamayı önerir (üreticiler Claude,
hakem Codex → `distinct_provider`). Sayfadan gelen özel kurgu için:

```bash
rgraph setup --preset "producers=claude-code,reviewer=grok"
```

YAML yapıştırma akışı yok.

---

## 10. Web yapılandırıcı (Vercel)

`architecture.html` zaten kendi kendine yeten tek dosya, dış bağımlılığı yok. Kök
`index.html` olarak servis edilir; üstüne ince bir şerit (repo linki, `git clone` satırı,
"30 saniyede dene").

Diyagram **ikna aracı** olarak yapılandırıcıyı taşır: node'a tıkla → yan panelde "bu rolü
kim koşsun?" → uyumsuz seçenekler soluk → altta canlı `assignment.yaml` + tek satırlık
`--preset` komutu → *Kopyala*.

Asıl işlevi kurulum değil, kurulumdan **önceki** soruyu cevaplamak: *"bende sadece ChatGPT
var, ne elde ederim?"* Terk noktası orası.

Üretilen YAML'ın başına, seçime göre kurulum komutları yorum olarak eklenir:

```yaml
# Kurulum:
#   codex login        ← ChatGPT aboneliğini bağlar
#   claude             ← Claude aboneliğini bağlar (ilk açılışta)
reviewer: {provider: codex, model: gpt-5.6}
```

---

## 11. Repo yapısı ve paketleme

```
research-graph/
├── README.md              # ilk ekran: "graph engineering kurallarını doğrulayan araç"
├── architecture.html      # v5.1 diyagram, olduğu gibi
├── graph.yaml             # akademik referans graf
├── assignment.example.yaml
├── providers.yaml
├── gates.yaml             # 9 gate: gereken artifact'ler, bağımsızlık seviyesi, bütçe
├── roles/                 # 6 rol: retrieval · planning · execution ·
│                          #   verification · synthesis · reviewer
├── schemas/               # 18 artifact + kg_snapshot JSON Schema
├── rgraph/                # Python CLI, tek bağımlılık: jsonschema
├── example-run/           # doldurulmuş uçtan uca koşu  [konu AÇIK — bkz. §14]
├── template-run/          # boş iskelet
├── .claude-plugin/        # plugin.json → "skills": ["./roles"]
├── .agents/plugins/marketplace.json
└── plugins/research-graph/.codex-plugin/plugin.json
```

Paketleme deseni Aletheia'dan alınıyor: **tek gövde, iki manifest**, içerik kopyalanmaz.

```bash
claude plugin marketplace add huguryildiz/research-graph
codex  plugin marketplace add huguryildiz/research-graph
```

---

## 12. Bilinçli olarak yapılmayanlar

- **Runtime/orkestratör yok** — `deer-workflow` ve Arbor o alanda; biz doğrulama katmanıyız
- **Model API çağrısı yok** (Katman 0–2'de) — kit hiçbir modele bağlanmaz, prompt verir ve çıktıyı denetler
- **Kendi çok-sağlayıcı katmanımız yok** — Katman 3'te LiteLLM'e delege
- **Web UI, veritabanı, sunucu yok** — CLI + dosya sistemi
- **Bilimsel doğruluk yargısı yok** — claim boundary README'de tekrarlanır
- **Arbor adaptörü yok** — sadece bir cümlelik "see also"

---

## 13. Bitti sayılma kriteri

1. `rgraph check` referans graf üzerinde statik katmanı temiz geçer
2. `rgraph next` + `rgraph check` example-run üzerinde 9 gate'i de yeşil gösterir
3. Bozulmuş DOI → E1 kırmızı, `exit 1`
4. Protokol donduktan sonra değişen veri → bayatlık zinciri downstream gate'leri geçersizler
5. `rgraph trace` manuscript'ten ham veriye kesintisiz zincir basar
6. Temiz makinede `git clone` → 5 dakikada 1–5 tekrarlanır
7. Vercel'de sayfa açılır, yapılandırıcı geçerli `assignment.yaml` üretir

---

## 14. AÇIK maddeler

**A. `example-run/` konusu — KARAR: hot topic, wireless × ML.**

Seçilen soru: **"Does a learned channel estimator actually beat LMMSE at low SNR?"**

Gerekçe — alanın bilinen zayıflığı kitin yakaladığı şeyle örtüşüyor: bu literatürde tek
koşu bildirme, dar SNR aralığı ve zayıf baseline seçimi yaygın. V1'in ham sonuçtan
yeniden hesaplaması ve `statistical_report`'un güven aralığı zorunluluğu gerçek bir şey
yakalar. Pratik: birkaç yüz satır Python, saniyeler içinde koşar, gerçek DOI'li literatür
bol.

Uygulama notu: `example-run/` içindeki **tüm DOI'ler gerçek ve çözülebilir olmalı** —
`rgraph demo` senaryo ②'de bilerek enjekte edilen sahte DOI hariç. Aksi halde kitin kendi
E1 gate'i kendi örneğinde kalır.

**B. ~~Otomatik mod v0.1'de olsun mu?~~ KAPANDI (2026-07-31).**
Evet, v0.1'de. Ama "otomatik" değil **onaylı**: `rgraph next` envanteri gösterir
(`No command has been executed.`), kullanıcı `[E] Execute` ile onaylar, orkestratör
doğrudan çalıştırır. Komut kopyalatma akışı kaldırıldı. Bkz. §9.0.3.

---

## 15. Notlar

- Bu doküman `Desktop/Graph-CLAUDE` altında yazıldı; burası git reposu değil, commit
  yapılmadı. Repo kurulunca `docs/` altına taşınacak.
- Yayın penceresi dar: terim 2 haftalık ve haftada birkaç yeni repo çıkıyor.
