#!/usr/bin/env python3
"""Compile translation files (.po -> .mo)"""
import subprocess
from pathlib import Path

LOCALES_DIR = Path("app/locales")

def compile_translations():
    """Compile all .po files to .mo files."""
    for po_file in LOCALES_DIR.rglob("*.po"):
        mo_file = po_file.with_suffix(".mo")
        print(f"Compiling {po_file} -> {mo_file}")
        
        subprocess.run(
            ["msgfmt", str(po_file), "-o", str(mo_file)],
            check=True,
        )
    
    print("\n✅ All translations compiled successfully!")

if __name__ == "__main__":
    compile_translations()
