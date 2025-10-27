# 🔋 Batteri ROI Kalkylator - Svenska Marknaden

En avancerad webbapplikation för att beräkna avkastningen på batteriinvesteringar för svenska solcellsinstallationer, med stöd för Tibber-data och stödtjänster.

## ✨ Funktioner

### Nuvarande funktioner (v1.0):
- ✅ **Tibber CSV-import**: Ladda upp dina faktiska elförbruknings- och prisdata
- ✅ **Realistiska simuleringar**: Optimerar batteriladdning/-urladdning baserat på verklig data
- ✅ **Svenska marknadsförutsättningar**: 
  - Effekttariff-optimering
  - Nätavgifter och energiskatt
  - Exportersättning vid överskott
  - 25% moms
- ✅ **Solcellsintegration**: Uppskatta produktion baserat på installerad effekt
- ✅ **Stödtjänster**: Beräkna extra intäkter från FCR-N, FCR-D, aFRR
- ✅ **ROI-analys**: Återbetalningstid, NPV, livstidsvinst
- ✅ **Fördefinierade konfigurationer**: Populära batterisystem (Tesla Powerwall, Huawei Luna, etc.)
- ✅ **Detaljerade rapporter**: Månadsvis uppdelning och visualiseringar

## 🚀 Snabbstart

### Installation

```bash
# Installera Python-beroenden
pip install -r requirements.txt

# Starta backend-servern
python app.py
```

Backend körs nu på `http://localhost:5000`

### Använd applikationen

1. **Öppna webbgränssnittet**: Öppna `index.html` i din webbläsare
2. **Ladda upp Tibber-data**: Exportera din förbrukning från Tibber-appen
3. **Konfigurera ditt system**: Välj batteristorlek, nätbolag, och solcellskapacitet
4. **Se resultaten**: Få en komplett ROI-analys med återbetalningstid och besparingar

## 📊 Hur man får Tibber-data

1. Öppna Tibber-appen
2. Gå till "Användning"
3. Tryck på "Exportera data"
4. Välj tidsperiod (minst 12 månader rekommenderas)
5. Ladda ner CSV-filen
6. Ladda upp filen i denna app

## 🔧 API-dokumentation

### POST /api/upload
Ladda upp Tibber CSV-fil

**Request**: Multipart form-data med fil

**Response**:
```json
{
  "success": true,
  "filename": "tibber_data.csv",
  "rows": 8760,
  "columns": ["timestamp", "consumption_kwh", "spot_price_sek_kwh"]
}
```

### POST /api/simulate
Kör batterisimulering

**Request body**:
```json
{
  "filename": "tibber_data.csv",
  "battery_capacity_kwh": 10,
  "battery_power_kw": 5,
  "battery_cost_sek": 80000,
  "grid_fee_sek_kwh": 0.45,
  "energy_tax_sek_kwh": 0.40,
  "effect_tariff_sek_kw_month": 50,
  "solar_capacity_kwp": 10,
  "stodtjanster_revenue_sek_year": 0
}
```

**Response**: Se nedan för fullständig responsstruktur

### POST /api/stodtjanster/estimate
Uppskatta intäkter från stödtjänster

**Request body**:
```json
{
  "battery_power_kw": 5,
  "battery_capacity_kwh": 10,
  "service_type": "fcr_n"
}
```

### GET /api/battery/presets
Hämta fördefinierade batterikonfigurationer

### GET /api/network-operators
Hämta lista över svenska nätbolag med typiska avgifter

## 🧮 Simuleringslogik

### Batterioptimering
Simulatorn optimerar batterianvändningen genom att:

1. **Självförbrukning först**: Använd solenergi direkt när möjligt
2. **Batterilagring**: Ladda batterie med överskott från solceller
3. **Peak shaving**: Minska effekttoppar för att spara på effekttariffen
4. **Arbitrage**: Ladda när elpriset är lågt, ladda ur när det är högt (valbart)
5. **Export**: Exportera överskott när batteriet är fullt

### Kostnadsberäkning
```
Total kostnad = (Spotpris + Nätavgift + Energiskatt) × Förbrukning × (1 + Moms)
Export intäkt = Spotpris × 0.7 × Export × (1 + Moms)
Effekttariff = Högsta effekttoppar × Tariff × 12 månader
```

### ROI-beräkning
```
Årlig besparing = Kostnad utan batteri - Kostnad med batteri + Effektbesparingar + Stödtjänster
Återbetalningstid = Batterikostnad / Årlig besparing
NPV = -Batterikostnad + Σ(Årlig besparing / (1 + diskonteringsränta)^år)
ROI% = ((Total livstidsbesparing - Batterikostnad) / Batterikostnad) × 100
```

## 💰 Stödtjänster

### FCR-N (Frequency Containment Reserve - Normal)
- **Krav**: Minst 5 kW effekt
- **Genomsnittlig intäkt**: 2000-3000 SEK/MW/timme
- **Tillgänglighet**: ~70% (resten används för hemmet)

### FCR-D (Frequency Containment Reserve - Disturbance)
- **Krav**: Minst 5 kW effekt
- **Genomsnittlig intäkt**: 1500-2500 SEK/MW/timme
- **Tillgänglighet**: ~60%

### Aggregatorer i Sverige
- **Checkwatt**: checkwatt.se
- **Flower**: flower.se
- **Tibber**: Lanserar eget program

**Obs**: Aggregatorer tar typiskt 20-30% provision

## 📈 Framtida funktioner (v2.0)

### Hardware - Plug & Play Dongle
För att skapa en Sigen.ai-liknande lösning planerar vi:

#### Hårdvara
- **ESP32/Raspberry Pi-baserad enhet**
- **Modbus/RS485-interface** för batteriövervakning
- **WiFi/4G-uppkoppling**
- **Realtidsmätning** av laddning/urladdning

#### Mjukvara
- **Realtidsoptimering**: ML-baserad prediktion av solproduktion och förbrukning
- **Smart styrning**: Automatisk batteristyrning baserad på elpriser och prognos
- **MQTT/API-integration**: Anslut till Home Assistant, Tibber Pulse, etc.
- **Cloud-dashboard**: Se realtidsdata och historik

#### Funktioner
1. **Prediktiv styrning**: 
   - Väderprognos → Solproduktionsprognos
   - Spotprisprognos → Optimal laddningstid
   - Förbrukningsprognos → Batteriförberedelse

2. **Automatisk optimering**:
   - Ladda när elpriset är lågt
   - Ladda ur vid höga priser eller effekttoppar
   - Spara kapacitet för stödtjänster

3. **Integration med stödtjänster**:
   - Automatisk registrering för FCR-N/D
   - Hantera tillgänglighet och bud
   - Maximera intäkter

#### Utvecklingsplan
```
Fas 1 (Q1): Hårdvaruprototyp med grundläggande mätning
Fas 2 (Q2): Cloud-backend och API
Fas 3 (Q3): ML-optimering och prediktion
Fas 4 (Q4): Stödtjänstintegration och certifiering
```

#### Hårdvarukostnad (uppskattning)
- ESP32/Pi: 200-500 SEK
- Modbus-interface: 300-600 SEK
- Hölje och komponenter: 200-400 SEK
- **Total**: 700-1500 SEK/enhet

#### Affärsmodell
1. **Engångskostnad**: Sälja dongeln för ~2000-3000 SEK
2. **Prenumeration**: 99 SEK/månad för avancerade funktioner
3. **Provision**: 10-15% av stödtjänstintäkter

## 🏗️ Teknisk arkitektur

### Backend
- **Flask**: Lätt Python-webbramverk
- **Pandas/NumPy**: Databehandling och beräkningar
- **REST API**: JSON-baserad kommunikation

### Frontend
- **React**: Modern UI-ramverk
- **TailwindCSS**: Utility-first styling
- **Chart.js**: Visualiseringar

### Framtida (v2.0)
- **MQTT Broker**: Realtidskommunikation med dongeln
- **PostgreSQL/TimescaleDB**: Tidsseriedata
- **Redis**: Caching och köhantering
- **Docker**: Containerisering
- **AWS/Azure**: Cloud hosting

## 🛠️ Utveckling

### Projektstruktur
```
.
├── app.py                 # Flask backend API
├── battery_simulator.py   # Simuleringsmotor
├── index.html             # React frontend
├── requirements.txt       # Python-beroenden
└── README.md             # Denna fil
```

### Köra i utvecklingsläge
```bash
# Backend med hot-reload
python app.py

# Frontend - öppna bara index.html i webbläsaren
```

### Tester
```bash
# Enhetstest (lägg till senare)
pytest tests/

# API-test
curl http://localhost:5000/api/health
```

## 🤝 Bidra

Detta är en öppen källkodsprojekt! Bidrag är välkomna:

1. Forka repot
2. Skapa en feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit dina ändringar (`git commit -m 'Add some AmazingFeature'`)
4. Push till branchen (`git push origin feature/AmazingFeature`)
5. Öppna en Pull Request

## 📝 Licens

MIT License - du är fri att använda detta i kommersiella projekt!

## 💡 Tips för bästa resultat

1. **Använd verklig data**: Minst 12 månaders Tibber-data
2. **Korrekt konfiguration**: Kontrollera dina nätavgifter och effekttariff
3. **Realistiska solprognoser**: Justera produktion baserat på ditt tak
4. **Inkludera stödtjänster**: Kan göra stor skillnad i ROI
5. **Jämför alternativ**: Testa olika batteristorlekar

## 📞 Kontakt & Support

- **GitHub Issues**: För buggar och feature requests
- **Email**: [din email här]
- **Discord**: [kommunitylänk]

## 🎯 Roadmap

### Q1 2025
- [x] Grundläggande ROI-kalkylator
- [x] Tibber-integration
- [x] Stödtjänstuppskattningar
- [ ] Export av rapporter (PDF/Excel)
- [ ] Delning av resultat (unika länkar)

### Q2 2025
- [ ] Hårdvaruprototyp (dongle)
- [ ] Realtidsdashboard
- [ ] Home Assistant-integration
- [ ] Mobil app (iOS/Android)

### Q3 2025
- [ ] ML-baserad prediktion
- [ ] Automatisk batterioptimering
- [ ] API för tredjepartsutvecklare

### Q4 2025
- [ ] Stödtjänstaggregator-integration
- [ ] Peer-to-peer energihandel
- [ ] Företagsversion

---

**Gjord med ❤️ för den svenska solcellsmarknaden**
