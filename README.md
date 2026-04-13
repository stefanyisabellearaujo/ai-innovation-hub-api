# AI Innovation Hub — Backend

API REST construída com **FastAPI**, **SQLAlchemy (async)** e **PostgreSQL 16**.

---

## Executar com Docker (recomendado)

```bash
# 1. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env: defina JWT_SECRET (obrigatório) e HUGGINGFACE_TOKEN (opcional)

# 2. Suba o banco + a API
docker compose up --build -d

# 3. Na PRIMEIRA execução, rode as migrations
docker compose exec backend alembic upgrade head

# API disponível em:  http://localhost:8000
# Swagger UI em:      http://localhost:8000/docs
```

> O `docker-compose.yml` inclui o PostgreSQL — não é necessário instalá-lo separadamente.

---

## Executar localmente (sem Docker)

### Pré-requisitos

- Python 3.11+
- PostgreSQL 16 rodando localmente

```bash
# Criar e ativar virtualenv
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite .env: ajuste DATABASE_URL para apontar para localhost

# Rodar migrations
alembic upgrade head

# Iniciar o servidor
uvicorn app.main:app --reload --port 8000
```

---

## Variáveis de ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `DATABASE_URL` | URL async do PostgreSQL | Sim |
| `POSTGRES_DB` | Nome do banco (usado pelo docker-compose) | Sim |
| `POSTGRES_USER` | Usuário do banco | Sim |
| `POSTGRES_PASSWORD` | Senha do banco | Sim |
| `JWT_SECRET` | Chave secreta para assinar tokens — **use valor único e aleatório** | Sim |
| `JWT_ALGORITHM` | Algoritmo JWT | Não (padrão: HS256) |
| `JWT_EXPIRATION_HOURS` | Validade do token em horas | Não (padrão: 24) |
| `HUGGINGFACE_TOKEN` | Token gratuito — [obter aqui](https://huggingface.co/settings/tokens) | Não (fallback: "Other") |
| `CORS_ORIGINS` | Origens permitidas separadas por vírgula | Não (padrão: localhost:3000) |

> **Gerar JWT_SECRET seguro:** `python3 -c "import secrets; print(secrets.token_hex(32))"`

---

## Primeiro admin

O papel **admin** não pode ser selecionado no formulário de cadastro do frontend.
Para criar o primeiro administrador, use a API após o backend estar rodando:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin","email":"admin@empresa.com","password":"senha-segura","role":"admin"}'
```

Após isso, novos admins só podem ser criados via painel de administração.

---

## Migrations

```bash
# Aplicar todas as migrations (necessário na primeira execução)
alembic upgrade head

# Criar nova migration após alterar models
alembic revision --autogenerate -m "descreva a mudança"

# Reverter uma migration
alembic downgrade -1
```

---

## Testes

```bash
# Todos os testes (SQLite in-memory — sem PostgreSQL necessário)
pytest

# Verbose
pytest -v

# Arquivo específico
pytest tests/test_auth_router.py -v

# Testes e2e com API real do HuggingFace (requer HUGGINGFACE_TOKEN)
pytest tests/e2e/ -m e2e -v
```

---

## Endpoints principais

| Método | Rota | Roles | Descrição |
|--------|------|-------|-----------|
| POST | `/api/auth/register` | público | Cadastro (user ou developer) |
| POST | `/api/auth/login` | público | Login — retorna JWT |
| GET | `/api/auth/me` | autenticado | Dados do usuário logado |
| GET | `/api/ideas` | todos | Listar ideias (filtros + paginação) |
| POST | `/api/ideas` | user, developer | Criar ideia (categorizada por IA) |
| PUT | `/api/ideas/{id}` | autor / colaborador | Atualizar ideia |
| DELETE | `/api/ideas/{id}` | autor | Deletar ideia |
| POST | `/api/ideas/{id}/vote` | user, developer | Toggle voto |
| POST | `/api/ideas/{id}/collaborators` | developer | Entrar como colaborador |
| POST | `/api/ideas/{id}/comments` | user, developer | Comentar |
| POST | `/api/ai/similar` | autenticado | Buscar ideias similares |
| GET | `/api/ranking/developers` | developer, admin | Ranking de desenvolvedores |
| GET | `/api/admin/stats` | admin | Métricas da plataforma |
| GET | `/api/admin/users` | admin | Listar usuários |
| PUT | `/api/admin/users/{id}/role` | admin | Alterar role de usuário |

Documentação completa e interativa: **http://localhost:8000/docs**

---

## APIs Externas

### HuggingFace Inference API

| Item | Detalhe |
|------|---------|
| **Modelo** | `facebook/bart-large-mnli` |
| **Tarefa** | Zero-shot text classification (NLI) |
| **Licenca do modelo** | MIT License |
| **Termos de uso da API** | [HuggingFace Terms of Service](https://huggingface.co/terms-of-service) |
| **Endpoint externo** | `POST https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli` |
| **Cadastro obrigatorio** | Sim — conta gratuita em [huggingface.co](https://huggingface.co) |
| **Credencial** | Bearer token em `HUGGINGFACE_TOKEN` no `.env` |
| **Plano gratuito** | Disponivel com rate limits — 429 tratado com fallback automatico |
| **Cold start** | Modelo inativo pode retornar 503; o servico retenta uma vez apos 2 s |

#### Para obter o token

1. Crie uma conta gratuita em [huggingface.co](https://huggingface.co)
2. Acesse [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
3. Crie um token com permissao de leitura (_Read_)
4. Adicione ao `.env`:
   ```
   HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
   ```

#### Categorias classificadas

O modelo classifica textos em uma destas categorias:
`Natural Language Processing` · `Computer Vision` · `Process Automation` · `Data Analytics` · `Generative AI`

Se nenhuma categoria for identificada com confianca, ou se a API falhar, o valor de fallback e `"Other"`.

---

#### Rotas que chamam esta API — detalhamento

**`POST /api/ideas` — Criacao de ideia**

Chamada: sempre que uma ideia e criada.
O que e enviado: a `description` da ideia como `inputs` com as 5 categorias como `candidate_labels`.
O que e usado: o label com maior score vira o campo `category` salvo no banco.
Falha: ideia e salva normalmente com `category = "Other"`.

---

**`PUT /api/ideas/{id}` — Edicao de ideia**

Chamada: somente se `title` ou `description` forem alterados. Mudancas apenas de `status` nao disparam a API.
O que e enviado: a descricao atualizada da ideia.
O que e usado: o novo label substitui o `category` existente.
Falha: `category` e sobrescrito com `"Other"`. O restante da atualizacao e salvo normalmente.

---

**`POST /api/ai/categorize` — Categorizacao direta**

Chamada: on-demand pelo frontend (ex: previa de categoria enquanto o usuario escreve).
Body: `{ "description": "texto" }`
Resposta:
```json
{
  "category": "Natural Language Processing",
  "scores": {
    "Natural Language Processing": 0.72,
    "Computer Vision": 0.10,
    "Process Automation": 0.08,
    "Data Analytics": 0.06,
    "Generative AI": 0.04
  }
}
```
Falha: retorna `{ "category": "Other", "scores": {} }`.

---

**`POST /api/ai/similar` — Ideias similares**

Chamada: quando o usuario busca ideias parecidas antes de criar uma nova.
Como a API e usada internamente:
1. A descricao e enviada para a HuggingFace para obter a categoria
2. Todas as ideias do banco sao carregadas e pontuadas por similaridade de tokens (Sorensen-Dice)
3. Ideias com a mesma categoria recebem bonus de `+0.15` no score final
4. Retorna ate 5 ideias com score >= 0.25, ordenadas por relevancia

Falha: o algoritmo de similaridade continua funcionando sem o bonus de categoria. Nenhum resultado e perdido.

---

#### Resumo

| Rota | Metodo | Dispara HuggingFace? | Condicao |
|------|--------|----------------------|----------|
| `/api/ideas` | POST | Sempre | Criacao de ideia |
| `/api/ideas/{id}` | PUT | Somente se `title` ou `description` mudar | Edicao de conteudo |
| `/api/ai/categorize` | POST | Sempre | Chamada direta |
| `/api/ai/similar` | POST | Sempre | Busca de similares |

---

## Decisões técnicas

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| ORM | SQLAlchemy 2 async | Performance com asyncpg; suporte nativo async/await |
| Autenticação | JWT com role no payload | Evita consulta ao banco a cada request |
| Hash de senha | bcrypt | Padrão da indústria, resistente a brute force |
| Migrations | Alembic | Integração nativa com SQLAlchemy |
| Config | pydantic-settings | Validação tipada das variáveis de ambiente |
| Categorização IA | HuggingFace gratuito | Sem custo; modelo `facebook/bart-large-mnli` |
| Permissões | FastAPI Depends | Declarativo, testável, composável |
| Testes | SQLite in-memory | Sem dependência de PostgreSQL nos testes unitários |
