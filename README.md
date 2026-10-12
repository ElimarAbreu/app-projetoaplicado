# SecureOps Lab — Calculadora de IMC

Aplicação web acadêmica para demonstrar práticas de **Secure by Design**. Possui tela de login, página interna protegida no servidor, logout funcional e calculadora de Índice de Massa Corporal (IMC). Armazena contas em um arquivo JSON protegido (nome, e-mail e hash de senha), sem banco de dados; os valores usados na calculadora não são persistidos.

## Tecnologias

- Python e Flask para autenticação, autorização e validação no servidor.
- HTML semântico, CSS responsivo e JavaScript para a interface.
- Gunicorn como servidor WSGI em produção.
- Nginx com HTTPS na VM OCI.
- pytest para testes automatizados.
- Arquivo JSON com gravação atômica e bloqueio de acesso durante alterações, sem servidor de banco de dados.
- GitHub Actions para testes e entrega contínua.

## Funcionalidades

- Cadastro de conta com nome, e-mail e senha e login nativo da aplicação; após o cadastro, o usuário é direcionado à tela de login e precisa autenticar-se explicitamente.
- Senhas armazenadas com hash adaptativo por `werkzeug.security`, nunca em texto puro; e-mail único e normalizado.
- `/dashboard` e `/calculate` protegidos por autorização no servidor.
- Logout via POST e proteção CSRF nos formulários.
- Cálculo `IMC = peso (kg) / altura (m)²`.
- Validação de tipo e faixa de peso/altura no servidor.
- Limitação de tentativas de login e cadastro a cinco por minuto por IP.
- Sessão com expiração de 30 minutos, cookie `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- Cabeçalhos HTTP de segurança, política CSP e `Cache-Control: no-store`.
- Testes de acesso não autenticado, login, logout, cálculo e cabeçalhos.

## Executar localmente no Windows

Requisitos: Python 3.11 ou superior e Git.

1. Abra o PowerShell na pasta do repositório.
2. Crie e ative o ambiente virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Instale as dependências:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copie o exemplo de variáveis de ambiente:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Gere uma chave secreta para a sessão:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

6. Edite `.env` e configure `SECRET_KEY` com a chave gerada. Mantenha `APP_ENV=development` e confirme que `USERS_FILE=instance/users.json` aponta para um local gravável. O diretório `instance/` está no `.gitignore` e não deve ser enviado ao GitHub.
7. Inicie a aplicação:

   ```powershell
   python app.py
   ```

8. Acesse `http://localhost:5000`, selecione **Criar uma conta**, preencha nome, e-mail e senha e envie o formulário. Depois, saia da sessão e teste o login com o e-mail e a senha cadastrados.

O cadastro exige senha entre 12 e 128 caracteres, com pelo menos uma letra maiúscula, uma letra minúscula, um número e um símbolo. Após cadastrar, a aplicação retorna à tela de login sem criar uma sessão autenticada. O arquivo JSON é criado automaticamente no caminho indicado por `USERS_FILE`; as senhas são armazenadas como hashes e o arquivo recebe permissões restritas em sistemas POSIX. O modo local usa HTTP e, por isso, não ativa o atributo `Secure` do cookie. Não publique o servidor de desenvolvimento. Em produção, use Gunicorn atrás de Nginx com HTTPS.

## Testes automatizados

Com o ambiente virtual ativado:

```powershell
pytest -q
```

Os testes desabilitam CSRF apenas na configuração de teste. CSRF continua habilitado na execução normal.

## Categorias OWASP Top 10:2025 abordadas

Referência oficial: https://top10.owasp.org/2025/pt-BR/

Os controles abaixo mitigam riscos específicos; não constituem certificação nem garantia de ausência de vulnerabilidades.

### A01:2025 — Controle de Acesso Quebrado

- `app.py`: `login_required` verifica a sessão no servidor antes de renderizar `/dashboard` e aceitar `/calculate`.
- Não basta ocultar elementos no frontend: o servidor redireciona solicitações sem autenticação.
- O logout chama `session.clear()` e as rotas protegidas deixam de aceitar a sessão.
- `tests/test_auth.py`: testes verificam bloqueio sem login e invalidação da sessão após logout.

### A07:2025 — Falhas de Autenticação

- `templates/login.html` e `templates/register.html`: apresentam login e cadastro nativos.
- `app.py`: valida entradas no servidor, exige senha de 12 a 128 caracteres com maiúscula, minúscula, número e símbolo, normaliza o e-mail, impede cadastro duplicado e grava contas em JSON usando bloqueio e substituição atômica do arquivo.
- `werkzeug.security.generate_password_hash` e `check_password_hash` protegem a verificação de senha sem armazenar senhas em texto puro.
- `Flask-Limiter` limita tentativas de login e cadastro a cinco por minuto por endereço IP.
- Sessões expiram após 30 minutos; o cookie tem `HttpOnly` e `SameSite=Lax`, além de `Secure` em produção.
- Limitação conhecida: o rate limit usa memória local, adequada para demonstração com um processo. Em uma instalação com múltiplos workers/servidores, use armazenamento compartilhado, como Redis.

### A02:2025 — Configuração de Segurança Incorreta

- `app.py`: o modo produção falha ao iniciar se `SECRET_KEY` não estiver configurada; o modo debug não é ativado. O arquivo JSON de usuários deve ficar fora do diretório público e do repositório.
- `SESSION_COOKIE_SECURE` é ativado em produção.
- Cabeçalhos `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` e `Cache-Control: no-store` são definidos na resposta.
- `.gitignore` exclui `.env`, chaves privadas e artefatos locais.
- `deploy/secureops-lab.service` executa o processo como usuário de sistema sem login interativo.

## Cálculo do IMC

A fórmula utilizada é peso em quilogramas dividido pela altura em metros ao quadrado. As faixas exibidas seguem a página da Secretaria de Estado de Saúde do Rio de Janeiro: https://www.saude.rj.gov.br/obesidade/calcule-seu-imc.

O protótipo usa `IMC >= 40` para Obesidade III, tratando o limiar 40 como pertencente a essa faixa. O IMC é uma medida de triagem e não substitui avaliação individual por profissional de saúde.

## CI/CD com GitHub Actions

O workflow `.github/workflows/ci-cd.yml` executa os testes em pushes e pull requests para `main`. Após um `push` em `main` com testes aprovados, o job de deploy envia os arquivos para a área de staging do servidor e executa um script fixo de implantação.

### Segredos necessários no GitHub

Em **Settings → Secrets and variables → Actions**, cadastre os segredos abaixo. Configure também o ambiente `production` em **Settings → Environments**.

- `DEPLOY_HOST`: IP ou hostname da VM OCI.
- `DEPLOY_USER`: usuário SSH que fará o deploy (por exemplo, `ubuntu`).
- `DEPLOY_SSH_KEY`: chave privada SSH exclusiva para deploy.
- `DEPLOY_KNOWN_HOSTS`: chave pública/host key do servidor, previamente verificada e obtida por canal confiável.

Nunca use `ssh-keyscan` como única validação de identidade do servidor em produção e nunca faça commit da chave privada.

### Armazenamento das contas sem banco de dados

As contas são guardadas em um arquivo JSON definido por `USERS_FILE`. Localmente, o padrão é `instance/users.json`, que está excluído pelo `.gitignore`. Na VM, use `/var/lib/secureops-lab/users.json`, fora do diretório do código e do Nginx. O arquivo armazena nome, e-mail, identificador, data de criação e hash da senha — nunca a senha original. Em Linux, o arquivo é gravado com permissões `0600`. A aplicação usa gravação atômica e bloqueio de arquivo para reduzir o risco de corrupção em gravações simultâneas.

Essa abordagem evita administrar um banco de dados e é apropriada para o protótipo acadêmico, mas não substitui um banco transacional em sistemas de produção com alta concorrência. Configure backups protegidos do arquivo JSON; perder esse arquivo significa perder as contas cadastradas.

### Preparação da VM OCI

1. Faça backup da configuração atual do Nginx.
2. Envie a pasta `deploy/` para a VM por um meio administrativo confiável.
3. Na pasta do projeto, execute:

   ```bash
   sudo bash deploy/bootstrap_oci.sh
   ```

   O script instala dependências do sistema, cria o usuário `secureops`, configura a unidade systemd e instala um comando de deploy restrito. Revise o script antes de executá-lo.

4. Confira `/etc/secureops-lab/secureops.env`: configure uma `SECRET_KEY` forte e `USERS_FILE=/var/lib/secureops-lab/users.json`. O script de preparação cria `/var/lib/secureops-lab` com permissão de gravação para o usuário `secureops`; esse caminho fica fora da pasta substituída durante os deploys para preservar as contas cadastradas. O arquivo de ambiente deve pertencer a `root:secureops` e ter modo `0640`. O arquivo JSON conterá hashes de senha, deve permanecer fora do repositório e precisa ser incluído na rotina de backup.

5. Cadastre os quatro GitHub Actions secrets listados acima. O workflow copia os arquivos para `~/secureops-lab-staging/`, executa o deploy e reinicia `secureops-lab` após os testes passarem.
6. Configure o trecho de `deploy/nginx-location.conf` dentro do `server` HTTPS existente no Nginx, preservando certificados Certbot e redirecionamento HTTP→HTTPS. Teste e recarregue:

   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

7. Verifique o serviço e o HTTPS:

   ```bash
   sudo systemctl status secureops-lab
   curl -I https://SEU-DOMINIO/
   ```

**Importante:** o primeiro deploy depende da preparação inicial da VM e do cadastro dos segredos. O workflow não deve ser considerado operacional até que SSH, o comando restrito de deploy, a unidade systemd e o proxy Nginx tenham sido validados.

## Uso e auditoria assistidos por IA

O desenvolvimento e a revisão inicial deste código foram realizados com auxílio de IA. Para a entrega acadêmica, execute os testes, revise o código e registre no README as verificações efetivamente realizadas, as falhas encontradas e as correções aplicadas. Não declare uma auditoria independente nem testes que ainda não foram executados. A responsabilidade final pela validação e operação é do aluno.

## Estrutura do projeto

```text
SecureOps-Lab/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── templates/
│   ├── login.html
│   ├── register.html
│   └── dashboard.html
├── static/
│   ├── css/style.css
│   └── js/main.js
├── tests/test_auth.py
├── deploy/
│   ├── bootstrap_oci.sh
│   ├── deploy-secureops-lab.sh
│   ├── secureops-lab.service
│   └── nginx-location.conf
└── .github/workflows/ci-cd.yml
```
