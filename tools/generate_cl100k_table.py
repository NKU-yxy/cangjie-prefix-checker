#!/usr/bin/env python3
"""Generate the compact runtime token-id -> decoded UTF-8 table.

The competition process receives cl100k token IDs, while importing tiktoken in
every fresh process costs much more than the actual checking work.  build.sh
runs this generator once; the native entry reads the resulting ~1 MiB table.
"""

# Team-authored build tool. It uses the public tiktoken API to generate a local
# cl100k_base lookup table. tiktoken is distributed under the MIT License; no
# tiktoken implementation source is copied here. See THIRD_PARTY_NOTICES.md.

from __future__ import annotations

import argparse
from pathlib import Path
import struct

import tiktoken


MAGIC = b"CJTK\x01\x00\x00\x00"
MISSING = 0xFFFFFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    encoding = tiktoken.get_encoding("cl100k_base")
    offsets: list[int] = []
    lengths: list[int] = []
    blob = bytearray()
    for token_id in range(encoding.n_vocab):
        try:
            # Match the existing solution exactly.  In particular, tiktoken
            # decodes an isolated token with UTF-8 replacement semantics.
            decoded = encoding.decode([token_id]).encode("utf-8")
        except KeyError:
            offsets.append(MISSING)
            lengths.append(0)
            continue
        offsets.append(len(blob))
        lengths.append(len(decoded))
        blob.extend(decoded)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        stream.write(MAGIC)
        stream.write(struct.pack("<II", encoding.n_vocab, len(blob)))
        for offset, length in zip(offsets, lengths):
            stream.write(struct.pack("<II", offset, length))
        stream.write(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
