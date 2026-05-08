# simulados_server

## API de exercícios

Servidor API (sem dependências extras):

```bash
python3 api_server.py
```

Por padrão sobe em `0.0.0.0:8080`.

### Rotas

- `GET /api/health`
- `GET /api/materias`
- `GET /api/stats/geral`
- `GET /api/stats/materias`
- `GET /api/questoes?materia=Biologia&tipo=alternativas&limit=50&offset=0`

Filtros de `tipo`:

- `alternativas`
- `aberta`
- `erro`

## Rodar no VPS com systemd

Arquivo sugerido: `/etc/systemd/system/robo-simulados-api.service`

```ini
[Unit]
Description=Robo Simulados API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=robo
Group=robo
WorkingDirectory=/opt/robo-simulados
Environment=API_HOST=0.0.0.0
Environment=API_PORT=8080
ExecStart=/usr/bin/python3 /opt/robo-simulados/api_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ativar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now robo-simulados-api.service
sudo systemctl status robo-simulados-api.service --no-pager
```
