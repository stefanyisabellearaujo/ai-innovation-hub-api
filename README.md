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
