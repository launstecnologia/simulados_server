# Deploy VPS (contínuo, sem bash aberto)

Este projeto pode rodar continuamente via `systemd`, com reinício automático.

## 1) Subir para Git

No seu ambiente local:

```bash
cd "/Users/lucasmoraes/Projects/Robo Simulados"
git init
git add .
git commit -m "chore: add VPS deploy package"
git branch -M main
git remote add origin <URL_DO_REPO>
git push -u origin main
```

## 2) Baixar no servidor

```bash
sudo mkdir -p /opt/robo-simulados
sudo chown -R $USER:$USER /opt/robo-simulados
git clone <URL_DO_REPO> /opt/robo-simulados
cd /opt/robo-simulados
```

## 3) Rodar setup automático

Como root:

```bash
cd /opt/robo-simulados
chmod +x deploy/setup_vps.sh
sudo APP_USER=robo APP_DIR=/opt/robo-simulados bash deploy/setup_vps.sh
```

## 4) Configurar credenciais

```bash
sudo nano /opt/robo-simulados/.env.server
```

Preencha:

- `ROBO_EMAIL`
- `ROBO_SENHA`
- `ROBO_HEADLESS=1`

## 5) Iniciar e monitorar

```bash
sudo systemctl start robo-simulados.service
sudo systemctl status robo-simulados.service
sudo journalctl -u robo-simulados.service -f
tail -f /opt/robo-simulados/logs/robo-simulados.out.log
```

## Atualizar código no futuro

```bash
cd /opt/robo-simulados
git pull
sudo systemctl restart robo-simulados.service
```
