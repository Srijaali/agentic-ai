# SaafHawa — AI4015 Assignment Beta Q1

Syeda Rija Ali | 23K-0057. 

`ROLL_DIGITS = "0057"`. Python derives R = 57 and D = (0+0+5+7) mod 10 = 2;  Main parameters: Q = 2,925, N = 6, p = 0.06, H = 5, B = $1,770/month and T = 10 seconds.

## Local Python workflow

```sh
source .venv/bin/activate
python tool_latency_logger.py status
python run_all.py
python verify_project.py
```

For a new computer, create a virtual environment with `python3 -m venv .venv`, activate it and install `requirements.txt`. No Colab or Jupyter is used. `run_all.py` runs the existing calculation script and the report/workbook builders in `work/`.

## Timing collection and status

```sh
python tool_latency_logger.py measure --samples 15
python tool_latency_logger.py status
```

Completion requires **at least 20 valid samples per tool in total across at least two Karachi calendar dates per tool**. Aim for 15 per tool per day; this is advice, not a stricter completion gate. The existing log already contains 45 samples/tool: 15 on 2026-11-14 and 30 on 2026-11-15. No third day is required. `status` reports counts by date, missing counts/dates and whether the machine field differs across runs.

The logger appends measurements; it never overwrites existing rows. Keep the OpenAQ key only in `.env` as `OPENAQ_API_KEY=...` or in the environment. Do not submit `.env` or `.venv`. Run only one logger at a time. API pacing occurs outside the timed section.

`timing_valid` means the response passed API/schema validation; `data_requirement_met` separately asks whether both PM2.5 and PM10 are recent (within three hours). For legacy CSVs the original schema and rows are preserved; new flags are saved in each run's `sample_validity.jsonl`. New CSVs also include both flags as columns. Existing legacy `valid` flags remain the timing baseline. `outputs/timing_audit.csv` reports historical coverage checks at collection time. Fourteen historical OpenAQ responses could not be matched to a saved body with the same timestamp; their coverage is **not verified**. A missing/stale PM10 reading must never be presented as live.

The headline delay is the pooled observation-weighted median, 0.062488645997 s in the current log. API-only sensitivity is 0.3110088749985 s. Half the observations are very fast local tools, so this pooled median is fragile and can lie far below typical API delay. Neither median is a median of four per-tool medians. Incomplete logs force downstream latency outputs to PENDING.

## Analysis and evidence

The original six-call loop has 25,080 expected input and 2,455 expected output tokens/query including retries. The report retains that main workload. A proposed deterministic tool workflow with one final LLM call is a separate architectural recalculation, not a replacement of the experiment pipeline.

Nano's latency estimate uses sourced non-reasoning aggregate TTFT at every growing input length. Input-length-specific TTFT is **not verified**. Haiku disabled-thinking TTFT/speed and RTX 4090 service time remain **not verified**, so the operational GPU count, candidate selection and Q* remain PENDING. The cost plot labels its W=10-second illustration explicitly. Qwen's A100 benchmark is not transferred to an RTX 4090.

The main cache scenario is one cold prefix write/query; the alternate assumes one shared-prefix write per fixed TTL window, continuous traffic and no eviction. Unknown eligibility gets no credited savings. Reasoning averages that are missing produce visible-token lower bounds rather than unsupported budget claims.

`data/models.json` and `data/sources.json` are the maintained evidence inputs. Every reported figure has a source ID resolving to a URL and ISO access date; the comparison CSV expands these per field. Artificial Analysis reports may use different providers/settings from the cost endpoint; mismatches are explicit. Unknown new-paid-account quotas, benchmark scores, cache terms and globally lowest price claims remain listed in `outputs/pending_items.txt`. Do not rerun `research_data.py`: it is the original seed-data generator and resets research inputs.

## Deliverables and review

- `outputs/report.docx`: parameters, model table, working, plot, limitations and assignment checklist.
- `outputs/calculations.xlsx`: one worksheet with editable inputs and live formulas.
- `outputs/model_comparison.csv`: per-field sources and dates.
- `outputs/results.json` and `outputs/answers.txt`: calculated results.
- `outputs/submission_checklist.md`: DONE / PENDING (needs me) / NOT VERIFIED against Section 1, Section 2 and Submission.
- `outputs/pending_items.txt` and `outputs/timing_audit.csv`: unresolved evidence and historical coverage audit.
- `tool_latency_raw.csv`, `raw_responses/` and `ai_declaration.txt`: original experiment evidence and declaration.

The report has a placeholder for your config screenshot. Embed it yourself, showing `num_hidden_layers`, `num_key_value_heads`, `hidden_size`, `num_attention_heads`, `intermediate_size`, `vocab_size`, `tie_word_embeddings`, `max_position_embeddings` and `use_sliding_window`. Also capture `data/model_config_values.json` showing derived head_dim = 3584/28 = 128 and source URL/access date. The original model config remains unchanged.

Review the report, checklist, unresolved evidence and declaration before submitting. Ask for student review before any commit or push; none is authorized automatically by this workflow.
