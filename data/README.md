# data

No question files are committed to this folder.

## Public vs. held-out evaluation sets

- **Public split:** Hosted on Hugging Face at [`openbenchmarks/OB-FinSearch`](https://huggingface.co/datasets/openbenchmarks/OB-FinSearch). `finsearch run` downloads it automatically; pass `--data <path>` to use a local folder or single `.jsonl` file instead.
- **Held-out split (private):** Evaluation sets used for published boards stay private so tools cannot train on them.

## Files and schema

| File | Description | Fields |
|---|---|---|
| `historical-lookup.jsonl` | A figure from one company or series: a filing, often read with its earnings call. 2 searches. | `id`, `question`, `answer`, `tolerance` |
| `multi-hop-lookup.jsonl` | Figures pulled from several companies, quarters or releases into a ranking, trend or comparison. 6 searches. | `id`, `question`, `answer`, `tolerance` |
| `live-lookup.jsonl` | Stocks and crypto assets queried right after a market moment. | `id`, `asset` (`equity` or `crypto`), `name`, `ticker`, `query_template` |
| `live-filings.jsonl` | Questions about company filings published the same day. | `id`, `question`, `answer`, `tolerance`, `filed_at` (ISO 8601 with time zone) |

A single `.jsonl` file passed with `--data` sets each row's task with `lookup` (`historical` or `multi_hop`). An `answer` may end with `Also accept: ...` (other correct answers) and `Wrong: ...` (likely wrong answers); the judge reads both.

Live lookup runs are graded against answer keys passed via `--closes` and `--coin-key`:

- `live-closes.jsonl` — One line per date and stock: official close and prior close.
- `live-coins.jsonl` — One line per coin and minute: lowest and highest traded price in that minute.
