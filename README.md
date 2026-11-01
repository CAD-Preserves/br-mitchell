# br-mitchell

> [!WARNING]
> We cannot always guarantee JSON keys are well-formatted, only that the data is complete. You will likely have to extract and clean these `.json` source files yourself for the target domain you wish to study.

Data structuring repository for BR Mitchell's _International Historical Statistics_. This means we take source PDF files/scans of BR Mitchell from our private collections and restructure it into usable JSON for dataset work, particularly in testing and validation.

JSON outputs are in `/outputs/`. To digitise from your own PDFs, see `/common/digitiser/volumes_config.json5` to point to your own filepaths, then run `autorun.bat`/`autorun.sh`. For IP reasons, we do not include our scans of BR Mitchell.

<details open>
  <summary><b>Table of Contents.</b></summary>

### Section A: Population and Vital Statistics

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **A1** | Population of Countries at Enumerations | Population of Countries | Population of Countries at Censuses |
| **A2** | Population of Selected Countries by Sex and Age Groups | Population of Major Countries by Sex and Age Groups | Population of Countries by Sex and Age Groups |
| **A3** | Population of Major Administrative Divisions in Selected Countries | Population of Major Administrative Divisions | Population of Major Districts |
| **A4** | Population of Major Cities | Population of Major Cities | Population of Major Cities |
| **A5** | Population Estimates | Mid-Year Population Estimates | Mid-year Population Estimates |
| **A6** | Vital Statistics | Vital Statistics | Vital Statistics |
| **A6a** | — | Collver's Estimates of Average Vital Rates for Quinquennia 1895–1959 | — |
| **A7** | Deaths of Infants Under One Year Old per 1,000 Live Births | Infant Mortality Rates | Deaths of Infants Under One Year Old per 1,000 Live Births |
| **A8** | International Migrants | International Migrations | Emigration from Europe by Decades |
| **A9** | — | — | Annual Migration Statistics |

---

### Section B: Labour Force

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **B1** | Economically Active Population by Major Activity Groups | Economically Active Population by Major Industrial Groups | Economically Active Population by Major Industrial Groups |
| **B2** | Unemployment | Unemployment | Unemployment |
| **B3** | Industrial Disputes | Industrial Disputes | Industrial Disputes |
| **B4** | Indices of Wages or Earnings | Money Wages in Industry | Money Wages in Industry |
| **B5** | — | Wages in Agriculture | Money Wages in Agriculture |

---

### Section C: Agriculture

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **C1** | Area of Main Arable Food Crops | Area of Main Arable Crops | Area of Main Cereal, Potato, and Sugar Beet Crops |
| **C2** | Output of Main Arable Food Crops | Output of Main Arable Crops | Output of Main Cereal, Potato, and Sugar Beet Crops |
| **C3** | Sugar Output | Output of Sugar | Area of Vineyards and Output of Wine |
| **C4** | Output of Main Oil Crops | Area of Flax, Groundnuts and Soya Beans | Area and Output of Mediterranean Crops |
| **C5** | Output of Cocoa, Coffee and Tea | Output of Major Oil Crops | Numbers of Livestock |
| **C6** | Output of Citrus Fruits, Apples and Bananas | Area and Output of Cotton and Tobacco | Output of Cows' Milk |
| **C7** | Output of Wine | Output of Cocoa, Coffee and Tea | Butter Output |
| **C8** | Output of Cotton | Output of Fruit | Meat Output |
| **C9** | Output of Tobacco | Area of Vineyards and Output of Wine | Landings of Fish |
| **C10** | Output of Rubber | Numbers of Livestock | External Trade in Corn |
| **C11** | Numbers of Livestock | Output of Cow's Milk | Exports of Agricultural, Fishing and Forestry Products |
| **C12** | Output of Meat | Output of Butter | — |
| **C13** | Output of Milk | Output of Meat | — |
| **C14** | Output of Butter | Landings of Fish | — |
| **C15** | Output of Wool | Exports of Wheat by Main Trading Countries | — |
| **C16** | Landings of Fish | Exports of Sugar by Main Trading Countries | — |
| **C17** | Exports of Various Agricultural Commodities by Major Exporting Countries | Exports of Principal Livestock Products by Main Trading Countries | — |
| **C18** | — | Exports of Various Agricultural Commodities by Main Trading Countries | — |
| **C19** | — | Exports of Timber Products by Main Trading Countries | — |

---

### Section D: Industry

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **D1** | Indices of Industrial Production | Indices of Industrial Production | Indices of Industrial Production |
| **D2** | Output of Coal | Output of Coal | Output of Coal |
| **D3** | Output of Crude Petroleum | Output of Crude Petroleum | Output of Crude Petroleum |
| **D4** | Output of Natural Gas | Output of Natural Gas | Output of Natural Gas |
| **D5** | Output of Iron Ore | Output of Iron Ore | Output of Main Non-ferrous Metal Ores |
| **D6** | Output of Main Non-ferrous Metal Ores | Output of Main Non-ferrous Metal Ores | Output of Main Non-metallic Minerals |
| **D7** | Output of Gold and Silver | Output of Main Non-metallic Minerals | Output of Iron Ore |
| **D8** | Output of Raw Asbestos, Phosphate Rock, Potash and Sulphur | Output of Pig Iron | Output of Pig Iron |
| **D9** | Output of Pig Iron | Output of Crude Steel | Output of Crude Steel |
| **D10** | Output of Steel Ingots and Castings | Output of Aluminium | Output of Aluminium |
| **D11** | Output of Aluminium | Output of Refined Copper, Lead, Tin, and Zinc | Imports and Exports of Coal by Main Surplus and Deficient Countries |
| **D12** | Output of Refined Copper, Lead, Tin and Zinc | Raw Cotton Consumption | Imports and Exports of Petroleum by Main Surplus and Deficient Countries |
| **D13** | Cotton Spindles | Cotton Spindles | Imports and Exports of Iron Ore by Main Trading Countries |
| **D14** | Raw Cotton Consumption | Output of Cotton Yarn | Raw Cotton Consumption Indicators |
| **D15** | Output of Cotton Yarn | Output of Cotton Tissues | Cotton Spindles |
| **D16** | Output of Woven Cotton Fabrics | Wool Industry Indicators | Output of Cotton Yarn |
| **D17** | Output of Wool Goods | Output of Artificial and Synthetic Fibres | Output of Cotton Tissues |
| **D18** | Output of Synthetic Filaments | Output of Sulphuric, Hydrochloric, Nitric Acid, and Caustic Soda | Raw Wool Consumption Indicators |
| **D19** | Output of Sulphuric, Hydrochloric, Nitric Acid and Caustic Soda | Timber Industry Indicators | Output of Wool Yarn |
| **D20** | Output of Wood | Output and Assembly of Motor Vehicles | Output of Wool Tissues |
| **D21** | Output of Wood Pulp | Output of Beer | Output of Artificial and Synthetic Fibres |
| **D22** | Assembly of Motor Vehicles | Output of Electric Energy | Linen Industry Indicators |
| **D23** | Output of Beer | Imports and Exports of Coal by Main Trading Countries | Output of Sulphuric Acid |
| **D24** | Output of Electric Energy | Imports and Exports of Petroleum by Main Trading Countries | Timber Industry Indicators |
| **D25** | Imports and Exports of Coal by Main Trading Countries | Imports and Exports of Iron Ore by Main Trading Countries | Output of Motor Vehicles |
| **D26** | Imports and Exports of Petroleum by Main Trading Countries | — | Output of Beer |
| **D27** | Imports and Exports of Iron Ore by Main Trading Countries | — | Output of Electric Energy |

---

### Section E: External Trade

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **E1** | External Trade: Aggregate Current Values | External Trade Aggregates in Current Values | External Trade Aggregate Current Value |
| **E2** | External Trade with Main Trading Partners | External Trade (in Current Values) with Main Trading Partners | External Trade (by value) with Main Trading Partners |
| **E3** | Major Commodity Exports by Main Exporting Countries | Major Commodity Exports by Main Exporting Countries | — |

---

### Section F: Transport and Communications

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **F1** | Length of Railway Line Open | Length of Railway Line Open | Length of Railway Line Open |
| **F2** | Freight Traffic on Railways | Freight Traffic on Railways | Freight Traffic on Railways |
| **F3** | Passenger Traffic on Railways | Passenger Traffic on Railways | Passenger Traffic on Railways |
| **F4** | Merchant Ships Registered | Merchant Ships Registered | Merchant Ships Registered |
| **F5** | Motor Vehicles in Use | North American Inland Waterway Traffic | Inland Navigation Traffic |
| **F6** | Civil Aviation Traffic | Motor Vehicles in Use | Motor Vehicles in Use |
| **F7** | Postal and Telegraph Traffic | Civil Aviation Traffic | Commercial Aviation |
| **F8** | Telephones in Use | Postal and Telegraph Traffic | Postal and Telegraph Services |
| **F9** | Radio and Television Sets in Use | Number of Telephones in Use | Telephone Services |
| **F10** | — | Radio and Television Sets in Use | Radio and Television Receiving Licences |

---

### Section G: Finance

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **G1** | Currency or Banknotes in Circulation | Currency in Circulation | Banknote Circulation |
| **G2** | Demand Deposits in Commercial Banks | Deposits in Commercial Banks | Deposits in Commercial Banks |
| **G3** | Savings Bank Deposits | Savings Bank Deposits | Deposits in Savings Banks |
| **G4** | Money Supply | Money Supply | Money Supply |
| **G5** | Total Central Government Expenditure | Total Central Government Expenditure | Total Central Government Expenditure |
| **G6** | Central Government Revenue with Some Main Tax Yields | Central Government Revenue with Some Main Tax Yields | Central Government Revenue and Main Tax Yields |

---

### Section H: Prices

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **H1** | Wholesale Price Indices | Wholesale Price Indices | Wholesale Price Indices |
| **H2** | Consumer Price Indices | Consumer Price Indices | Cost-of-living / Consumer Prices Indices |

---

### Section I: Education

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **I1** | Number of Children in Schools | Pupils and Teachers in Schools | Children and Teachers in Schools |
| **I2** | Students in Higher Education | Students in Universities | Number of Students in Universities |

---

### Section J: National Accounts

| ID | Africa, Asia & Oceania | The Americas | Europe |
| :--- | :--- | :--- | :--- |
| **J1** | National Accounts Totals | National Accounts Totals | National Accounts Totals |
| **J2** | Proportions of GDP by Sector of Origin | Proportions of GDP by Sector of Origin | Proportions of National Product by Sector of Origin |
| **J3** | Balance of Payments | Balance of Payments | Balance of Payments |
  
</details>

<details>
  <summary><b>Technical Notes.</b></summary>

## Directory Structure

- `common/areal_masks/` — JSON5 geospatial configurations and country, administrative-division and city mask rules (`areal_mask_config.json5`, `country_rules.json5`, `admin_division_rules.json5`, `city_rules.json5`).
- `common/digitiser/` — JSON5 pipeline and volume configurations (`pipeline_config.json5`, `volumes_config.json5`).
- `core/` — Modular Python CV + CUDA EasyOCR pipeline (`PagePreprocessor`, `GraphicalElementDetector`, `TokenSegmenter`, `GpuOcrEngine`, `BraceAndCellResolver`, `HeaderHierarchyResolver`, `TableStructureReconstructor`, `PlaceKeyNormaliser`, `TableSeriesFlattener`, `SectionAssembler`, `TableDigitiserPipeline` and `cli_runner.py`).
- `docs/` — Doxygen configuration (`Doxyfile`), pipeline architecture, JSON schema (`architecture_and_schema.md`) and generated API reference (`api_reference.md`).
- `localisation/` — CLI localisation strings in EN-GB, FR and DE (`en_gb.json5`, `fr.json5`, `de.json5`).
- `output/areal_masks/` — `4320x2160` WGS84 Equirectangular lossless RGB `.png` areal mask (`provinces.png`) plus flat JSON registries (`country_masks.json`, `subadmin_masks.json`, `city_masks.json` and `table_masks.json`) covering 100% of corpus locations.
- `output/json/` — Digitised per-section JSON files namespaced by volume (`africa_asia_oceania/`, `americas/`, `europe/`) plus `manifest.json`.

## Usage

### Digitise All 3 Volumes
```powershell
.\autorun.bat
```

### Digitise a Specific Volume, Page Slice or Custom PDF
```powershell
# Single configured volume
python core/cli_runner.py --volume europe

# Specific 0-based PDF page slice (e.g. pages 30 to 52)
python core/cli_runner.py --volume africa_asia_oceania --start-page 30 --end-page 52 --no-manifest

# Reuse on any external scanned statistical PDF
python core/cli_runner.py --pdf path/to/custom_tables.pdf --volume custom_id
```

### Generate 4320x2160 WGS84 Areal Masks
```powershell
python core/areal_mask_runner.py
```

### Verify Environment & Build Documentation
```powershell
.\autobuild.bat
.\autodoc.bat
```

See `docs/architecture_and_schema.md` for full details on the CV pipeline stages and output JSON schema.

</details>


