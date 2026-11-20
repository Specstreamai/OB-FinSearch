# data

The public questions live on Hugging Face at `openbenchmarks/OB-FinSearch`, not in this folder. `finsearch run` downloads them. Pass `--data` to use a local folder or a single `.jsonl` file instead.

- `historical-lookup.jsonl` — Questions the agent answers with one search. Each line has `id`, `question`, `answer`, and `tolerance`.
- `multi-hop-lookup.jsonl` — Questions that need several searches. Same fields.
- `live-lookup.jsonl` — Stocks and coins asked about right after a market moment. Each line has `id`, `asset` (`equity` or `crypto`), `name`, `ticker`, and `query_template`.

Live lookup is graded against answer keys, passed with `--closes` and `--coin-key`:

- `live-closes.jsonl` — One line per date and stock: the official close and the close before it.
- `live-coins.jsonl` — One line per coin and minute: the lowest and highest traded price in that minute.
