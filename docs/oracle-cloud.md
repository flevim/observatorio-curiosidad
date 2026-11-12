# Servidor en Oracle Cloud (gratis)

Objetivo: una VM Linux siempre encendida que corre la API, la actualización diaria y la descarga de temas nuevos,
con disco persistente. Todo lo de abajo usa el nivel **Always Free** de Oracle.

> La cuenta la crea y verifica **la persona titular** (identidad y tarjeta). Nadie más debe ingresar esos datos.

## 1. Crear la cuenta

1. Entra a https://www.oracle.com/cloud/free/ y pulsa **Start for free**.
2. Completa tus datos y verifica el correo y el teléfono.
3. Una tarjeta de crédito/débito es obligatoria para verificar la identidad. El nivel gratuito no cobra si no
   cambias a una cuenta de pago. En **Billing → Upgrade** puedes revisar que siga en «Free Tier».
4. **Región:** elige la más cercana. Para Chile suele ser **Chile (Santiago)**; si no hay capacidad, prueba
   otra región (Brasil São Paulo o EE. UU.). La región no se puede cambiar después.

## 2. Llave SSH (en tu computador)

Crea una llave para entrar a la VM. En PowerShell o Git Bash:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_observatorio -C "observatorio"
```

Queda un archivo **privado** (`oracle_observatorio`, no lo compartas) y uno **público** (`oracle_observatorio.pub`).
Oracle pedirá el contenido del `.pub`.

## 3. Crear la VM

En la consola de Oracle: **Menu → Compute → Instances → Create instance**.

| Campo | Valor |
| --- | --- |
| Name | `observatorio` |
| Image | **Canonical Ubuntu 24.04** (pulsa *Change image*) |
| Shape | **VM.Standard.A1.Flex** (Ampere ARM): **2 OCPU y 12 GB de RAM** |
| Networking | Asignar **IPv4 pública** (*Assign a public IPv4 address*) |
| SSH keys | *Paste public keys* → pega el contenido de `oracle_observatorio.pub` |
| Boot volume | **100 GB** (el nivel gratuito permite hasta 200 GB en total) |

Pulsa **Create**. Cuando el estado esté en *Running*, copia la **Public IP**.

Si aparece **«Out of capacity»**, la región no tiene VMs gratuitas libres en ese momento: vuelve a intentar más
tarde, o prueba otra región (crear una cuenta nueva no es necesario).

## 4. Entrar a la VM

```bash
ssh -i ~/.ssh/oracle_observatorio ubuntu@IP_PUBLICA
```

La primera vez pregunta si confías en el servidor: responde `yes`.

## 5. Instalar el observatorio

Dentro de la VM:

```bash
git clone https://github.com/flevim/observatorio-curiosidad.git
bash observatorio-curiosidad/deploy/servidor/setup.sh
```

El script instala Python, las dependencias, los servicios (`observatorio-api` y el temporizador diario) y `cloudflared`.

Luego:

```bash
nano ~/observatorio-curiosidad/.env          # completa OBSERVATORIO_CONTACT (tu correo)
sudo systemctl restart observatorio-api
curl -s http://127.0.0.1:8010/api/health     # debe responder {"ok": true, ...}
```

**Primera descarga completa** (tarda ~2 horas). Conviene correrla en `tmux` para que no se corte si se cae la conexión:

```bash
sudo apt-get install -y tmux
tmux new -s datos
cd ~/observatorio-curiosidad && .venv/bin/python -m observatorio all
# Para salir sin detenerla: Ctrl+B y luego D. Para volver: tmux attach -t datos
```

## 6. Dejarlo accesible desde internet

El servidor no necesita abrir puertos: `cloudflared` crea una conexión **saliente** hacia Cloudflare.

**Opción A — rápida (sin cuenta, dirección temporal):**

```bash
cloudflared tunnel --url http://127.0.0.1:8010
```

Muestra una dirección `https://….trycloudflare.com`. Cambia cada vez que se reinicia el túnel.

**Opción B — dirección fija (requiere cuenta de Cloudflare y un dominio):** en el panel de Cloudflare,
*Zero Trust → Networks → Tunnels → Create tunnel*, copia el comando de instalación que muestra con su token y
ejecútalo en la VM. Luego asigna un subdominio (por ejemplo `api.tudominio.org`) que apunte a
`http://127.0.0.1:8010`.

## 7. Conectar la web publicada

La web de GitHub Pages necesita saber la dirección de la API. Se configura al compilar:

```bash
VITE_API_BASE=https://api.tudominio.org npm --prefix web run build
```

Y en el `.env` del servidor, `OBSERVATORIO_CORS_ORIGINS` debe incluir el origen de la web (por ejemplo
`https://flevim.github.io`). Después de cambiarlo: `sudo systemctl restart observatorio-api`.

## Mantención

- Logs de la API: `journalctl -u observatorio-api -f`
- Logs de la actualización diaria: `journalctl -u observatorio-diario`
- Próxima actualización: `systemctl list-timers observatorio-diario.timer`
- Actualizar el código: `cd ~/observatorio-curiosidad && git pull && sudo systemctl restart observatorio-api`

**Aviso importante:** Oracle puede recuperar VMs del nivel gratuito si están casi sin uso durante mucho tiempo.
La actualización diaria y la API mantienen algo de actividad, pero conviene revisar cada tanto que la VM siga
encendida.
