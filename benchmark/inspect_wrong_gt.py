"""Inspect official GT tokens for key wrong/ cases."""
import json
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
d = json.load(open("/ref/wrong_error_positions.json"))

names = [
    "err_arraylist_add_type",
    "err_string_contains_arg",
    "err_arity",
    "err_ctor_call_mismatch",
    "err_unknown_named_arg",
    "err_hashmap_key_type",
    "err_no_member",
]
for item in d["wrong_examples"]:
    if item["name"] in names:
        src = open(f"/ref/wrong/{item['name']}.cj").read()
        ids = enc.encode(src)
        i = item["first_error_token_index"]
        starts = []
        pos = 0
        for t in ids:
            starts.append(pos)
            pos += len(enc.decode_single_token_bytes(t))
        end = starts[i + 1] if i + 1 < len(starts) else len(src)
        print("==", item["name"], "GT=", i)
        for k in range(max(0, i - 2), min(len(ids), i + 3)):
            kend = starts[k + 1] if k + 1 < len(starts) else len(src)
            print(f"   {k}: {src[starts[k]:kend]!r}")
        print("   ctx:", repr(src[max(0, starts[i] - 30): end + 10]))
