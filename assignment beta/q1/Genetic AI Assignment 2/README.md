# SaafHawa — Assignment Beta Q1

Syeda Rija Ali | 23K-0057. 

## Run the calculations

In the VS Code terminal:

```sh
source .venv/bin/activate
python calculations.py
```

Read `outputs/answers.txt` for the main numbers. `outputs/results.json` contains the full calculation results.

For a new computer, first run `python3 -m venv .venv`, activate it, then run `python -m pip install -r requirements.txt`.

## Collect your own measurements

Keep the OpenAQ key only in `.env` as `OPENAQ_API_KEY=...`, or in the environment. Never submit `.env` or `.venv`.

```sh
python tool_latency_logger.py measure --samples 15
python tool_latency_logger.py summary
```

Repeat on **two different Karachi calendar dates**. Each tool needs at least 15 successful samples on each date; two successful runs normally give 30 per tool. Run more samples if requests fail. Never edit dates or invent missing rows. Run only one logger at a time.

The logger appends to `tool_latency_raw.csv`, saves every response under `raw_responses/`, validates freshness and units, and excludes its 1.1-second pacing delay from timings. Only validated samples count. It reports both the pooled median and the API-only median because fast local tools can strongly affect the pooled value.

**PENDING** means either the two-day measurement requirement has not been met or a required model/GPU figure has not been verified. The report names the missing evidence. A missing or stale PM10 reading must not be shown as a live value.

## Deliverables

- `outputs/report.docx`: concise report, portrait throughout.
- `outputs/calculations.xlsx`: **one worksheet**, with editable inputs, live formulas, comparison evidence and the cost plot.
- `outputs/model_comparison.csv`: full table with per-field source URLs and access dates.
- `outputs/pending_items.txt`: evidence still needed before submission.
- `tool_latency_raw.csv` and `raw_responses/`: actual measurements and coverage evidence.
- `ai_declaration.txt`: AI tools used and their purposes.

The initial coverage check found no live station providing both PM2.5 and PM10 within 25 km. See `data/coverage_latest.json`; run `python tool_latency_logger.py discover` to check again.

## Rebuild documents if needed

```sh
python run_all.py
```

`run_all.py` runs the calculations and, if present, the optional exporters in `work/`. Those helpers generate the Word and Excel files; they are not the experiment itself and are not required to submit the analysis code. The workbook is recalculated when opened in Excel or LibreOffice; Python answers do not need either application.

Model evidence is in `data/models.json` and `data/sources.json`. Do not rerun `research_data.py` after editing these files: it resets the initial research inputs. Incomplete model figures remain unverified. The break-even curve is explicitly a 10-second service-time sensitivity, not a measured deployment result.

## Configuration screenshot

Capture `data/config.json` showing `num_hidden_layers`, `num_key_value_heads`, `hidden_size`, `num_attention_heads`, `intermediate_size`, `vocab_size`, `tie_word_embeddings` and `max_position_embeddings`. Also capture `data/model_config_values.json`: derived `head_dim = 3584 / 28 = 128`, download URL and access date.

