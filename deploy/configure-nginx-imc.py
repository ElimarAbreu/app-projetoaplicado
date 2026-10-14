#!/usr/bin/env python3
import os, re, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path
site=Path('/etc/nginx/sites-available/default'); domain='app-papm.duckdns.org'
if not site.is_file(): sys.exit(f'Arquivo Nginx não encontrado: {site}')
text=site.read_text()
def end_brace(src, opening):
    depth=0; quote=None; esc=False
    for i in range(opening,len(src)):
        c=src[i]
        if quote:
            if esc: esc=False
            elif c=='\\': esc=True
            elif c==quote: quote=None
            continue
        if c in ('\"', "'"): quote=c; continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return i+1
    return None
servers=[]
for m in re.finditer(r'(?m)^\s*server\s*\{',text):
    op=text.find('{',m.start()); end=end_brace(text,op)
    if end is None: continue
    block=text[m.start():end]
    if re.search(r'(?m)^\s*server_name\s+[^;]*\b'+re.escape(domain)+r'\b[^;]*;',block) and re.search(r'(?m)^\s*listen\s+[^;]*\b443\b[^;]*;',block): servers.append((m.start(),end,block))
if len(servers)!=1: sys.exit(f'Esperava um bloco HTTPS único para {domain}; encontrados {len(servers)}. Nenhuma alteração feita.')
start,end,block=servers[0]; locs=[]
for m in re.finditer(r'(?m)^\s*location\s+/\s*\{',block):
    close=end_brace(block,block.find('{',m.start()))
    if close is not None: locs.append((m.start(),close))
if len(locs)!=1: sys.exit(f'Esperava um location / único no bloco HTTPS; encontrados {len(locs)}. Nenhuma alteração feita.')
a,b=locs[0]
proxy="""location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }"""
newblock=block[:a]+proxy+block[b:]
newtext=text[:start]+newblock+text[end:]
if newtext != text:
    backup=site.with_name(site.name+'.backup-imc-'+datetime.now().strftime('%Y%m%d%H%M%S'))
    shutil.copy2(site,backup)
    tmp=site.with_suffix('.default.imc-tmp'); tmp.write_text(newtext); shutil.copystat(site,tmp); tmp.replace(site)
    test=subprocess.run(['nginx','-t'],text=True,capture_output=True)
    if test.returncode:
        shutil.copy2(backup,site)
        print(test.stdout+test.stderr,file=sys.stderr)
        sys.exit('nginx -t falhou; configuração original restaurada.')
    subprocess.run(['systemctl','reload','nginx'],check=True)
    print(f'Proxy configurado; backup: {backup}')
else: print('Proxy Nginx já estava configurado; nenhuma alteração necessária.')
# Confirma TLS local com SNI/Host correto; falha explícita para o pipeline.
subprocess.run(['curl','--silent','--show-error','--fail','--max-time','10','--resolve',f'{domain}:443:127.0.0.1',f'https://{domain}/login','-o','/dev/null'],check=True)
print(f'Verificação HTTPS local concluída para https://{domain}/login')
