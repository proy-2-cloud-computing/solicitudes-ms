# itsm-solicitudes

Microservicio de **solicitudes de servicio** de la plataforma ITSM (Grupo 6).
Stack: **Python 3.12 + Serverless Framework v4 + API Gateway (REST) + Lambda +
DynamoDB + S3 + SNS**.

El servicio es dueño solo de las solicitudes. El `tenant_id` se lee **siempre**
del token de Cognito; nunca se acepta del body ni de la ruta. El Catálogo de
Servicios se consulta por API al crear la solicitud y sus datos (`nombre`,
`sla_horas`, `requiere_aprobacion`) se copian en la solicitud.

## Estructura

```
solicitudes-ms/
├── serverless.yml
├── requirements.txt
├── package.json
├── src/
│   ├── common/
│   │   ├── auth.py           # claims, tenant, grupos
│   │   ├── catalog.py        # cliente del Catálogo
│   │   ├── db.py             # DynamoDB, contador, historial, paginación
│   │   ├── events.py         # SNS publish (best-effort)
│   │   ├── responses.py      # JSON, CORS, ApiError
│   │   ├── storage.py        # URLs prefirmadas S3
│   │   ├── timeutils.py      # SLA y fechas UTC
│   │   ├── transitions.py    # máquina de estados y roles
│   │   └── validation.py     # validación de entradas
│   └── handlers/
│       ├── crear.py
│       ├── listar.py
│       ├── obtener.py
│       ├── cambiar_estado.py
│       ├── adjuntos.py
│       ├── historial.py
│       └── resumen.py
├── scripts/
│   ├── mock_catalogo.py
│   └── seed_solicitudes.py
├── tests/
└── docs/
    ├── PLAN_SOLICITUDES.md
    ├── openapi.yaml
    └── postman_collection.json
```

## Modelo DynamoDB

Tabla `itsm-solicitudes-{stage}`:

- PK: `tenant_id`
- SK: `sk` → `REQ#000870`
- GSI1: `tenant_id` + `estado_fecha` (`en_proceso#2026-11-11T09:30:00Z`)
- Billing: `PAY_PER_REQUEST`
- Nunca se usa `Scan`.

| Ítem | SK | Contenido |
|---|---|---|
| Solicitud | `REQ#000870` | Negocio |
| Contador | `CONTADOR#REQ` | `ultimo_id` atómico |
| Historial | `HIST#REQ#000870#<fecha>#<evento>` | Auditoría |

La API expone `solicitud_id` (mismo valor que `sk`) para no filtrar el detalle
interno de la clave.

## Endpoints

Todos requieren `Authorization: <ID token>` de Cognito. El authorizer se toma
del Output `UserPoolArn` de `itsm-base`.

| Método | Ruta | Rol |
|---|---|---|
| `POST` | `/solicitudes` | `solicitante`, `agente`, `aprobador` o `admin` |
| `GET` | `/solicitudes` | autenticado |
| `GET` | `/solicitudes/{id}` | autenticado |
| `PUT` | `/solicitudes/{id}/estado` | según transición |
| `POST` | `/solicitudes/{id}/adjuntos` | dueño o `agente`/`admin` |
| `PUT` | `/solicitudes/{id}/adjuntos` | dueño o `agente`/`admin` |
| `GET` | `/solicitudes/{id}/historial` | autenticado |
| `GET` | `/solicitudes/resumen` | autenticado |

`{id}` viaja URL-encoded: `REQ%23000870`. API Gateway lo entrega ya decodificado.

### Crear

```http
POST /solicitudes
Content-Type: application/json
```

```json
{
  "servicio_id": "SVC#000012",
  "titulo": "Acceso VPN para nuevo analista",
  "descripcion": "Alta de acceso remoto",
  "prioridad": "medio"
}
```

Validaciones: `servicio_id` obligatorio, `titulo` 3–200, `descripcion` ≤2000,
`prioridad` en `bajo|medio|alto|critico` (default `medio`).

Flujo:

1. Extrae `tenant_id` y `sub` del token.
2. Valida el body.
3. `GET {CATALOGO_URL}/catalogo/{servicio_id}` reenviando el mismo token.
4. Si no existe o está inactivo → `400`; timeout/5xx → `503` sin escribir nada.
5. Incrementa el contador atómico.
6. Calcula `sla_vence_en = creado_en + sla_horas`.
7. Estado inicial: `en_aprobacion` si requiere aprobación; si no, `nueva`.
8. Escribe solicitud + primer historial en una transacción.
9. Publica `solicitud-creada` (best-effort).
10. Responde `201`.

### Listar

```
GET /solicitudes?estado=en_proceso&limit=25&next=<token>
```

- Sin `estado`: `Query` por `begins_with(sk, "REQ#")`.
- Con `estado`: `Query` sobre GSI1.
- `limit` 1–100 (default 25).
- `next` es un token opaco (base64 del `LastEvaluatedKey`), `null` al final.

### Cambiar estado

```json
{
  "estado": "en_proceso",
  "asignado_a": "u-90de",
  "comentario": "Asignado a redes"
}
```

| Desde | Hacia | Quién |
|---|---|---|
| `nueva` | `en_aprobacion`, `en_proceso` | `agente`, `admin` |
| `nueva` | `cancelada` | `agente`, `admin` o el solicitante dueño |
| `en_aprobacion` | `en_proceso` | `aprobador`, `admin` |
| `en_aprobacion` | `cancelada` | `aprobador`, `admin` |
| `en_proceso` | `completada` | `agente`, `admin` |
| `en_proceso` | `cancelada` | `agente`, `admin` |
| `completada` / `cancelada` | — | terminal |

Usa `ConditionExpression: estado = :anterior` (bloqueo optimista). Si otro
usuario cambió el estado antes, responde `409`. Escribe historial y, al pasar a
`completada`, publica `solicitud-completada`.

### Adjuntos

1. `POST /solicitudes/{id}/adjuntos`:

```json
{ "nombre_archivo": "vpn.pdf", "content_type": "application/pdf" }
```

Respuesta:

```json
{
  "upload_url": "https://...",
  "key": "empresa-beta/solicitudes/REQ-000870/uuid-vpn.pdf",
  "expires_in": 300,
  "metodo": "PUT",
  "content_type": "application/pdf",
  "solicitud_id": "REQ#000870"
}
```

2. El navegador hace `PUT` a `upload_url` con el mismo `Content-Type`.

3. `PUT /solicitudes/{id}/adjuntos` con `{"key": "<key>"}` confirma que el
   objeto existe en S3 y recién entonces lo agrega a `adjuntos`.

La key debe empezar con `{tenant_id}/solicitudes/{REQ-000870}/`; si no, `400`.

## Catálogo: estado actual

`itsm-catalogo` **aún no existe**. Por eso:

- `CATALOGO_URL` se toma de la variable de entorno, con default
  `http://localhost:8000`.
- Para pruebas locales: `python3 scripts/mock_catalogo.py`.
- Para un Lambda desplegado necesitas una URL **públicamente accesible**
  (Postman Mock Server, un mock en EC2/ngrok o el Catálogo real). `localhost`
  dentro de Lambda apunta a la propia Lambda, no a tu máquina.
- Cuando exista `itsm-catalogo-dev`, despliega con:

```bash
CATALOGO_URL=$(aws cloudformation describe-stacks \
  --stack-name itsm-catalogo-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text) \
  npx serverless deploy --stage dev
```

o cambia en `serverless.yml`:

```yaml
CATALOGO_URL: ${cf:itsm-catalogo-${self:provider.stage}.ApiUrl}
```

Contrato esperado:

```json
{
  "tenant_id": "empresa-beta",
  "servicio_id": "SVC#000012",
  "nombre": "Acceso VPN",
  "sla_horas": 48,
  "requiere_aprobacion": true,
  "activo": true
}
```

El `#` se envía URL-encoded (`SVC%23000012`). Si la respuesta trae un
`tenant_id` distinto al del token, se responde `400` para no filtrar servicios
de otro tenant.

## Requisitos y despliegue

- Node.js 20+ y npm
- Python 3.10+ con `boto3` (scripts locales)
- `itsm-base-dev` desplegado en la misma región
- Credenciales AWS o AWS Academy

```bash
npm install
python3 -m pip install -r requirements.txt
npx serverless deploy --stage dev
```

Salida esperada: stack `itsm-solicitudes-dev` y Outputs `ApiUrl`, `TableName`,
`TableArn`.

> **AWS Academy**: `provider.iam.role` apunta a `LabRole`. Si usas una cuenta
> normal, elimina ese bloque y descomenta `iam.role.statements` al final de
> `serverless.yml`.

## Probar la API

```bash
API=$(aws cloudformation describe-stacks \
  --stack-name itsm-solicitudes-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

ID_TOKEN=$(python3 ../itsm-base/scripts/obtener_token.py \
  --email solicitante.alfa@example.com \
  --password 'Itsm2026!' \
  --stage dev --region us-east-1)

# Crear (usa un servicio que exista en tu Catálogo/mock)
curl -sS -X POST "$API/solicitudes" \
  -H "Authorization: $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"servicio_id":"SVC#000001","titulo":"Acceso VPN","prioridad":"alto"}'

# Listar
curl -sS "$API/solicitudes?limit=10" -H "Authorization: $ID_TOKEN"

# Detalle (el # va como %23)
curl -sS "$API/solicitudes/REQ%23000001" -H "Authorization: $ID_TOKEN"

# Cambiar estado (agente/admin)
curl -sS -X PUT "$API/solicitudes/REQ%23000001/estado" \
  -H "Authorization: $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"estado":"en_proceso","asignado_a":"u-90de"}'

# Historial y resumen
curl -sS "$API/solicitudes/REQ%23000001/historial" -H "Authorization: $ID_TOKEN"
curl -sS "$API/solicitudes/resumen" -H "Authorization: $ID_TOKEN"
```

Usa el **ID token**, no el access token: el access token no incluye
`custom:tenant_id`.

### Adjuntos

```bash
RESP=$(curl -sS -X POST "$API/solicitudes/REQ%23000001/adjuntos" \
  -H "Authorization: $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nombre_archivo":"vpn.pdf","content_type":"application/pdf"}')

UPLOAD_URL=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["upload_url"])')
KEY=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')

curl -sS -X PUT "$UPLOAD_URL" -H "Content-Type: application/pdf" --data-binary @vpn.pdf

curl -sS -X PUT "$API/solicitudes/REQ%23000001/adjuntos" \
  -H "Authorization: $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"$KEY\"}"
```

## Colección Postman

`docs/postman_collection.json` trae las 10 peticiones en orden y sus
aserciones. Importa la colección y define las variables:

| Variable | Valor |
|---|---|
| `baseUrl` | Output `ApiUrl` del stack `itsm-solicitudes-dev` |
| `idToken` | ID token de un usuario de `empresa-alfa` |
| `otroTenantToken` | ID token de un usuario de otro tenant (prueba de aislamiento) |
| `solicitudId` / `solicitudIdEnc` | Se llenan solos al ejecutar “Crear solicitud” |

Orden de ejecución: Crear → Listar → Listar por estado → Detalle → Cambiar
estado → Historial → Resumen → Firmar adjunto → **subir el archivo a S3** →
Confirmar adjunto → Aislamiento.

> **Importante:** entre “Firmar adjunto” y “Confirmar adjunto” debes subir el
> archivo. La colección guarda `adjuntoKey`, pero no puede subir binarios:
> abre la respuesta de “Firmar adjunto”, copia `upload_url` y haz un `PUT` con
> el mismo `Content-Type` (`vpn.pdf`) usando Postman o:
>
> ```bash
> curl -sS -X PUT "<upload_url>" \
>   -H "Content-Type: application/pdf" --data-binary @vpn.pdf
> ```
>
> Si ejecutas “Confirmar adjunto” sin subir el archivo, la API responde `400`
> con `ADJUNTO_NO_ENCONTRADO`.

## Cargar 30,000 solicitudes

```bash
python3 scripts/seed_solicitudes.py --stage dev --region us-east-1
```

- 10,000 por tenant (`empresa-alfa`, `empresa-beta`, `empresa-gamma`).
- IDs `REQ#000001`…`REQ#010000` por tenant.
- Deja `CONTADOR#REQ` en `10000`.
- Los `servicio_id` son placeholders `SVC#000001`…`SVC#000020`. Reemplaza
  `SERVICIOS` en el script cuando el Catálogo real tenga sus IDs.

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```

89 pruebas unitarias sin AWS: SLA, transiciones, roles, aislamiento,
validación, paginación, catálogo caído, adjuntos y serialización.

## Errores

```json
{ "error": { "code": "TRANSICION_INVALIDA", "message": "nueva -> completada" } }
```

| Código | HTTP | Cuándo |
|---|---|---|
| `NO_AUTORIZADO` | 401 | Sin token o sin tenant |
| `SIN_PERMISO` | 403 | Rol insuficiente |
| `VALIDACION` | 400 | Body/query inválido |
| `SERVICIO_INVALIDO` | 400 | Servicio no existe, inactivo o de otro tenant |
| `NO_ENCONTRADO` | 404 | No existe o es de otro tenant |
| `TRANSICION_INVALIDA` | 409 | Cambio no permitido |
| `CONFLICTO` | 409 | Otro usuario cambió el estado |
| `CATALOGO_NO_DISPONIBLE` | 503 | Timeout/5xx del Catálogo |
| `CATALOGO_INVALIDO` | 502 | Respuesta mal formada del Catálogo |

## Notas

- **SLA vencido** se calcula al leer (`sla_vence_en < ahora`), sin tareas
  programadas.
- **Eventos SNS**: `solicitud-creada` y `solicitud-completada`, con
  `MessageAttributes` `tenant_id` y `tipo`. Si SNS falla, la solicitud ya está
  guardada y solo se registra el error.
- **CORS**: `*` para desarrollo. Restríngelo al dominio de Amplify antes de la
  entrega.
- **Tabla**: `DeletionPolicy: Retain`; si haces `serverless remove`, la tabla y
  sus datos quedan en la cuenta.
- **Adjuntos**: el tamaño máximo de 10 MB es una recomendación; con
  `put_object` no se puede imponer en la URL prefirmada. Si necesitas límite
  estricto, cambia a presigned POST con `content-length-range`.
