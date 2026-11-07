"""Peak memory of ONE configuration in a fresh process (Windows only exposes a process-lifetime peak).

    uv run python -m hebloc.pilot.memprobe <model> <threads> <lex_topk 0|1>
"""

from __future__ import annotations

import json
import sys

from hebloc.parse import models as M
from hebloc.pilot import bench as Bn


def main() -> None:
    model, threads, topk = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1"
    name = f"mem_{model}_t{threads}{'_topk' if topk else ''}"
    lm = M.load(model, threads=threads)
    r = Bn.one(lm, Bn.bench_units(300), name, threads=threads, lex_topk=topk)
    print(json.dumps({"name": name, "peak_mem_gb_fresh_process": r["peak_mem_gb"], "ws_tokens_per_second": r["ws_tokens_per_second"]}))


if __name__ == "__main__":
    main()
