"""Generate a local, policy-filtered listing without changing the manifest."""

import argparse
from pathlib import Path

from trace_them.manifest import load_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=".work/site-list")
    args = parser.parse_args()
    manifest = load_manifest(include_nsfw=True)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["# Trace Them supported public-profile targets", "",
             "Static definitions; live reliability is not guaranteed.", ""]
    for name, info in sorted(manifest.sites.items(), key=lambda item: item[0].casefold()):
        suffix = " (NSFW)" if info.get("isNSFW") else ""
        lines.append(f"- [{name}]({info['urlMain']}){suffix}")
    lines.extend(["", "## Policy exclusions", ""])
    lines.extend(f"- {name}: {reason}" for name, reason in sorted(manifest.skipped.items()))
    (directory / "sites.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {len(manifest.sites)} eligible targets in {directory}")


if __name__ == "__main__":
    main()
