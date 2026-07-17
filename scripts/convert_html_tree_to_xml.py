#!/usr/bin/env python3
"""Convert HTML tree to DocBook XML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Import the existing converter
sys.path.insert(0, str(Path(__file__).parent))
from convert_html_to_docbook import convert_file, infer_version_defaults


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert HTML tree to DocBook XML")
    parser.add_argument("html_dir", help="Source HTML directory")
    parser.add_argument("output_dir", help="Output XML directory")
    parser.add_argument("--skip-sample", action="store_true", help="Skip .generated.html files")
    args = parser.parse_args()
    
    html_dir = Path(args.html_dir)
    output_dir = Path(args.output_dir)

    if not html_dir.exists():
        print(f"Error: HTML directory not found: {html_dir}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Converting HTML from {html_dir} -> {output_dir}")

    # Process all HTML files
    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        print(f"No HTML files found in {html_dir}")
        return 1

    for html_file in html_files:
        # Skip generated files
        if html_file.name.endswith(".generated.html"):
            print(f"  Skipping {html_file.name} (generated artifact)")
            continue

        output_xml = output_dir / f"{html_file.stem}.xml"
        print(f"  Converting {html_file.name}...")

        # Infer version defaults from path
        version_id, status, framework_version, _implementation_date, _effective_date = infer_version_defaults(
            html_file,
            version_id=None,
            status=None,
            framework_version=None,
            implementation_date=None,
            effective_date=None,
        )

        try:
            convert_file(
                html_file,
                output_xml,
                base_uri="https://cccbr.org.uk/",
                version_id=version_id,
                status=status,
                framework_version=framework_version
            )
        except Exception as e:
            print(f"  ERROR: Failed to convert {html_file.name}: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print(f"\n[OK] Converted {len([f for f in html_files if not f.name.endswith('.generated.html')])} HTML files to XML")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
