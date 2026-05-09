# Documentação da API de Exercícios

Base URL (produção):

`http://69.62.86.185:8080`

Formato de resposta: `application/json` (UTF-8)

---

## 1) Healthcheck

Endpoint:

`GET /api/health`

Resposta esperada:

```json
{ "ok": true }
```

---

## 2) Listar matérias disponíveis

Endpoint:

`GET /api/materias`

Resposta:

```json
{
  "materias": [
    "Arte",
    "Biologia",
    "Eletivas"
  ]
}
```

---

## 3) Estatísticas gerais

Endpoint:

`GET /api/stats/geral`

Resposta:

```json
{
  "arquivo": "/opt/robo-simulados/questoes_extraidas.json",
  "stats": {
    "total": 4310,
    "alternativas": 3800,
    "abertas": 500,
    "erro": 10
  }
}
```

---

## 4) Estatísticas por matéria

Endpoint:

`GET /api/stats/materias`

Resposta:

```json
{
  "totais": {
    "total": 4310,
    "alternativas": 3800,
    "abertas": 500,
    "erro": 10
  },
  "materias": [
    {
      "materia": "Biologia",
      "total": 1000,
      "alternativas": 900,
      "abertas": 98,
      "erro": 2
    }
  ]
}
```

---

## 5) Listar questões (principal)

Endpoint:

`GET /api/questoes`

Parâmetros de query:

- `materia` (opcional): filtra por matéria. Ex.: `Biologia`
- `tipo` (opcional): `alternativas`, `aberta`, `erro`
- `q` (opcional): busca textual geral (id, origem, enunciado, resolução, tags, tópicos)
- `id` (opcional): id exato da questão
- `dificuldade` (opcional): ex.: `Fácil`, `Médio`, `Difícil`
- `tag` (opcional): filtra por tag (contém)
- `topico` (opcional): filtra por tópico (contém)
- `ano` (opcional): filtra por ano da origem. Ex.: `2025`
- `origem_titulo` (opcional): filtra por título da origem (contém)
- `limit` (opcional): padrão `50`, mínimo `1`, máximo `500`
- `offset` (opcional): padrão `0`

Exemplos:

- `GET /api/questoes?limit=20&offset=0`
- `GET /api/questoes?materia=Biologia&limit=20&offset=0`
- `GET /api/questoes?tipo=alternativas&limit=20&offset=40`
- `GET /api/questoes?materia=Matemática&tipo=aberta&limit=50&offset=0`
- `GET /api/questoes?q=SARESP%202025%20Q40`
- `GET /api/questoes?materia=Química&ano=2025&origem_titulo=SARESP`
- `GET /api/questoes?topico=equil%C3%ADbrios&dificuldade=F%C3%A1cil`
- `GET /api/questoes?id=474822`

Resposta:

```json
{
  "total": 4310,
  "offset": 0,
  "limit": 20,
  "count": 20,
  "questoes": [
    {
      "id": "476497",
      "materia": "Biologia",
      "tipo": "Múltipla escolha",
      "enunciado_html": "<p>...</p>",
      "alternativas": {
        "A": "Texto A",
        "B": "Texto B",
        "C": "Texto C",
        "D": "Texto D"
      },
      "gabarito": "A",
      "resolucao_html": "<p>...</p>"
    }
  ]
}
```

---

## 6) Facetas dinâmicas (filtros vinculados)

Use esta rota para montar tela de filtros encadeados.

Endpoint:

`GET /api/facets`

Ela aceita os mesmos filtros de `/api/questoes` (`tipo`, `materia`, `ano`, `origem_titulo`, `dificuldade`, `topico`, `tag`, `q`) e retorna:

- `total_filtrado`
- opções disponíveis e contagem de cada campo já vinculadas ao filtro atual

Exemplo:

`GET /api/facets?tipo=alternativas&materia=Química&ano=2025`

Resposta (resumo):

```json
{
  "total_filtrado": 120,
  "facets": {
    "materias": [{ "valor": "Química", "total": 120 }],
    "anos": [{ "valor": "2025", "total": 120 }],
    "origens_titulo": [{ "valor": "SARESP 1º EM - 1ª Aplicação", "total": 34 }],
    "dificuldades": [{ "valor": "Fácil", "total": 80 }],
    "tipos": [{ "valor": "multipla escolha", "total": 120 }],
    "topicos": [{ "valor": "Físico-Química", "total": 41 }],
    "tags": [{ "valor": "Química", "total": 120 }]
  }
}
```

Fluxo recomendado:

1. Chamar `/api/facets` sem filtros.
2. Usuário seleciona `tipo=multipla escolha` ou `tipo=alternativas`.
3. Rechamar `/api/facets` com os filtros já escolhidos.
4. Exibir apenas opções com vínculo (as que vieram no retorno).
5. Quando finalizar seleção, chamar `/api/questoes` com os mesmos filtros.

---

## Como paginar corretamente

1. Faça a primeira chamada com `offset=0`.
2. Guarde `total`, `limit` e `count`.
3. Próxima página: `offset = offset + limit`.
4. Pare quando `count == 0` ou `offset >= total`.

Exemplo:

- Página 1: `?limit=100&offset=0`
- Página 2: `?limit=100&offset=100`
- Página 3: `?limit=100&offset=200`

---

## Modelo de uso para IA (prompt pronto)

Use este prompt na sua IA agente:

```txt
Consuma a API de exercícios em http://69.62.86.185:8080.

Regras:
1) Primeiro consulte /api/health.
2) Depois consulte /api/stats/geral para saber o total.
3) Extraia questões de /api/questoes paginando com limit=200 e offset incremental.
4) Salve os campos: id, materia, tipo, enunciado_html, alternativas, gabarito, resolucao_html, bncc, tags, topicos.
5) Não duplicar por id.
6) Se matéria for informada, aplicar query materia=<nome>.
7) Se tipo for informado, aplicar query tipo=alternativas|aberta|erro.
8) Encerrar quando count=0 ou offset>=total.
```

---

## cURL rápido

```bash
curl -sS "http://69.62.86.185:8080/api/health"
curl -sS "http://69.62.86.185:8080/api/stats/geral"
curl -sS "http://69.62.86.185:8080/api/questoes?limit=5&offset=0"
curl -sS "http://69.62.86.185:8080/api/questoes?materia=Biologia&tipo=alternativas&limit=5&offset=0"
```

---

## Observações

- A API retorna JSON bruto com HTML em alguns campos (`enunciado_html`, `resolucao_html`).
- O campo `total` na rota `/api/questoes` respeita o filtro aplicado.
- Para alto volume, prefira `limit` entre `100` e `300`.

---

## MySQL (sincronização horária)

Arquivos no projeto:

- `db/schema_mysql.sql`
- `sync_mysql.py`

### Objetivo

Manter o JSON como fonte, mas também persistir no MySQL para consultas encadeadas rápidas no front.

### Tabelas principais

- `questoes` (questão base)
- `materias`, `tipos`, `dificuldades`
- `origens` (ano, título, número/código do simulado)
- `topicos`, `tags`
- vínculo N:N: `questao_topicos`, `questao_tags`

### 1) Criar banco e tabelas

```bash
mysql -u root -p < /opt/robo-simulados/db/schema_mysql.sql
```

### 2) Variáveis de ambiente (exemplo)

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD='SUA_SENHA'
export MYSQL_DATABASE=simulados
```

### 3) Rodar carga inicial

```bash
cd /opt/robo-simulados
/usr/bin/python3 sync_mysql.py
```

### 4) Agendar atualização de hora em hora

```bash
crontab -e
```

Adicionar:

```cron
0 * * * * cd /opt/robo-simulados && MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_USER=root MYSQL_PASSWORD='SUA_SENHA' MYSQL_DATABASE=simulados /usr/bin/python3 sync_mysql.py >> /opt/robo-simulados/logs/cron_sync_mysql.log 2>&1
```

### Exemplo de SQL para front com filtros encadeados

```sql
SELECT
  q.id,
  m.nome AS materia,
  t.nome AS tipo,
  d.nome AS dificuldade,
  o.ano,
  o.titulo AS origem_titulo,
  o.numero AS codigo_simulado
FROM questoes q
LEFT JOIN materias m ON m.id = q.materia_id
LEFT JOIN tipos t ON t.id = q.tipo_id
LEFT JOIN dificuldades d ON d.id = q.dificuldade_id
LEFT JOIN origens o ON o.id = q.origem_id
WHERE t.nome LIKE '%multipla%'
  AND m.nome = 'Química'
  AND o.ano = '2025';
```
