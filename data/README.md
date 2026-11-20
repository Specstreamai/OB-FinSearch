# data

No question files are committed to this folder.

## Public vs. held-out evaluation sets

- **Public split:** Hosted on Hugging Face at [`openbenchmarks/OB-FinSearch`](https://huggingface.co/datasets/openbenchmarks/OB-FinSearch). `finsearch run` downloads it automatically; pass `--data <path>` to use a local folder or single `.jsonl` file instead.
- **Held-out split (private):** Evaluation sets used for published boards stay private so tools cannot train on them.

## Files and schema

| File | Description | Fields |
|---|---|---|
| `historical-lookup.jsonl` | Single-search factual finance questions. | `id`, `question`, `answer`, `tolerance` |
| `multi-hop-lookup.jsonl` | Multi-search financial synthesis questions. | `id`, `question`, `answer`, `tolerance` |
| `live-lookup.jsonl` | Stocks and crypto assets queried right after a market moment. | `id`, `asset` (`equity` or `crypto`), `name`, `ticker`, `query_template` |

Live lookup runs are graded against answer keys passed via `--closes` and `--coin-key`:

- `live-closes.jsonl` — One line per date and stock: official close and prior close.
- `live-coins.jsonl` — One line per coin and minute: lowest and highest traded price in that minute.
