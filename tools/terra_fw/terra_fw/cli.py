import argparse
import json
import sys

from . import container, firmware, presets


def main(argv=None):
    ap = argparse.ArgumentParser(prog="terra-fw")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info", help="verify and describe a .smf/.smp file")
    s.add_argument("file")
    s = sub.add_parser("unpack", help="write payload (.smf -> app.bin, .smp -> JSON)")
    s.add_argument("file"); s.add_argument("out")
    s = sub.add_parser("pack", help="build .smf from app.bin or .smp from JSON")
    s.add_argument("src"); s.add_argument("out")
    s.add_argument("--like", required=True, help="original file to copy the header field from")
    s = sub.add_parser("patch", help="apply mod(s) to a stock .smf")
    s.add_argument("smf"); s.add_argument("out", help="output .smf, or with --auto-name a directory"); s.add_argument("mods", nargs="+")
    s.add_argument("--auto-name", action="store_true",
                   help="write OUT/TERRA_V<fw>_<mod>[+<mod>]/TERRA_V<fw>_<mod>[+<mod>].smf (one firmware per USB-stick folder)")
    s = sub.add_parser("padtest", help="stock .smf + 64 bytes of 0xFF (tests that a longer image is accepted)")
    s.add_argument("smf"); s.add_argument("out")
    a = ap.parse_args(argv)

    if a.cmd == "info":
        data = open(a.file, "rb").read()
        c = container.parse(data)
        print(f"OK  crc={c.crc:#010x}  payload={len(c.payload)} bytes  field04={c.field04.hex()}")
        if a.file.endswith(".smf"):
            i = firmware.info(c)
            print(f"    sp={i.initial_sp:#x} reset={i.reset_vector:#x} "
                  f"vectors={i.vector_min:#x}..{i.vector_max:#x}")
        else:
            b = presets.decode(c)
            print(f"    presets used: {sum(s is not None for s in b.slots)}/{presets.SLOTS}")
    elif a.cmd == "patch":
        from . import patcher
        import os
        mods = [patcher.load_mod(m) for m in a.mods]
        out, placed = patcher.apply(open(a.smf, "rb").read(), mods)
        if a.auto_name:
            name = f"TERRA_V{mods[0]['mod']['fw_version']}_" + "+".join(m["mod"]["id"] for m in mods)
            os.makedirs(os.path.join(a.out, name), exist_ok=True)
            a.out = os.path.join(a.out, name, name + ".smf")
        open(a.out, "wb").write(out)
        for p in placed:
            print(f"hook {p.at:#010x} -> trampoline {p.tramp:#010x} ({p.size} bytes)")
        print(f"wrote {a.out} ({len(out)} bytes)")
    elif a.cmd == "padtest":
        from . import patcher
        open(a.out, "wb").write(patcher.pad_test(open(a.smf, "rb").read()))
    elif a.cmd == "unpack":
        c = container.parse(open(a.file, "rb").read())
        if a.file.endswith(".smf"):
            open(a.out, "wb").write(c.payload)
        else:
            json.dump(presets.to_json(presets.decode(c)), open(a.out, "w"), indent=1)
    elif a.cmd == "pack":
        like = container.parse(open(a.like, "rb").read())
        if a.out.endswith(".smf"):
            out = container.Container(like.field04, open(a.src, "rb").read())
        else:
            out = presets.encode(presets.from_json(json.load(open(a.src))), like.field04)
        open(a.out, "wb").write(out.to_bytes())


if __name__ == "__main__":
    sys.exit(main())
