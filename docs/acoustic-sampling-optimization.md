# Teorema del Campionamento Acustico Spettrale e Ottimizzazione del Finder

Questo documento formalizza i principi fisici, matematici ed algoritmici utilizzati nel motore di simulazione e nel sistema di ricerca altoparlanti (*Bass Match / Finder*) di **Load Forge**.

L'obiettivo è garantire il trade-off ottimale di Pareto: **massima velocità di esecuzione** e **precisione sub-hertziana/sub-dB**, definendo una regola analoga al teorema di Nyquist-Shannon per il dominio della frequenza logaritmica.

---

## 1. Fondamenti: Natura Analitica delle Funzioni di Trasferimento Acustiche

Nei sistemi a parametri concentrati e distribuiti (cassa chiusa, bass reflex, DCCAV, bandpass del 4° e 6° ordine, passive radiator, linee di trasmissione, trombe), la risposta in frequenza è descritta nel dominio di Laplace $s = \sigma + j\omega$ da una funzione di trasferimento razionale:

$$H(s) = \frac{N(s)}{D(s)}$$

- **Poli complessi coniugati:** $s = -\alpha \pm j\omega_d$, con frequenza di risonanza $\omega_0 = \sqrt{\alpha^2 + \omega_d^2}$ e fattore di merito $Q = \frac{\omega_0}{2\alpha}$.
- **Pendenze asintotiche:** Su scala logaritmica $[\ln f, \text{SPL}_{\text{dB}}]$, la risposta decade o cresce secondo pendenze asintotiche rette pari a $n \times 6\text{ dB/ottava}$ ($n \times 20\text{ dB/decade}$), dove $n$ è l'ordine del filtro (es. $n=2$ per sospensione pneumatica, $n=4$ per bass reflex, $n=6$ per DCCAV).
- **Group delay e fase:** Il ritardo di gruppo $\tau_g = -\frac{d\phi}{d\omega}$ presenta i propri picchi esattamente in corrispondenza della banda di transizione dei risonatori ad alto $Q$.

---

## 2. Teorema del Campionamento Acustico Spettrale (Analogia di Nyquist-Shannon)

Nel dominio del tempo, il teorema di Shannon dimostra che un segnale a banda limitata $B$ richiede $f_s \ge 2B$ campioni al secondo per una ricostruzione esatta senza aliasing.

Nel dominio della frequenza logaritmica $\ln \omega$, la "banda spettrale" (massima derivata della risposta in ampiezza e fase) è vincolata dal polo a più alto fattore di merito $Q_{\max}$.

### Enunciato del Teorema:
Sia $Q_{\max}$ il massimo fattore di qualità presente nei circuiti risonanti del carico acustico. Il passo di campionamento logaritmico $\Delta(\ln f)$ necessario e sufficiente per catturare ogni picco di risonanza, sella di accordo o ripple senza aliasing spettrale soddisfa:

$$\Delta(\ln f) \le \frac{1}{2 \, Q_{\max}}$$

### Corollario in Punti per Ottava e Punti per Decade:
- **Punti minimi per ottava:**
  $$N_{\text{oct}} = \frac{\ln(2)}{\Delta(\ln f)} \ge 2 \ln(2) \cdot Q_{\max} \approx 1.39 \, Q_{\max}$$
- **Punti minimi per decade:**
  $$N_{\text{dec}} = \frac{\ln(10)}{\Delta(\ln f)} \ge 2 \ln(10) \cdot Q_{\max} \approx 4.61 \, Q_{\max}$$

### Applicazione Pratica:
Nei carichi reali reflex, DCCAV e bandpass con tipiche perdite di assorbimento e condotto ($Q_b \approx 5 \dots 10$), il fattore $Q_{\max}$ raramente supera $5$.
- Sono sufficienti **$\approx 23$ punti per decade** ($7$ punti per ottava).
- Su una banda d'interesse estesa a 1.5 decadi ($10\text{ Hz} \dots 300\text{ Hz}$), una griglia globale di **$30$ punti logaritmici** soddisfa pienamente il criterio di Shannon-Nyquist spettrale.

---

## 3. Teorema di Ricostruzione Logaritmica (Precisione Sub-Hertziana)

La determinazione dei punti caratteristici di taglio ($F_3, F_6, F_{10}$) non richiede un campionamento ad altissima densità:
- L'interpolazione lineare in frequenza genera un errore sistematico convesso a causa della curvatura logaritmica naturale del roll-off.
- L'interpolazione lungo la retta naturale in coordinate $[\ln f, \text{SPL}_{\text{dB}}]$ ricostruisce il punto esatto di transizione:

$$f_{\text{crossing}} = \exp\left( \ln f_0 + \frac{\text{SPL}_{\text{target}} - \text{SPL}_0}{\text{SPL}_1 - \text{SPL}_0} \cdot \ln\left(\frac{f_1}{f_0}\right) \right)$$

Questo approccio garantisce una precisione analitica **$< 0.05\text{ Hz}$** anche su griglie rade (30 punti), eliminando la distorsione del "ginocchio" di filtro.

---

## 4. Principio di Decomposizione Ottimale a Due Stadi

La valutazione di un catalogo di $M$ driver con $K$ iterazioni dell'ottimizzatore per ciascuno comporta una complessità temporale di:

$$C = \mathcal{O}(M \cdot K \cdot N_{\text{grid}})$$

Per minimizzare il costo computazionale globale a parità di risoluzione, la simulazione viene decomposta in due stadi ortogonali:

```
[ Catalogo Driver (M candidati) ]
               │
               ▼
┌────────────────────────────────────────────────────────┐
│ STADIO 1: Coarse Global Screening (N_coarse = 30 pt)   │
│ - Griglia logaritmica full-band (10 - 300 Hz)          │
│ - Calcolo rapido di ripple, escursione e SPL nominale  │
│ - Pattern search / compass optimization                │
└────────────────────────────────────────────────────────┘
               │
      [ 1 Vincitore per Topologia ]
               │
               ▼
┌────────────────────────────────────────────────────────┐
│ STADIO 2: Narrow-band Refinement (N_refine = 20 pt)    │
│ - Zoom logaritmico ristretto attorno al ginocchio      │
│   stimato [0.7 F3, 1.4 F3]                             │
│ - Estrazione metrica F3 / F6 / F10 ad alta risoluzione │
└────────────────────────────────────────────────────────┘
```

---

## 5. Regola Aurea per l'Efficienza del Finder di Load Forge

$$\boxed{\text{Budget di Calcolo per Driver} = \underbrace{30 \text{ pt}}_{\text{Full-band Coarse}} + \mathbb{I}_{\text{vincitore}} \cdot \underbrace{20 \text{ pt}}_{\text{Zoom su } [0.7 F_3, 1.4 F_3]}}$$

1. **Campionamento Vincolato a $Q_{\max}$:** 30 punti distribuiti geometricamente su $10\text{ Hz} \dots 300\text{ Hz}$ soddisfano $\Delta(\ln f) \le 1 / (2 Q_{\max})$.
2. **Interpolazione Log-Lineare:** Ricerca delle soglie $F_3, F_6, F_{10}$ nello spazio $(\ln f, \text{dB})$ lungo la pendenza naturale del polo.
3. **Inizializzazione Ottima dei Volumi (Seeding):** Per ricerche orientate alla massima estensione con tetto volumetrico, i volumi di partenza sono inizializzati direttamente al $95\text{--}98\%$ del limite massimo ($V_{\text{init}} = 0.95 \cdot V_{\max}$), evitando iterazioni sprecate nella scalata del volume e concentrando il budget computazionale sull'accordo risonante.
4. **Multiprocessing Bounded:** Esecuzione parallela a zero-overhead con pool di processi pre-allocato e digest compatti T/S.
