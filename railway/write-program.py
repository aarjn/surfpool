#!/usr/bin/env python3
"""Deploy a program to surfpool via the surfnet_writeProgram cheatcode.

Installs the program in a handful of RPC calls instead of the ~100
transactions of `solana program deploy`, which makes it immune to the
request-timeout flakiness hosted instances can hit under transaction
floods. Creates/overwrites the program + programdata accounts directly.

Usage:
  python3 write-program.py <program.so> <program-id> <rpc-url> [authority]

  <program-id> and [authority] accept either a base58 pubkey or a path to
  a keypair JSON file (e.g. target/deploy/myprog-keypair.json).

Example:
  python3 write-program.py target/deploy/onlydevs.so \
      target/deploy/onlydevs-keypair.json \
      "https://<domain>/?api-key=<key>" \
      ~/.config/solana/admin.json

Stdlib only — no dependencies.
"""

import json
import os
import sys
import urllib.request

CHUNK = 800_000  # bytes per surfnet_writeProgram call (hex doubles it; RPC cap is 5MB)

B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58_ALPHABET[r] + out
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return B58_ALPHABET[0] * pad + out


def resolve_pubkey(arg: str) -> str:
    """Accept a base58 pubkey or a keypair JSON path; return the pubkey."""
    if os.path.exists(arg):
        with open(arg) as f:
            key = json.load(f)
        if not (isinstance(key, list) and len(key) == 64):
            sys.exit(f"error: {arg} is not a 64-byte keypair JSON file")
        return b58encode(bytes(key[32:]))
    return arg


def rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    if "error" in resp:
        sys.exit(f"error: {method} failed: {resp['error']}")
    return resp["result"]


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    so_path, program_arg, url = sys.argv[1], sys.argv[2], sys.argv[3]
    program_id = resolve_pubkey(program_arg)
    authority = resolve_pubkey(sys.argv[4]) if len(sys.argv) == 5 else None

    data = open(so_path, "rb").read()
    print(f"program id: {program_id}")
    print(f"authority:  {authority or '(default: system program)'}")
    print(f"binary:     {len(data)} bytes, {(len(data) + CHUNK - 1) // CHUNK} chunk(s)")

    for offset in range(0, len(data), CHUNK):
        chunk = data[offset : offset + CHUNK]
        rpc(url, "surfnet_writeProgram", [program_id, chunk.hex(), offset, authority])
        print(f"  wrote bytes {offset}..{offset + len(chunk)}")

    info = rpc(url, "getAccountInfo", [program_id, {"encoding": "base64"}])["value"]
    if info and info.get("executable"):
        print(f"done — {program_id} is live (owner {info['owner']})")
    else:
        sys.exit("error: program account not executable after write")


if __name__ == "__main__":
    main()
