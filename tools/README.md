# tools

One `<tool>.yaml` file per search tool. Keeping each tool in its own file makes it easy to compare setups and open pull requests without merge conflicts.

Each file lists the tool's setups: the name, the options each setup sends, and its list price per search (`list_usd`) and per page fetch (`fetch_usd`). Some tools also set how fast live lookup may call them (`live_limit`).

To add or update a tool: edit `tools/<tool>.yaml` (and `harness/adapters/<tool>.py` if adding a new search API), run the tests, and open a pull request.
