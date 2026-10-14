#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

site = Path("/etc/nginx/sites-available/default")
domain = "app-papm.duckdns.org"

if not site.is_file():
    sys.exit(f"Arquivo Nginx não encontrado: {site}")

original = site.read_text()


def mask_comments(source):
    """Substitui comentários por espaços, preservando posições e quebras de linha."""
    result = list(source)
    quote = None
    escaped = False
    comment = False

    for i, char in enumerate(source):
        if comment:
            if char == "\n":
                comment = False
            else:
                result[i] = " "
            continue

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
        elif char == "#":
            comment = True
            result[i] = " "

    return "".join(result)


def end_brace(source, opening):
    depth = 0
    quote = None
    escaped = False

    for i in range(opening, len(source)):
        char = source[i]

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i + 1

    return None


clean = mask_comments(original)
servers = []

for match in re.finditer(r"(?m)^[ \t]*server\s*\{", clean):
    opening = clean.find("{", match.start(), match.end())
    end = end_brace(clean, opening)

    if end is None:
        sys.exit("Bloco server incompleto no Nginx. Nenhuma alteração feita.")

    block = clean[match.start():end]

    has_domain = re.search(
        r"(?m)^[ \t]*server_name\s+[^;]*\b"
        + re.escape(domain)
        + r"\b[^;]*;",
        block,
    )
    has_https = re.search(
        r"(?m)^[ \t]*listen\s+[^;]*\b443\b[^;]*;",
        block,
    )

    if has_domain and has_https:
        servers.append((match.start(), end))

if len(servers) != 1:
    sys.exit(
        f"Esperava um bloco HTTPS único para {domain}; "
        f"encontrados {len(servers)}. Nenhuma alteração feita."
    )

start, end = servers[0]
block_clean = clean[start:end]
locations = []

for match in re.finditer(
    r"(?m)^[ \t]*location\s+/\s*\{", block_clean
):
    opening = block_clean.find("{", match.start(), match.end())
    close = end_brace(block_clean, opening)

    if close is None:
        sys.exit("Bloco location incompleto. Nenhuma alteração feita.")

    locations.append((match.start(), close))

if len(locations) != 1:
    sys.exit(
        f"Esperava um location / único no bloco HTTPS; "
        f"encontrados {len(locations)}. Nenhuma alteração feita."
    )

a, b = locations[0]
proxy = """location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }"""

new_block = original[start:end]
new_block = new_block[:a] + proxy + new_block[b:]
new_text = original[:start] + new_block + original[end:]

if new_text != original:
    backup = site.with_name(
        site.name + ".backup-imc-" + datetime.now().strftime("%Y%m%d%H%M%S")
    )
    shutil.copy2(site, backup)

    fd, temporary = tempfile.mkstemp(
        prefix=".default.imc-", dir=str(site.parent)
    )

    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(new_text)

        shutil.copystat(site, temporary)
        os.replace(temporary, site)

        test = subprocess.run(
            ["nginx", "-t"], text=True, capture_output=True
        )

        if test.returncode:
            shutil.copy2(backup, site)
            print(test.stdout, file=sys.stderr)
            print(test.stderr, file=sys.stderr)
            sys.exit(
                "nginx -t falhou; configuração original restaurada."
            )

        subprocess.run(
            ["systemctl", "reload", "nginx"], check=True
        )
        print(f"Proxy Nginx configurado. Backup: {backup}")

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
else:
    print("Proxy Nginx já estava configurado; nenhuma alteração necessária.")

subprocess.run(
    [
        "curl", "--silent", "--show-error", "--fail",
        "--max-time", "10",
        "--resolve", f"{domain}:443:127.0.0.1",
        f"https://{domain}/login",
        "-o", "/dev/null",
    ],
    check=True,
)
print(f"Verificação HTTPS concluída para https://{domain}/login")
