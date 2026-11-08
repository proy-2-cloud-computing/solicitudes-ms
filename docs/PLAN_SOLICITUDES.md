# Plan del microservicio `itsm-solicitudes`

> Documento de diseño previo a la implementación. Basado en
> `Guia_Proyecto_Final_ITSM_Grupo6.md` (v2.0) y en la tabla DynamoDB
> `ITSM - Solicitudes`.
>
> Stack: **Python 3.12 + Serverless Framework v4 + API Gateway (REST) + Lambda +
> DynamoDB + S3 + SNS**.
>
> **Estado (2026-11-08):** Fases 0–4 implementadas en este repositorio
> (`serverless.yml`, 7 handlers, `common/`, tests, scripts y OpenAPI). La Fase 5
> (deploy, seed de 30k y evidencias) queda pendiente de credenciales AWS. El
> Catálogo está mockeado porque `itsm-catalogo-dev` aún no existe.

---

## 1. Alcance y límites del servicio

`itsm-solicitudes` es dueño de las **solicitudes de servicio**. No es dueño del
catálogo, de los usuarios ni de los adjuntos.

| Responsabilidad | ¿Es del servicio? |
|---|---|
| CRUD de solicitudes | Sí |
| Generar IDs consecutivos `REQ#000001` | Sí |
| Calcular `sla_vence_en` | Sí |
| Guardar historial de estados en la misma tabla | Sí |
| Publicar `solicitud-creada` / `solicitud-completada` | Sí |
| Generar URL prefirmada para subir adjuntos a S3 | Sí |
| Validar que el `servicio_id` exista y esté activo | No: lo consulta al **Catálogo** |
| Conocer el `tenant_id` | No: lo lee del **token de Cognito** |
| Gestionar usuarios/roles | No: **Cognito** |
| Guardar archivos | No: **S3** |
| Entregar eventos a otros servicios | No: **SNS** |

**Regla clave:** la solicitud copia `nombre_servicio`, `sla_horas` y
`requiere_aprobacion` del Catálogo **al crear**. Después de creada, la solicitud
sigue siendo válida aunque el Catálogo esté caído.

---

## 2. Dependencias externas (qué necesito y de quién)

### 2.1 Bloqueantes duros

| Dependencia | Quién la entrega | Qué necesito exactamente | Sin esto no puedo... |
|---|---|---|---|
| `itsm-base` | Integrante 1 | `UserPoolArn` (authorizer) | Proteger los endpoints |
| `itsm-base` | Integrante 1 | `UserPoolId` + `UserPoolClientId` | Obtener ID token para pruebas/Postman |
| `itsm-base` | Integrante 1 | Atributo `custom:tenant_id` + grupos `solicitante`, `agente`, `aprobador`, `admin` | Aislar tenants y autorizar roles |
| `itsm-base` | Integrante 1 | `SolicitudesTopicArn` | Publicar eventos |
| `itsm-base` | Integrante 1 | `AdjuntosBucketName` | URLs prefirmadas |
| `itsm-catalogo` | Integrante 3 | `GET /catalogo/{id}` funcionando y datos sembrados | Validar `servicio_id` y copiar SLA |
| AWS Academy | Docente/equipo | Credenciales y `LabRole` (si aplica) | Desplegar |

### 2.2 Outputs de CloudFormation que deben existir

La guía usa `${cf:itsm-base-dev.SolicitudesTopicArn}`. Ese mecanismo lee los
**Outputs** del stack de CloudFormation (no los `Export`). El extracto de la
guía solo muestra `UserPoolArn` y deja los topics con `# ...`, así que hay que
asegurarse de que existan estos Outputs. Los `Export` son opcionales, pero
útiles si otro stack usa `Fn::ImportValue`:

Hay que pedir que agreguen:

```yaml
# itsm-base/serverless.yml
Outputs:
  UserPoolArn:
    Value: !GetAtt UserPool.Arn
    Export: { Name: itsm-UserPoolArn }
  UserPoolId:
    Value: !Ref UserPool
    Export: { Name: itsm-UserPoolId }
  UserPoolClientId:
    Value: !Ref UserPoolClient
    Export: { Name: itsm-UserPoolClientId }
  SolicitudesTopicArn:
    Value: !Ref SolicitudesTopic
    Export: { Name: itsm-SolicitudesTopicArn }
  AdjuntosBucketName:
    Value: !Ref AdjuntosBucket
    Export: { Name: itsm-AdjuntosBucketName }
```

Y de `itsm-catalogo`:

```yaml
Outputs:
  ApiUrl:
    Value: !Sub "https://${ApiGatewayRestApi}.execute-api.${AWS::Region}.amazonaws.com/${self:provider.stage}"
    Export: { Name: itsm-catalogo-ApiUrl }
```

### 2.3 Contrato que exijo al Catálogo

`GET {CATALOGO_URL}/catalogo/{servicio_id}` con el **mismo** header
`Authorization: <ID token>` del usuario.

Respuesta `200` mínima:

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

Reglas:

- El Catálogo obtiene el tenant del token; nunca de la URL.
- Si `activo == false` o no existe: no se crea la solicitud.
- `#` debe ir URL-encoded: `SVC%23000012`. Si no, el `#` se interpreta como
  fragmento y la llamada llega truncada.

### 2.4 Estrategia para no quedar bloqueado

| Fase | Catálogo | Cómo avanzo |
|---|---|---|
| Local | No existe | Función `get_servicio()` mockeada en tests unitarios |
| Integración temprana | Contrato acordado, sin deploy | `CATALOGO_URL` apuntando a un **Postman Mock Server** con el JSON de arriba |
| Integración real | Desplegado | `${cf:itsm-catalogo-dev.ApiUrl}` |

---

## 3. Modelo de datos DynamoDB

Una sola tabla: `itsm-solicitudes-{stage}`.

- PK: `tenant_id` (String)
- SK: `sk` (String)
- GSI1: `tenant_id` (PK) + `estado_fecha` (SK)
- Billing: `PAY_PER_REQUEST`

### 3.1 Ítem de negocio

```json
{
  "tenant_id": "empresa-beta",
  "sk": "REQ#000870",
  "servicio_id": "SVC#000012",
  "titulo": "Acceso VPN para nuevo analista",
  "descripcion": "Alta de acceso remoto",
  "solicitante_id": "u-33c4",
  "asignado_a": "u-90de",
  "estado": "en_proceso",
  "prioridad": "medio",
  "requiere_aprobacion": true,
  "nombre_servicio": "Acceso VPN",
  "sla_horas": 48,
  "sla_vence_en": "2026-11-13T18:00:00Z",
  "adjuntos": [],
  "creado_en": "2026-11-11T09:30:00Z",
  "actualizado_en": "2026-11-11T10:00:00Z",
  "estado_fecha": "en_proceso#2026-11-11T09:30:00Z"
}
```

Decisiones:

- El atributo canónico es **`sk`**. La API expone además `solicitud_id`
  (mismo valor que `sk`) para que el frontend no tenga que saber que la clave se
  llama `sk`. No se guarda duplicado en DynamoDB.
- `estado_fecha` es **disperso**: solo lo llevan los ítems de negocio. Contador e
  historial no entran al GSI1.
- `estado_fecha` se recalcula en cada cambio de estado usando `creado_en` (no
  `actualizado_en`), para que el orden del listado sea estable.

### 3.2 Contador de IDs

```json
{ "tenant_id": "empresa-beta", "sk": "CONTADOR#REQ", "ultimo_id": 10000 }
```

Incremento atómico:

```python
resp = table.update_item(
    Key={"tenant_id": tenant_id, "sk": "CONTADOR#REQ"},
    UpdateExpression="ADD ultimo_id :one SET actualizado_en = :now",
    ExpressionAttributeValues={":one": 1, ":now": now_iso},
    ReturnValues="UPDATED_NEW",
)
nuevo = int(resp["Attributes"]["ultimo_id"])
sk = f"REQ#{nuevo:06d}"
```

- Se incrementa **después** de validar el catálogo (no se queman IDs si el
  catálogo falla).
- Puede haber huecos si falla la escritura posterior; es aceptable.

### 3.3 Historial

```json
{
  "tenant_id": "empresa-beta",
  "sk": "HIST#REQ#000870#2026-11-11T10:00:00Z#7c1e9a",
  "solicitud_id": "REQ#000870",
  "estado_anterior": "nueva",
  "estado_nuevo": "en_proceso",
  "actor_id": "u-90de",
  "comentario": "Asignado al equipo de redes",
  "evento_id": "7c1e9a",
  "fecha": "2026-11-11T10:00:00Z"
}
```

Se consulta con `begins_with(sk, "HIST#REQ#000870#")`. No necesita GSI.

### 3.4 Patrones de acceso

| Operación | Índice | Expresión |
|---|---|---|
| Crear | tabla | `PutItem` (dentro de transacción con historial) |
| Obtener por ID | tabla | `GetItem(PK=tenant, SK=REQ#...)` |
| Listar todos | tabla | `Query(PK=tenant, begins_with(sk,"REQ#"))` |
| Listar por estado | GSI1 | `Query(PK=tenant, begins_with(estado_fecha,"en_proceso#"))` |
| Contar por estado | GSI1 | `Query(..., Select="COUNT")` |
| Historial | tabla | `Query(PK=tenant, begins_with(sk,"HIST#REQ#..."))` |
| Resumen dashboard | GSI1 | `Select="COUNT"` por cada estado |

Nunca `Scan`.

---

## 4. Contrato de API

Prefijo: `https://<api-id>.execute-api.us-east-1.amazonaws.com/dev`

Todos los endpoints requieren `Authorization: <ID token>` (no access token).
El `tenant_id` **nunca** viaja en el body ni en la ruta.

| Método | Ruta | Rol mínimo | Acción |
|---|---|---|---|
| POST | `/solicitudes` | `solicitante` | Crear |
| GET | `/solicitudes` | cualquiera autenticado | Listar/paginar |
| GET | `/solicitudes/{id}` | cualquiera autenticado | Detalle |
| PUT | `/solicitudes/{id}/estado` | `agente`, `admin` | Cambiar estado / asignar |
| POST | `/solicitudes/{id}/adjuntos` | solicitante dueño o `agente`/`admin` | URL prefirmada |
| GET | `/solicitudes/{id}/historial` | cualquiera autenticado | Historial (opcional, recomendado) |
| GET | `/solicitudes/resumen` | cualquiera autenticado | Contadores por estado (opcional, para dashboard) |

> `{id}` viaja URL-encoded: `REQ%23000870`. API Gateway lo entrega decodificado.

### 4.1 `POST /solicitudes`

Request:

```json
{
  "servicio_id": "SVC#000012",
  "titulo": "Acceso VPN para nuevo analista",
  "descripcion": "Alta de acceso remoto",
  "prioridad": "medio"
}
```

Validaciones:

- `servicio_id` obligatorio y string.
- `titulo` obligatorio, 3–200 caracteres.
- `descripcion` opcional, máx. 2000.
- `prioridad` en `bajo|medio|alto|critico`, default `medio`.

Flujo del handler:

1. Extraer `tenant_id` y `sub` de los claims.
2. Validar body.
3. `GET` al Catálogo con el `Authorization` recibido (timeout 5 s).
4. Si no existe / inactivo → `400`; si falla la red o responde 5xx → `503`.
5. Incrementar contador.
6. Calcular `sla_vence_en = creado_en + sla_horas`.
7. Estado inicial: `en_aprobacion` si `requiere_aprobacion`, si no `nueva`.
8. `TransactWriteItems`: ítem de negocio (`attribute_not_exists(sk)`) + primer
   historial.
9. Publicar `solicitud-creada` (best-effort, se loguea si falla).
10. `201` con el ítem.

Respuesta `201`: el ítem completo + `solicitud_id`.

### 4.2 `GET /solicitudes`

Query params: `estado`, `limit` (1–100, default 25), `next` (token opaco).

- Sin `estado`: `Query` sobre la tabla con `begins_with(sk,"REQ#")`.
- Con `estado`: `Query` sobre GSI1 con `begins_with(estado_fecha,"{estado}#")`.

```json
{
  "items": [ { "...": "..." } ],
  "next": "eyJ0ZW5hbnRfaWQiOi..."
}
```

`next` = base64 de `LastEvaluatedKey`; `null` cuando no hay más.

### 4.3 `GET /solicitudes/{id}`

- `200` con el ítem + `sla_vencido` calculado al leer.
- `404` si no existe **o si pertenece a otro tenant** (mismo código, para no
  filtrar información).

### 4.4 `PUT /solicitudes/{id}/estado`

Request:

```json
{
  "estado": "en_proceso",
  "asignado_a": "u-90de",
  "comentario": "Asignado a redes"
}
```

- Valida transición (ver §5).
- `UpdateItem` con `ConditionExpression: estado = :anterior` (bloqueo
  optimista) y `SET estado, actualizado_en, estado_fecha`, más `asignado_a` si
  viene.
- Escribe historial.
- Si el nuevo estado es `completada`, publica `solicitud-completada`.
- `409` si la transición es inválida o hubo conflicto de concurrencia.

### 4.5 `POST /solicitudes/{id}/adjuntos`

Request:

```json
{ "nombre_archivo": "vpn.pdf", "content_type": "application/pdf" }
```

Respuesta:

```json
{
  "upload_url": "https://...",
  "key": "empresa-beta/solicitudes/REQ-000870/uuid-vpn.pdf",
  "expires_in": 300
}
```

- Verifica primero que la solicitud exista y sea del tenant.
- `key = {tenant_id}/solicitudes/{id_sin_hash}/{uuid4}-{nombre_saneado}`.
- URL prefirmada `put_object`, 300 s, con `ContentType`.
- **Confirmación implementada:** después de subir, el cliente hace
  `PUT /solicitudes/{id}/adjuntos` con `{"key": "..."}`. La Lambda verifica con
  `head_object` que el objeto exista y recién entonces lo agrega a `adjuntos`.
  Así no se guardan claves de archivos que nunca se subieron.

### 4.6 Errores

```json
{ "error": { "code": "TRANSICION_INVALIDA", "message": "nueva -> completada" } }
```

| Código | HTTP | Cuándo |
|---|---|---|
| `NO_AUTORIZADO` | 401 | Sin token o token inválido |
| `SIN_PERMISO` | 403 | Rol insuficiente |
| `VALIDACION` | 400 | Body inválido |
| `SERVICIO_INVALIDO` | 400 | `servicio_id` no existe o inactivo |
| `NO_ENCONTRADO` | 404 | No existe o es de otro tenant |
| `TRANSICION_INVALIDA` | 409 | Cambio de estado no permitido |
| `CATALOGO_NO_DISPONIBLE` | 503 | Timeout/5xx del Catálogo |

---

## 5. Máquina de estados y roles

```
nueva ──────────► en_proceso ─────► completada
  │                   │
  ├──► en_aprobacion ─┤
  │                   │
  └───────────────────┴──► cancelada
```

| Desde | Hacia permitido | Quién |
|---|---|---|
| `nueva` | `en_aprobacion`, `en_proceso`, `cancelada` | agente/admin; el solicitante solo `cancelada` |
| `en_aprobacion` | `en_proceso`, `cancelada` | aprobador/admin |
| `en_proceso` | `completada`, `cancelada` | agente/admin |
| `completada` | — | terminal |
| `cancelada` | — | terminal |

Los grupos se leen de `cognito:groups` y se validan **dentro de la Lambda**.

---

## 6. Integración con el Catálogo

- Variable de entorno `CATALOGO_URL`.
- Llamada con `urllib.request` (stdlib, sin dependencias) o `requests` si se
  agrega `serverless-python-requirements`.
- Reenviar el header `Authorization` tal cual.
- `quote(servicio_id, safe="")` para el `#`.
- Timeout 5 s, un reintento solo para errores de red.
- Mapeo:
  - `200` → usar datos.
  - `404` / `activo=false` → `400 SERVICIO_INVALIDO`.
  - `401/403` → `502` (problema de configuración, no del usuario).
  - timeout / 5xx → `503 CATALOGO_NO_DISPONIBLE`, **sin escribir nada**.

---

## 7. Eventos SNS

Topic: `solicitudes-eventos` (creado en `itsm-base`).

Mensaje (formato de la guía):

```json
{
  "evento_id": "7c1e-...",
  "tipo": "solicitud-creada",
  "tenant_id": "empresa-beta",
  "id": "REQ#000870",
  "estado": "en_aprobacion",
  "actor_id": "u-33c4",
  "fecha": "2026-11-11T09:30:00Z",
  "datos": { "servicio_id": "SVC#000012", "sla_vence_en": "2026-11-13T18:00:00Z" }
}
```

`MessageAttributes`: `tenant_id` y `tipo` (String), para que los consumidores
filtren con `FilterPolicy`.

Eventos publicados:

| Evento | Cuándo |
|---|---|
| `solicitud-creada` | Después del commit en DynamoDB |
| `solicitud-completada` | Al pasar a `completada` |

Nota: si `sns:Publish` falla, la solicitud ya quedó guardada. Para el curso se
loguea el error y se responde `201`; si se quisiera garantía total, se usaría
outbox pattern (fuera de alcance).

---

## 8. Adjuntos S3

- Bucket único de `itsm-base`.
- Prefijo: `{tenant_id}/solicitudes/{id}/`.
- La Lambda solo firma; el navegador sube directo.
- IAM de la Lambda: `s3:PutObject` sobre `arn:aws:s3:::<bucket>/*` (necesario
  para que la URL firmada funcione).
- Validar `content_type` permitido y tamaño máximo (p. ej. 10 MB) con
  `content-length-range` si se usa presigned POST.

---

## 9. Estructura del repositorio

```
itsm-solicitudes/
├── serverless.yml
├── requirements.txt              # vacío o solo dev
├── package.json                  # solo si se usa serverless-python-requirements
├── src/
│   ├── handlers/
│   │   ├── crear.py
│   │   ├── listar.py
│   │   ├── obtener.py
│   │   ├── cambiar_estado.py
│   │   ├── adjuntos.py
│   │   └── historial.py
│   └── common/
│       ├── auth.py               # claims, tenant, grupos
│       ├── db.py                 # tabla, contador, query, paginación
│       ├── catalog.py            # cliente del Catálogo
│       ├── events.py             # SNS publish
│       ├── responses.py          # JSON + CORS + errores
│       ├── validation.py
│       └── timeutils.py
├── scripts/
│   ├── seed_solicitudes.py       # 30,000 registros
│   └── mock_catalogo.py          # mock local para pruebas
├── tests/
│   ├── test_transiciones.py
│   ├── test_sla.py
│   └── test_auth.py
└── docs/
    └── PLAN_SOLICITUDES.md
```

---

## 10. `serverless.yml` (esqueleto)

```yaml
service: itsm-solicitudes
frameworkVersion: '4'

provider:
  name: aws
  runtime: python3.12
  region: us-east-1
  stage: ${opt:stage, 'dev'}
  environment:
    TABLE: ${self:service}-${self:provider.stage}
    TOPIC_ARN: ${cf:itsm-base-${self:provider.stage}.SolicitudesTopicArn}
    BUCKET: ${cf:itsm-base-${self:provider.stage}.AdjuntosBucketName}
    CATALOGO_URL: ${cf:itsm-catalogo-${self:provider.stage}.ApiUrl}
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:UpdateItem
            - dynamodb:Query
            - dynamodb:TransactWriteItems
          Resource:
            - !GetAtt SolicitudesTable.Arn
            - !Sub "${SolicitudesTable.Arn}/index/*"
        - Effect: Allow
          Action: [sns:Publish]
          Resource: ${self:provider.environment.TOPIC_ARN}
        - Effect: Allow
          Action: [s3:PutObject]
          Resource: !Sub "arn:aws:s3:::${self:provider.environment.BUCKET}/*"

functions:
  crear:
    handler: src/handlers/crear.handler
    events:
      - http:
          path: solicitudes
          method: post
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}
  listar:
    handler: src/handlers/listar.handler
    events:
      - http:
          path: solicitudes
          method: get
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}
  obtener:
    handler: src/handlers/obtener.handler
    events:
      - http:
          path: solicitudes/{id}
          method: get
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}
  cambiarEstado:
    handler: src/handlers/cambiar_estado.handler
    events:
      - http:
          path: solicitudes/{id}/estado
          method: put
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}
  adjuntos:
    handler: src/handlers/adjuntos.handler
    events:
      - http:
          path: solicitudes/{id}/adjuntos
          method: post
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}

resources:
  Resources:
    SolicitudesTable:
      Type: AWS::DynamoDB::Table
      Properties:
        TableName: ${self:provider.environment.TABLE}
        BillingMode: PAY_PER_REQUEST
        AttributeDefinitions:
          - { AttributeName: tenant_id,    AttributeType: S }
          - { AttributeName: sk,           AttributeType: S }
          - { AttributeName: estado_fecha, AttributeType: S }
        KeySchema:
          - { AttributeName: tenant_id, KeyType: HASH }
          - { AttributeName: sk,        KeyType: RANGE }
        GlobalSecondaryIndexes:
          - IndexName: GSI1
            KeySchema:
              - { AttributeName: tenant_id,    KeyType: HASH }
              - { AttributeName: estado_fecha, KeyType: RANGE }
            Projection: { ProjectionType: ALL }
```

Notas:

- Se usa **REST API** (`http`) y no `httpApi` para mantener el authorizer de
  Cognito por ARN tal como en la guía. Con `httpApi` habría que configurar
  `issuerUrl`/`audience` y los claims se leen en
  `requestContext.authorizer.jwt.claims`.
- Con REST API los claims están en
  `event.requestContext.authorizer.claims`.
- Si es AWS Academy y se usa `LabRole`, los `iam.statements` no aplican (el rol
  es amplio); igual se documentan.
- Sin dependencias extra no hace falta `serverless-python-requirements`.
  Si se agrega `requests` o `aws-lambda-powertools`, agregar el plugin y
  `requirements.txt`.

---

## 11. Orden de implementación

### Fase 0 — Acuerdos (1–2 días)
- Confirmar outputs de `itsm-base` y contrato del Catálogo.
- Confirmar las decisiones de §14.
- Crear la tabla y el esqueleto del repo.

### Fase 1 — Núcleo sin dependencias (2–3 días)
- `serverless.yml`, `common/`, tabla y GSI.
- `POST /solicitudes` con catálogo **mockeado**.
- Contador atómico, cálculo de SLA, estado inicial.
- `GET /solicitudes` y `GET /solicitudes/{id}`.
- Tests unitarios de SLA, transiciones y aislamiento.

### Fase 2 — Integración real (1–2 días)
- `catalog.py` real + manejo de 400/503.
- Authorizer de Cognito y extracción de claims.
- Prueba con ID token de 2 tenants.

### Fase 3 — Ciclo de vida (2 días)
- `PUT /estado` con transiciones, bloqueo optimista e historial.
- `solicitud-completada`.

### Fase 4 — S3 y SNS (1–2 días)
- URL prefirmada y subida desde el navegador.
- Publicación de eventos y evidencia en CloudWatch.

### Fase 5 — Datos y demo (2 días)
- Script de 30,000 solicitudes (10,000 por tenant).
- Contador en 10,000.
- Colección Postman: crear, listar, cambiar estado, aislamiento (404).

---

## 12. Pruebas y evidencias

| Prueba | Cómo | Resultado esperado |
|---|---|---|
| Crear con catálogo OK | POST con token tenant A | 201, SLA calculado |
| Catálogo caído | `CATALOGO_URL` inválida | 503 y **nada** escrito |
| Catálogo inactivo | servicio con `activo=false` | 400 |
| Aislamiento | token tenant A pide ID de tenant B | 404 |
| Transición inválida | `nueva → completada` | 409 |
| Rol insuficiente | solicitante intenta `PUT /estado` | 403 |
| Adjunto | POST /adjuntos + PUT a la URL | archivo en `{tenant}/solicitudes/...` |
| Evento | crear solicitud | mensaje en SNS/SQS y log |
| Paginación | 30k registros, `limit=25` | `next` funciona |
| Conteo | `GET /resumen` | suma por estado |

Evidencias para el informe: capturas de Postman, logs de CloudWatch, objeto en
S3, mensaje SNS y prueba 404 entre tenants.

---

## 13. Datos ficticios

`scripts/seed_solicitudes.py`:

- 10,000 por tenant × 3 tenants = 30,000.
- `batch_write_item` de 25.
- IDs `REQ#000001` … `REQ#010000` por tenant.
- `servicio_id` tomados de servicios **reales** del Catálogo del mismo tenant
  (leer la tabla del catálogo con boto3 desde el script; el runtime del servicio
  no lo hace).
- Estados y fechas distribuidas; `estado_fecha` coherente.
- `sla_vence_en = creado_en + sla_horas`.
- Al terminar, `CONTADOR#REQ` en `10000`.
- Verificar con `Query(Select="COUNT")` por tenant.

---

## 14. Decisiones tomadas

1. **API type:** REST (`http`) con authorizer de Cognito por ARN. Los claims se
   leen de `event.requestContext.authorizer.claims`.
2. **Estado inicial:** `en_aprobacion` cuando `requiere_aprobacion=true`; si no,
   `nueva`.
3. **Quién aprueba:** `en_aprobacion → en_proceso` lo hacen `aprobador` y
   `admin`; `agente` no.
4. **Adjuntos:** se confirma la subida (`PUT .../adjuntos` con la `key`) antes
   de agregarla a `adjuntos`.
5. **Un Lambda por endpoint**, más `historial` y `resumen` (7 funciones).
6. **Catálogo:** aún no existe. `CATALOGO_URL` es una variable de entorno con
   default `http://localhost:8000` y se usa `scripts/mock_catalogo.py`. Cuando
   exista `itsm-catalogo-dev`, se cambia por su Output `ApiUrl`.
7. **Outputs de `itsm-base`:** `UserPoolArn`, `UserPoolId`, `UserPoolClientId`,
   `SolicitudesTopicArn`, `AdjuntosBucketName` (ya existen en el stack
   desplegado).

---

## 15. Lo que puedo empezar ya vs lo que está bloqueado

| Puedo hacer ya | Bloqueado hasta tener |
|---|---|
| Modelo, `serverless.yml`, tabla, GSI | — |
| Handlers con catálogo mockeado | — |
| Tests unitarios | — |
| Script de seed (estructura) | IDs reales del Catálogo para referencias |
| Deploy con authorizer | `UserPoolArn` |
| Pruebas con token | `UserPoolClientId` + usuarios |
| Crear solicitud end-to-end | `CATALOGO_URL` real o mock |
| Adjuntos | `AdjuntosBucketName` |
| Eventos | `SolicitudesTopicArn` |
