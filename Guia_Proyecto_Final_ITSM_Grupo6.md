# Proyecto Final: Solución SaaS en AWS
## Plataforma ITSM - Gestión de Cambios y Solicitudes de Servicios TI
**Guía de trabajo para el equipo (versión 2.0)**

UTEC - Universidad de Ingeniería y Tecnología

| | |
|---|---|
| **Curso** | CS2032 - Cloud Computing (Ciclo 2026-2) |
| **Grupo / Tipo de SaaS** | Grupo 6 - ITSM (IT Service Management) |
| **Semanas de proyecto** | Semana 11 a 15 (exposición en Semana 16) |
| **Hito ACL (30%)** | Sábado 14-Nov-2026 |
| **Entrega final (Canvas)** | Domingo 22-Nov-2026, 23:59 |
| **Versión de la guía** | 2.0 - incluye dependencias entre servicios, contrato de eventos y preguntas de ejecución |

> Documento de apoyo elaborado a partir del enunciado del proyecto. Las decisiones de diseño (microservicios, modelos de datos, eventos) son propuestas que el equipo puede ajustar.

---

## Índice

1. Resumen del enunciado
2. Arquitectura propuesta
3. Multi-tenancy y seguridad
4. Microservicios
5. Dependencias entre servicios
6. Integración de S3, SNS y SQS
7. Repositorios y despliegue con Serverless Framework
8. Generación de datos ficticios
9. Frontend
10. ¿Qué presentar en el 30% (ACL)?
11. Cronograma sugerido
12. Reparto de trabajo sugerido
13. Preguntas frecuentes y errores comunes
14. Lista de verificación final

---

## 1. Resumen del enunciado

Se debe implementar una solución **SaaS** en AWS para el tipo de plataforma asignado (ITSM: gestión de incidentes, problemas, cambios y solicitudes de servicios TI). Requisitos obligatorios:

| Aspecto | Requisito |
|---|---|
| Bases del diseño | Multi-tenancy, Serverless y Arquitectura basada en eventos (EDA). |
| FrontEnd | Cualquier framework, desplegado obligatoriamente en **AWS Amplify**. |
| BackEnd | Mínimo **5 microservicios serverless protegidos** (API Gateway + Lambda). |
| Base de datos | Cada microservicio con su propia BD. SQL: un único RDS con patrón Single Database, Multiple Schemas. NoSQL: Amazon DynamoDB. |
| Volumen de datos | Mínimo **30,000 registros ficticios por microservicio**, divididos equitativamente en **3 tenants**. |
| Modelado | Por microservicio: Diagrama E-R (SQL) o estructura JSON (NoSQL). |
| Servicios obligatorios | Amazon S3, Amazon SNS y Amazon SQS. |
| Despliegue | Toda la infraestructura automatizada con el framework **Serverless**. |
| Demo presencial | Funcionando con **2 tenants**. |

### Rúbrica (20 puntos)

| Componente | Puntos | Comentario |
|---|---|---|
| Diagrama de Arquitectura de Solución | 2 | Debe mostrar todos los servicios AWS y los flujos. |
| BackEnd | 8 | Microservicios, BD, datos, S3/SNS/SQS, Serverless. |
| FrontEnd | 6 | Desplegado en Amplify, consumiendo las APIs protegidas. |
| Exposición virtual con ACL (avance 30%) | 3 | Hasta el sábado 14-Nov. |
| Exposición presencial | 1 | Semana 16. |

> **Importante:** si un integrante no se presenta a la exposición presencial, su evaluación será desaprobatoria (nota máxima de 10). Todos deben estar en la Semana 16.

### Entregables

- **Informe** (Word o PDF) con la evidencia de todo lo solicitado.
- **Enlaces públicos** a los repositorios del código fuente.
- **Diseño de la base de datos** de cada microservicio.
- **Presentación** (PowerPoint) con el resumen ejecutivo.
- **Demo y exposición** presencial en la Semana 16.

---

## 2. Arquitectura propuesta

Cada microservicio es independiente: tiene su API, sus Lambdas, su tabla DynamoDB y su archivo `serverless.yml`. Los servicios no comparten tablas; se comunican mediante eventos (SNS/SQS) o consultando por ID a través de su API.

```
Cognito (login + tenant_id)
      | JWT
      v
Frontend (Amplify) ---> API Gateway (authorizer Cognito) ---> Lambda Cambios      ---> DynamoDB Cambios
      |                                                  ---> Lambda Solicitudes  ---> DynamoDB Solicitudes
      | URL prefirmada                                   ---> Lambda Incidentes   ---> DynamoDB Incidentes
      v                                                  ---> Lambda Problemas    ---> DynamoDB Problemas
S3 (adjuntos, CSV)                                       ---> Lambda Catálogo     ---> DynamoDB Catálogo

Lambdas --publican evento--> SNS (topics por dominio) --> SQS + DLQ (colas por consumidor) --> Lambdas consumidoras
```

*Figura 1. Esquema general de la solución (versión inicial, base para el diagrama oficial del informe).*

### Decisiones técnicas clave

| Tema | Decisión | Justificación |
|---|---|---|
| Base de datos | DynamoDB (NoSQL) en los 5 servicios, una tabla por servicio. | Evita RDS en VPC y la complejidad de múltiples schemas. Permite aplicar multi-tenancy con `tenant_id` como clave. |
| Multi-tenancy | Modelo pool: tablas compartidas por tenants, aisladas lógicamente por `tenant_id`. | Simple, barato y escalable. El `tenant_id` sale del token, nunca del body. |
| Autenticación | Amazon Cognito con atributo personalizado `tenant_id` y rol. | Los usuarios los gestiona Cognito, por eso no hay microservicio de usuarios. |
| Eventos | SNS (publica) + SQS (consume) + DLQ. | Desacopla servicios (EDA) y permite reintentos. |
| Archivos | S3 con URL prefirmada y carpetas por tenant. | El navegador sube directo, sin pasar por Lambda. |
| Despliegue | Un `serverless.yml` por microservicio y uno base (Cognito, topics, bucket). | Cumple la automatización exigida. |
| Frontend | React o Next.js en Amplify. | Despliegue continuo desde el repositorio. |
| Repositorios | Repositorios en la organización de GitHub del grupo (uno por componente). | Cada servicio se despliega de forma independiente. Deben ser públicos para el entregable. |
| Dependencias | Solo Solicitudes consulta al Catálogo (API). El resto se comunica por referencias de ID y eventos. | Minimiza el acoplamiento (ver sección 5). |

---

## 3. Multi-tenancy y seguridad

Tenants de ejemplo (3 en total; la demo presencial usa 2):

| tenant_id | Descripción ficticia |
|---|---|
| `empresa-alfa` | Empresa de retail con 10,000 registros por servicio |
| `empresa-beta` | Entidad financiera con 10,000 registros por servicio |
| `empresa-gamma` | Operador de telecomunicaciones con 10,000 registros por servicio |

- Cada usuario de Cognito tiene el atributo `custom:tenant_id`.
- API Gateway valida el JWT; la Lambda lee el `tenant_id` de los claims del token.
- Toda consulta a DynamoDB usa `tenant_id` como partition key: un tenant jamás ve datos de otro.
- Roles mediante **grupos de Cognito** (claim `cognito:groups`), validados dentro de la Lambda: **solicitante** (crea solicitudes), **agente** (atiende), **aprobador** (aprueba cambios) y **admin** del tenant.
- El authorizer de Cognito User Pools debe recibir el **ID token**: el access token no incluye `custom:tenant_id`.
- El atributo `custom:tenant_id` se declara en el User Pool desde `itsm-base` (se pueden agregar atributos después, pero no eliminarlos ni cambiar su tipo). El App Client debe tener permiso de **lectura** sobre él para que aparezca en el token y **no** de escritura, para que el usuario no pueda cambiarlo.
- Prueba de aislamiento obligatoria: un usuario del tenant A pide un ID del tenant B y debe recibir 404.
- Los adjuntos en S3 se guardan bajo `{tenant_id}/{servicio}/{id}/archivo`.

> **Regla de oro:** el `tenant_id` nunca se recibe desde el frontend como parámetro de confianza. Siempre se extrae del token.

---

## 4. Microservicios

Patrón de claves común en todas las tablas DynamoDB:

| Elemento | Valor | Uso |
|---|---|---|
| PK (partition key) | `tenant_id` | Aislamiento por tenant. |
| SK (sort key) | Prefijo + ID, ej. `CHG#000123` | Obtener un registro y listar por tenant. |
| GSI1 | PK: `tenant_id` / SK: `estado#fecha_creacion` | Listar por estado ordenado por fecha. |
| Billing | `PAY_PER_REQUEST` | Sin dimensionar capacidad. |
| Contador de IDs | SK `CONTADOR#CHG` (un ítem por tenant y servicio) | Genera el siguiente ID con un UpdateItem ADD atómico. El script de datos lo deja en 10000. |
| Historial | SK `HIST#CHG#000123#fecha` | Auditoría de cambios de estado en la misma tabla (no es un servicio aparte). |
| Listados | Query paginado (Limit + LastEvaluatedKey) | Nunca usar Scan. |
| Conteos y SLA | Query con Select COUNT sobre GSI1. El SLA vencido se calcula al leer (`sla_vence_en` menor que ahora) | Dashboard sin tablas extra ni tareas programadas. |

El GSI1 es **disperso**: solo los ítems de negocio llevan el atributo `estado_fecha` (valor `estado#creado_en`). El contador y el historial no entran al índice. Los 10,000 registros por tenant se cuentan sobre los ítems de negocio; el historial es adicional.

Los 5 servicios siguen este patrón. Las relaciones entre servicios se guardan como **IDs de referencia** (no hay JOIN entre tablas de distintos servicios).

---

### 4.1 Microservicio: Cambios (Change Management)

Gestiona las **solicitudes de cambio (RFC)** sobre la infraestructura y los servicios TI: su registro, evaluación de riesgo, aprobación, programación e implementación. Es uno de los dos ejes de su enfoque.

**Responsabilidades**
- Registrar RFC con tipo (estándar, normal, emergencia), riesgo e impacto.
- Flujo de estados: borrador, en revisión, aprobado/rechazado, programado, implementado, cerrado.
- Guardar plan de implementación, plan de rollback y adjuntos.
- Publicar un evento en cada cambio de estado.

**Modelo de datos (NoSQL / JSON)**

| Atributo | Tipo | Descripción |
|---|---|---|
| `tenant_id` | String (PK) | Identificador del tenant |
| `cambio_id` | String (SK) | CHG#000001 |
| `titulo` / `descripcion` | String | Resumen y detalle del cambio |
| `tipo` | String | estandar \| normal \| emergencia |
| `prioridad` / `riesgo` / `impacto` | String | bajo \| medio \| alto \| critico |
| `estado` | String | borrador \| en_revision \| aprobado \| rechazado \| programado \| implementado \| cerrado |
| `solicitante_id` / `aprobador_id` | String | Usuarios de Cognito (sub) |
| `fecha_inicio_plan` / `fecha_fin_plan` | String (ISO) | Ventana de implementación |
| `plan_implementacion` / `plan_rollback` | String | Pasos y reversión |
| `servicio_afectado` | String | Nombre del servicio o sistema afectado |
| `problema_id` | String (opc.) | Referencia al servicio Problemas |
| `adjuntos` | List | Claves S3 de los archivos |
| `creado_en` / `actualizado_en` | String (ISO) | Auditoría de fechas |

Claves: PK = `tenant_id`, SK = `CHG#NNNNNN`, GSI1 = `tenant_id` + `estado#creado_en`.

**Ejemplo de documento**

```json
{
  "tenant_id": "empresa-alfa",
  "cambio_id": "CHG#000123",
  "titulo": "Actualizar firewall perimetral",
  "tipo": "normal",
  "prioridad": "alto",
  "riesgo": "medio",
  "impacto": "alto",
  "estado": "en_revision",
  "solicitante_id": "u-8f21",
  "aprobador_id": "u-1a77",
  "fecha_inicio_plan": "2026-11-20T22:00:00Z",
  "fecha_fin_plan": "2026-11-21T02:00:00Z",
  "plan_rollback": "Restaurar configuracion v2.3",
  "problema_id": "PRB#000045",
  "adjuntos": ["empresa-alfa/cambios/CHG-000123/plan.pdf"],
  "creado_en": "2026-11-10T14:05:00Z"
}
```

**Endpoints (todos protegidos con authorizer)**

| Método y ruta | Acción |
|---|---|
| `POST /cambios` | Crear un cambio |
| `GET /cambios` | Listar (filtro por estado, paginado) |
| `GET /cambios/{id}` | Ver detalle |
| `PUT /cambios/{id}` | Actualizar datos |
| `POST /cambios/{id}/aprobar` | Aprobar o rechazar (rol aprobador) |
| `POST /cambios/{id}/adjuntos` | Obtener URL prefirmada de S3 |

**Eventos y relaciones**
- **Publica** en SNS: `cambio-creado`, `cambio-aprobado`, `cambio-implementado`.
- **Consume**: ninguno obligatorio.
- **Relaciones:** puede originarse en un Problema: el frontend envía `problema_id` en el POST y Cambios solo guarda la referencia, sin evento ni llamada a Problemas.

---

### 4.2 Microservicio: Solicitudes (Service Requests)

Gestiona las **solicitudes de servicio** de los usuarios (acceso, equipos, software, altas de usuario). Cada solicitud se basa en un ítem del Catálogo de Servicios. Es el segundo eje de su enfoque.

**Responsabilidades**
- Crear solicitudes a partir de un ítem del catálogo.
- Seguir el flujo: nueva, en aprobación, en proceso, completada, cancelada.
- Controlar el vencimiento de SLA según el ítem solicitado.
- Asignar a un agente y permitir adjuntos.

**Modelo de datos (NoSQL / JSON)**

| Atributo | Tipo | Descripción |
|---|---|---|
| `tenant_id` | String (PK) | Identificador del tenant |
| `solicitud_id` | String (SK) | REQ#000001 |
| `servicio_id` | String | Referencia al Catálogo (SVC#...) |
| `titulo` / `descripcion` | String | Detalle de lo que se pide |
| `solicitante_id` / `asignado_a` | String | Usuarios |
| `estado` | String | nueva \| en_aprobacion \| en_proceso \| completada \| cancelada |
| `prioridad` | String | bajo \| medio \| alto \| critico |
| `requiere_aprobacion` | Boolean | Copiado del catálogo al crear |
| `nombre_servicio` / `sla_horas` | String / Number | Copiados del catálogo al crear: la solicitud no depende del Catálogo después |
| `sla_vence_en` | String (ISO) | Fecha límite según SLA |
| `adjuntos` | List | Claves S3 |
| `creado_en` / `actualizado_en` | String (ISO) | Fechas |

Claves: PK = `tenant_id`, SK = `REQ#NNNNNN`, GSI1 = `tenant_id` + `estado#creado_en`.

**Ejemplo de documento**

```json
{
  "tenant_id": "empresa-beta",
  "solicitud_id": "REQ#000870",
  "servicio_id": "SVC#000012",
  "titulo": "Acceso VPN para nuevo analista",
  "solicitante_id": "u-33c4",
  "asignado_a": "u-90de",
  "estado": "en_proceso",
  "prioridad": "medio",
  "nombre_servicio": "Acceso VPN",
  "sla_horas": 48,
  "requiere_aprobacion": true,
  "sla_vence_en": "2026-11-13T18:00:00Z",
  "adjuntos": [],
  "creado_en": "2026-11-11T09:30:00Z"
}
```

**Endpoints (todos protegidos con authorizer)**

| Método y ruta | Acción |
|---|---|
| `POST /solicitudes` | Crear solicitud (el frontend solo envía `servicio_id`; el backend calcula el SLA) |
| `GET /solicitudes` | Listar (filtro por estado) |
| `GET /solicitudes/{id}` | Ver detalle |
| `PUT /solicitudes/{id}/estado` | Cambiar estado / asignar |
| `POST /solicitudes/{id}/adjuntos` | URL prefirmada de S3 |

**Eventos y relaciones**
- **Publica** en SNS: `solicitud-creada`, `solicitud-completada`.
- **Consume**: ninguno obligatorio (opcional: avisos de cambios de SLA).
- **Relaciones:** al crear, consulta el Catálogo por API reenviando el JWT del usuario y copia SLA y aprobación a la solicitud. Es la única dependencia por consulta del proyecto.

---

### 4.3 Microservicio: Incidentes (Incident Management)

Registra y gestiona las **interrupciones o degradaciones** de un servicio TI, con prioridad calculada a partir de urgencia e impacto, y control de SLA.

**Responsabilidades**
- Reportar incidentes con categoría, urgencia e impacto.
- Flujo: nuevo, asignado, en progreso, resuelto, cerrado.
- Control de SLA y escalamiento de incidentes críticos.
- Vincular el incidente con un Problema cuando se repite.

**Modelo de datos (NoSQL / JSON)**

| Atributo | Tipo | Descripción |
|---|---|---|
| `tenant_id` | String (PK) | Identificador del tenant |
| `incidente_id` | String (SK) | INC#000001 |
| `titulo` / `descripcion` | String | Qué ocurre |
| `categoria` | String | red \| hardware \| software \| acceso \| otro |
| `urgencia` / `impacto` / `prioridad` | String | P1 a P4 calculada |
| `estado` | String | nuevo \| asignado \| en_progreso \| resuelto \| cerrado |
| `reportado_por` / `asignado_a` | String | Usuarios |
| `servicio_afectado` | String | Servicio o sistema impactado |
| `sla_vence_en` | String (ISO) | Límite de resolución |
| `solucion` | String | Descripción de la resolución |
| `problema_id` | String (opc.) | Referencia a Problemas |
| `adjuntos` / `creado_en` / `actualizado_en` | List / ISO | Evidencias y fechas |

Claves: PK = `tenant_id`, SK = `INC#NNNNNN`, GSI1 = `tenant_id` + `estado#creado_en`.

**Ejemplo de documento**

```json
{
  "tenant_id": "empresa-gamma",
  "incidente_id": "INC#004512",
  "titulo": "Caida del servicio de correo",
  "categoria": "software",
  "urgencia": "alta",
  "impacto": "alto",
  "prioridad": "P1",
  "estado": "en_progreso",
  "reportado_por": "u-5b12",
  "asignado_a": "u-72aa",
  "servicio_afectado": "Correo corporativo",
  "sla_vence_en": "2026-11-12T12:00:00Z",
  "problema_id": null,
  "creado_en": "2026-11-12T08:10:00Z"
}
```

**Endpoints (todos protegidos con authorizer)**

| Método y ruta | Acción |
|---|---|
| `POST /incidentes` | Reportar incidente |
| `GET /incidentes` | Listar (por estado / prioridad) |
| `GET /incidentes/{id}` | Ver detalle |
| `PUT /incidentes/{id}` | Actualizar / resolver |
| `POST /incidentes/{id}/adjuntos` | URL prefirmada de S3 |

**Eventos y relaciones**
- **Publica** en SNS: `incidente-creado`, `incidente-critico`, `incidente-resuelto`.
- **Consume**: `problema-resuelto`, que trae la lista de incidentes vinculados, para cerrarlos (flujo final).
- **Relaciones:** puede estar asociado a un Problema (`problema_id`).

---

### 4.4 Microservicio: Problemas (Problem Management)

Investiga la **causa raíz** de incidentes recurrentes o graves para evitar que se repitan. Registra soluciones temporales (workaround) y errores conocidos, y puede originar un Cambio.

**Responsabilidades**
- Crear un problema a partir de uno o varios incidentes.
- Registrar causa raíz, workaround y estado de análisis.
- Flujo: identificado, en análisis, error conocido, resuelto, cerrado.
- Solicitar un Cambio para la solución definitiva.

**Modelo de datos (NoSQL / JSON)**

| Atributo | Tipo | Descripción |
|---|---|---|
| `tenant_id` | String (PK) | Identificador del tenant |
| `problema_id` | String (SK) | PRB#000001 |
| `titulo` / `descripcion` | String | Resumen del problema |
| `estado` | String | identificado \| en_analisis \| error_conocido \| resuelto \| cerrado |
| `prioridad` | String | bajo \| medio \| alto \| critico |
| `causa_raiz` | String | Resultado del análisis |
| `workaround` | String | Solución temporal |
| `incidentes_relacionados` | List | IDs INC# asociados |
| `cambio_id` | String (opc.) | Cambio que resuelve el problema |
| `responsable` | String | Usuario a cargo |
| `creado_en` / `actualizado_en` | String (ISO) | Fechas |

Claves: PK = `tenant_id`, SK = `PRB#NNNNNN`, GSI1 = `tenant_id` + `estado#creado_en`.

**Ejemplo de documento**

```json
{
  "tenant_id": "empresa-alfa",
  "problema_id": "PRB#000045",
  "titulo": "Caidas recurrentes del firewall",
  "estado": "error_conocido",
  "prioridad": "alto",
  "causa_raiz": "Firmware con fuga de memoria",
  "workaround": "Reinicio programado cada 24 h",
  "incidentes_relacionados": ["INC#003901", "INC#003955"],
  "cambio_id": "CHG#000123",
  "responsable": "u-1a77",
  "creado_en": "2026-11-05T10:00:00Z"
}
```

**Endpoints (todos protegidos con authorizer)**

| Método y ruta | Acción |
|---|---|
| `POST /problemas` | Crear problema |
| `GET /problemas` | Listar |
| `GET /problemas/{id}` | Ver detalle |
| `PUT /problemas/{id}` | Actualizar causa raíz / estado |
| `POST /problemas/{id}/incidentes` | Asociar incidentes |

**Eventos y relaciones**
- **Publica** en SNS: `problema-creado`, `problema-resuelto`.
- **Consume**: ninguno obligatorio. Opcional (extra): `cambio-implementado` para marcar el problema como resuelto.
- **Relaciones:** agrupa Incidentes por referencia (`incidentes_relacionados`). El `cambio_id` se guarda por referencia con `PUT /problemas/{id}`, enviado por el frontend.

---

### 4.5 Microservicio: Catálogo de Servicios (Service Catalog)

Define los **servicios que los usuarios pueden solicitar**, con su descripción, SLA, responsable y si requieren aprobación. Alimenta directamente al servicio de Solicitudes, por lo que encaja con su enfoque.

**Responsabilidades**
- Mantener el listado de servicios disponibles por tenant.
- Definir SLA (horas), costo estimado y equipo responsable.
- Indicar si el servicio requiere aprobación.
- Activar o desactivar servicios.

**Modelo de datos (NoSQL / JSON)**

| Atributo | Tipo | Descripción |
|---|---|---|
| `tenant_id` | String (PK) | Identificador del tenant |
| `servicio_id` | String (SK) | SVC#000001 |
| `nombre` / `descripcion` | String | Qué ofrece el servicio |
| `categoria` | String | acceso \| hardware \| software \| soporte \| otro |
| `sla_horas` | Number | Tiempo objetivo de atención |
| `requiere_aprobacion` | Boolean | Si pasa por aprobación |
| `equipo_responsable` | String | Grupo que lo atiende |
| `costo_estimado` | Number | Costo referencial |
| `activo` | Boolean | Disponible para solicitar |
| `estado` | String | activo \| inactivo (para GSI1) |
| `creado_en` / `actualizado_en` | String (ISO) | Fechas |

Claves: PK = `tenant_id`, SK = `SVC#NNNNNN`, GSI1 = `tenant_id` + `estado#creado_en`.

**Ejemplo de documento**

```json
{
  "tenant_id": "empresa-beta",
  "servicio_id": "SVC#000012",
  "nombre": "Acceso VPN",
  "descripcion": "Alta de acceso remoto por VPN",
  "categoria": "acceso",
  "sla_horas": 48,
  "requiere_aprobacion": true,
  "equipo_responsable": "Redes",
  "costo_estimado": 0,
  "activo": true,
  "estado": "activo",
  "creado_en": "2026-10-01T08:00:00Z"
}
```

**Endpoints (todos protegidos con authorizer)**

| Método y ruta | Acción |
|---|---|
| `POST /catalogo` | Crear servicio |
| `GET /catalogo` | Listar servicios activos |
| `GET /catalogo/{id}` | Ver detalle |
| `PUT /catalogo/{id}` | Actualizar / desactivar |

**Eventos y relaciones**
- **Publica** en SNS: `servicio-actualizado` (opcional).
- **Consume**: ninguno.
- **Relaciones:** Solicitudes lo consulta por `servicio_id` (vía API).

> **Alternativa para el quinto servicio:** si el equipo prefiere otro enfoque, el quinto microservicio puede ser **Activos (CMDB)**: servidores, equipos y software afectados por cambios e incidentes. Se mantiene la misma estructura de claves y el mismo patrón de eventos. La decisión debe tomarse y justificarse antes del 3-Nov.

---

## 5. Dependencias entre servicios

Los servicios son independientes: no comparten tablas y solo tienen **una** dependencia por consulta. El resto de la relación es por IDs de referencia y eventos.

### 5.1 Mapa de dependencias

| Servicio | Consulta a (API) | Publica | Consume | Depende de |
|---|---|---|---|---|
| Cambios | - | cambio-creado, cambio-aprobado, cambio-implementado | - | Nadie |
| Solicitudes | **Catálogo** (al crear) | solicitud-creada, solicitud-completada | - | Catálogo |
| Incidentes | - | incidente-creado, incidente-critico, incidente-resuelto | problema-resuelto | Evento de Problemas |
| Problemas | - | problema-creado, problema-resuelto | (extra) cambio-implementado | Nadie |
| Catálogo | - | (opcional) servicio-actualizado | - | Nadie |

### 5.2 Referencias por ID (sin llamadas entre servicios)

| Campo | Está en | Apunta a | Cómo se llena |
|---|---|---|---|
| `servicio_id` | Solicitudes | Catálogo | Lo envía el frontend; el backend lo valida consultando al Catálogo. |
| `problema_id` | Cambios | Problemas | El frontend lo envía al crear el cambio desde un problema. Solo se guarda. |
| `problema_id` | Incidentes | Problemas | El frontend lo actualiza con `PUT /incidentes/{id}` al vincular. |
| `incidentes_relacionados` | Problemas | Incidentes | `POST /problemas/{id}/incidentes` (lista de IDs INC#). |
| `cambio_id` | Problemas | Cambios | El frontend lo actualiza con `PUT /problemas/{id}`. |

Estas referencias no se validan contra el otro servicio en tiempo real, pero **siempre** se consultan filtradas por el `tenant_id` del token.

### 5.3 Contrato de eventos

| Evento | Topic (en itsm-base) | Publica | Consume | Fase |
|---|---|---|---|---|
| cambio-creado | cambios-eventos | Cambios | notificaciones, auditoría | Hito 30% |
| cambio-aprobado | cambios-eventos | Cambios | notificaciones, auditoría | Hito 30% |
| cambio-implementado | cambios-eventos | Cambios | auditoría; (extra) Problemas | Final |
| solicitud-creada | solicitudes-eventos | Solicitudes | notificaciones | Final |
| incidente-critico | incidentes-eventos | Incidentes | notificaciones | Final |
| problema-resuelto | problemas-eventos | Problemas | Incidentes (cierra los vinculados) | Final |

**Formato mínimo del mensaje (el mismo para todos los eventos):**

```
{
  "evento_id": "7c1e-...",            # unico, sirve para idempotencia
  "tipo": "problema-resuelto",
  "tenant_id": "empresa-alfa",
  "id": "PRB#000045",
  "estado": "resuelto",
  "actor_id": "u-1a77",
  "fecha": "2026-11-18T16:20:00Z",
  "datos": { "incidentes_relacionados": ["INC#003901", "INC#003955"] }
}
# MessageAttributes de SNS: tenant_id y tipo (para filtrar suscripciones)
```

- Todo consumidor usa el `tenant_id` del mensaje en **cada** lectura y escritura a DynamoDB.
- SQS entrega al menos una vez, así que un mensaje puede llegar repetido: los consumidores deben ser **idempotentes** (por ejemplo, usar `evento_id` como parte de la clave del historial, con escritura condicional).
- Un mensaje que falla 3 veces pasa a la DLQ; muestren ese caso en la demo.

### 5.4 Cadena de eventos opcional (extra)

```
Se implementa un cambio              -> Cambios publica cambio-implementado
  Problemas lo recibe (extra)        -> marca el problema como resuelto y publica problema-resuelto
    Incidentes lo recibe (final)     -> cierra los incidentes vinculados
```

Solo la segunda parte (`problema-resuelto` a Incidentes) está en el alcance final. La primera (`cambio-implementado` a Problemas) es un extra: háganla si sobra tiempo, porque demuestra bien la arquitectura basada en eventos. No entra en el hito del 30%.

### 5.5 Reglas para no complicarse

- Ninguna tabla se comparte entre servicios; solo se guardan IDs de referencia.
- Solicitudes copia `sla_horas` y `requiere_aprobacion` al crear: si el Catálogo falla después, la solicitud sigue siendo válida.
- Si el Catálogo no responde al crear una solicitud, se devuelve un error claro (503) y no se guarda nada.
- Eviten cadenas largas de llamadas síncronas entre servicios; prefieran eventos.
- El frontend orquesta las acciones que tocan dos servicios (por ejemplo, vincular un incidente a un problema hace dos llamadas).

### 5.6 Orden de despliegue

| Orden | Repositorio | Motivo |
|---|---|---|
| 1 | `itsm-base` | Crea Cognito, bucket S3 y topics SNS; exporta sus ARN como Outputs. |
| 2 | `itsm-catalogo` | Solicitudes necesita su URL. |
| 3 | `itsm-solicitudes` | Usa la URL del Catálogo como variable de entorno. |
| 4 | `itsm-cambios` | Independiente; ya tiene el topic disponible. |
| 5 | `itsm-incidentes` | Consume `problema-resuelto`; el topic ya existe desde itsm-base. |
| 6 | `itsm-problemas` | Independiente. |
| 7 | `itsm-frontend` | Necesita las 5 URLs base como variables de entorno en Amplify. |

---

## 6. Integración de S3, SNS y SQS

| Servicio | Rol en el proyecto | Detalle |
|---|---|---|
| **S3** | Adjuntos y carga masiva | Un bucket (creado en itsm-base) con carpetas por tenant. La Lambda genera una URL prefirmada y el navegador sube directo. Un CSV subido a un prefijo `carga/` puede disparar una Lambda que inserta datos en DynamoDB. |
| **SNS** | Publicar eventos de dominio | Un topic por dominio, **todos creados en itsm-base**: `cambios-eventos`, `solicitudes-eventos`, `incidentes-eventos`, `problemas-eventos`. Así los consumidores no dependen del orden de despliegue de los publicadores. El tipo de evento va como atributo del mensaje. |
| **SQS** | Procesar de forma asíncrona | Cada servicio consumidor define en su propio `serverless.yml` su cola, su DLQ y su suscripción al topic (con filtro por `tipo`). Las Lambdas consumen con trigger SQS. |

### Flujo de ejemplo para el hito del 30%

```
Usuario crea un cambio (API Gateway -> Lambda Cambios)
      | guarda en DynamoDB (+ historial) y publica el evento
      v
SNS topic "cambios-eventos"  (tipo = cambio-creado)
      |--> SQS "notificaciones" --> Lambda: avisa a los aprobadores
      '--> SQS "auditoria"      --> Lambda: guarda el historial del cambio
```

- El servicio Cambios no conoce a los consumidores: solo publica el evento (principio de EDA).
- Si una Lambda falla, SQS reintenta y, tras 3 intentos, envía el mensaje a la **DLQ**.
- Para la demo, muestren el mensaje llegando a la cola y procesándose en CloudWatch.
- Las suscripciones por correo de SNS requieren confirmación manual: suscriban el correo del equipo con anticipación.

---

## 7. Repositorios y despliegue con Serverless Framework

Los repositorios ya están creados en la **organización de GitHub** del grupo. Esta es la correspondencia sugerida (ajusten los nombres a los reales):

```
itsm-base/            # Cognito (User Pool, grupos, App Client), bucket S3, topics SNS
itsm-catalogo/        # serverless.yml + handlers + tabla DynamoDB
itsm-solicitudes/
itsm-cambios/
itsm-incidentes/
itsm-problemas/
itsm-frontend/        # React/Next.js desplegado en Amplify
scripts-datos/        # generador de 30,000 registros por servicio (puede ir en itsm-base)
```

- El enunciado pide **enlaces públicos**: verifiquen que cada repositorio de la organización tenga visibilidad pública antes de entregar.
- Para conectar Amplify a un repositorio de la organización, el dueño de la organización debe autorizar la aplicación de GitHub de Amplify.
- Cada integrante trabaja en ramas y abre pull requests hacia `main`; el despliegue se hace desde `main`.

### Primero, `itsm-base` (extracto referencial)

```yaml
service: itsm-base
frameworkVersion: '4'
provider: { name: aws, region: us-east-1, stage: "${opt:stage, 'dev'}" }
resources:
  Resources:
    UserPool:
      Type: AWS::Cognito::UserPool
      Properties:
        UserPoolName: itsm-${self:provider.stage}
        UsernameAttributes: [email]
        Schema:
          - { Name: tenant_id, AttributeDataType: String, Mutable: true }
    UserPoolClient:
      Type: AWS::Cognito::UserPoolClient
      Properties:
        UserPoolId: !Ref UserPool
        ExplicitAuthFlows: [ALLOW_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH]
        ReadAttributes: [email, custom:tenant_id]     # sin permiso de escritura
    CambiosTopic:      { Type: AWS::SNS::Topic }
    SolicitudesTopic:  { Type: AWS::SNS::Topic }
    IncidentesTopic:   { Type: AWS::SNS::Topic }
    ProblemasTopic:    { Type: AWS::SNS::Topic }
    AdjuntosBucket:    { Type: AWS::S3::Bucket }
    # + AWS::Cognito::UserPoolGroup para solicitante, agente, aprobador, admin
  Outputs:
    UserPoolArn:      { Value: !GetAtt UserPool.Arn,  Export: { Name: itsm-UserPoolArn } }
    CambiosTopicArn:  { Value: !Ref CambiosTopic }
    # ... un Output por topic y uno para el bucket
```

### Después, un microservicio, por ejemplo `itsm-cambios` (parte 1: provider y funciones)

```yaml
service: itsm-cambios
frameworkVersion: '4'
provider:
  name: aws
  runtime: nodejs20.x
  region: us-east-1
  stage: ${opt:stage, 'dev'}
  # Si usan AWS Academy / Learner Lab, usar el rol existente (ver seccion 13):
  #   iam: { role: "arn:aws:iam::<ID_CUENTA>:role/LabRole" }
  environment:
    TABLE: ${self:service}-${self:provider.stage}
    TOPIC_ARN: ${cf:itsm-base-${self:provider.stage}.CambiosTopicArn}
  iam:
    role:
      statements:
        - Effect: Allow
          Action: [dynamodb:Query, dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem]
          Resource:
            - !GetAtt CambiosTable.Arn
            - !Sub "${CambiosTable.Arn}/index/*"
        - Effect: Allow
          Action: sns:Publish
          Resource: ${self:provider.environment.TOPIC_ARN}
functions:
  crear:
    handler: src/crear.handler
    events:
      - http:
          path: cambios
          method: post
          cors: true
          authorizer:
            name: cognitoAuth
            arn: ${cf:itsm-base-${self:provider.stage}.UserPoolArn}
  listar:
    handler: src/listar.handler
    events:
      - http: { path: cambios, method: get, cors: true,
                authorizer: { name: cognitoAuth, arn: "${cf:itsm-base-${self:provider.stage}.UserPoolArn}" } }
  auditoria:
    handler: src/auditoria.handler
    events:
      - sqs:
          arn: !GetAtt AuditoriaQueue.Arn
```

### Parte 2: recursos propios del servicio (tabla, cola, DLQ y suscripción al topic de itsm-base)

```yaml
resources:
  Resources:
    CambiosTable:
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
          - { AttributeName: sk,        KeyType: RANGE }      # CHG#000123, CONTADOR#CHG, HIST#...
        GlobalSecondaryIndexes:
          - IndexName: GSI1
            KeySchema:
              - { AttributeName: tenant_id,    KeyType: HASH }
              - { AttributeName: estado_fecha, KeyType: RANGE }
            Projection: { ProjectionType: ALL }
    AuditoriaDLQ:
      Type: AWS::SQS::Queue
    AuditoriaQueue:
      Type: AWS::SQS::Queue
      Properties:
        RedrivePolicy: { deadLetterTargetArn: !GetAtt AuditoriaDLQ.Arn, maxReceiveCount: 3 }
    AuditoriaSubscription:
      Type: AWS::SNS::Subscription
      Properties:
        TopicArn: ${self:provider.environment.TOPIC_ARN}
        Protocol: sqs
        Endpoint: !GetAtt AuditoriaQueue.Arn
        RawMessageDelivery: true
        FilterPolicyScope: MessageAttributes
        FilterPolicy: { tipo: [cambio-creado, cambio-aprobado, cambio-implementado] }
    AuditoriaQueuePolicy:
      Type: AWS::SQS::QueuePolicy
      Properties:
        Queues: [!Ref AuditoriaQueue]
        PolicyDocument:
          Statement:
            - Effect: Allow
              Principal: { Service: sns.amazonaws.com }
              Action: sqs:SendMessage
              Resource: !GetAtt AuditoriaQueue.Arn
              Condition:
                ArnEquals: { "aws:SourceArn": "${self:provider.environment.TOPIC_ARN}" }
```

**Notas:**
1. El authorizer se declara en cada servicio con el ARN del User Pool, porque un authorizer de API Gateway pertenece a una sola API y no se comparte entre servicios.
2. La clave de ordenamiento se llama `sk` y guarda el prefijo + ID (`CHG#000123`).
3. Es un esqueleto referencial: revisen versiones, región y nombres antes de desplegar.

---

## 8. Generación de datos ficticios

| Servicio | Por tenant | Tenants | Total |
|---|---|---|---|
| Cambios | 10,000 | 3 | 30,000 |
| Solicitudes | 10,000 | 3 | 30,000 |
| Incidentes | 10,000 | 3 | 30,000 |
| Problemas | 10,000 | 3 | 30,000 |
| Catálogo de Servicios | 10,000 | 3 | 30,000 |
| **Total del proyecto** | | | **150,000** |

- Escriban un script (Python con `boto3` y `Faker`, o Node.js) que use `batch_write_item` (25 ítems por lote).
- Generen IDs consecutivos por tenant (CHG#000001 a CHG#010000), fechas distribuidas y estados variados.
- Mantengan coherencia entre servicios: las solicitudes deben referenciar `servicio_id` existentes en el catálogo, y los problemas, incidentes existentes.
- Alternativa: generar un CSV, subirlo a S3 y procesarlo con una Lambda (demuestra el uso de S3).
- Dejen el ítem `CONTADOR#...` de cada tenant en 10000 al terminar la carga, para que los nuevos registros continúen la numeración.
- Para el hito, carguen primero un **catálogo mínimo** (unos 20 servicios por tenant) que ya permita crear solicitudes; el resto hasta 10,000 por tenant se genera después variando nombres y categorías (el enunciado exige 30,000 por microservicio).
- Verifiquen los conteos con una consulta por tenant antes de la demo.

---

## 9. Frontend (6 puntos)

| Pantalla | Contenido | Prioridad |
|---|---|---|
| Login / registro | Cognito, con selección o asignación de tenant | Hito 30% |
| Dashboard | Contadores por estado, incidentes críticos, cambios pendientes | Final |
| Cambios | Listado, crear, ver detalle, aprobar, subir adjuntos | Hito 30% |
| Solicitudes | Elegir servicio del catálogo, crear y seguir estado | Hito 30% |
| Incidentes | Reportar, listar, resolver | Final |
| Problemas | Crear, asociar incidentes, registrar causa raíz | Final |
| Catálogo | Gestión de servicios (rol admin) | Final |

- Desplegar en Amplify conectando el repositorio (despliegue continuo).
- Guardar las 5 URLs base de las APIs como variables de entorno de Amplify (no escribirlas en el código).
- Enviar siempre el **ID token** en el header Authorization.
- Crear un cambio desde un problema: el frontend abre el formulario de cambios enviando el `problema_id` (referencia, sin eventos).
- Mostrar el nombre del tenant en la barra superior para evidenciar la multi-tenancy.
- Para la demo, preparar usuarios de 2 tenants y mostrar que los datos no se mezclan.

---

## 10. ¿Qué presentar en el 30% (ACL, sábado 14-Nov)?

Recomendación: entregar un **corte vertical funcional** de punta a punta, en lugar de varias piezas a medias. Con esto se demuestra que multi-tenancy, serverless, seguridad y eventos ya funcionan; los demás microservicios son replicar el patrón.

| # | Entregable para el hito | Evidencia a mostrar |
|---|---|---|
| 1 | Diagrama de arquitectura (versión inicial) | Imagen con servicios y flujos |
| 2 | Repositorios creados con la estructura de los 5 servicios | Enlaces de GitHub |
| 3 | Autenticación multi-tenant | Login con Cognito y `tenant_id` en el token |
| 4 | **Cambios** y **Solicitudes** completos | CRUD protegido: API Gateway + Lambda + DynamoDB |
| 5 | **Catálogo mínimo** (lo necesita Solicitudes) | `GET /catalogo` con datos y creación de una solicitud que lo consulta |
| 6 | Datos cargados en Cambios y Solicitudes | 30,000 registros c/u, 10,000 por tenant |
| 7 | Un flujo de eventos real | Crear cambio, SNS, SQS y Lambda consumidora (con DLQ) |
| 8 | Subida de un adjunto a S3 | Archivo bajo la carpeta del tenant |
| 9 | Frontend mínimo en Amplify | Login, listado y creación de cambios y solicitudes |
| 10 | Prueba de aislamiento entre tenants | Un ID de otro tenant devuelve 404 |
| 11 | Diseño de BD (JSON) de los servicios construidos | Incluido en el informe |

Con este alcance cubren aproximadamente un 30% del proyecto: la infraestructura base, 2 de 5 microservicios completos más un Catálogo mínimo, los 3 servicios obligatorios (S3, SNS, SQS) y el frontend inicial.

---

## 11. Cronograma sugerido

| Fecha | Meta |
|---|---|
| Hasta 3-Nov | Definir microservicios, diagrama inicial, repositorios, `itsm-base` (Cognito, S3, SNS) y diseño de tablas. |
| Hasta 10-Nov | Catálogo mínimo, microservicios Cambios y Solicitudes, carga de datos, flujo SNS/SQS y prueba de aislamiento. |
| 11 al 13-Nov | Frontend básico en Amplify y ensayo de la demo. |
| 14-Nov | **Exposición virtual con ACL (30%)**. |
| 15 al 21-Nov | Incidentes, Problemas y Catálogo; frontend completo; informe y PPT. |
| 22-Nov, 23:59 | **Entrega en Canvas**: informe, repos, diseño de BD y presentación. |
| Semana 16 | Exposición presencial con demo de 2 tenants (asistencia de todos). |

---

## 12. Reparto de trabajo sugerido (5 integrantes)

| Rol | Responsabilidad principal |
|---|---|
| Integrante 1 | `itsm-base`: Cognito (User Pool, grupos), bucket S3, topics SNS; permisos de la organización de GitHub y conexión con Amplify. |
| Integrante 2 | Microservicio Cambios + flujo de eventos y adjuntos. |
| Integrante 3 | Catálogo primero (lo necesita Solicitudes) y luego Solicitudes. |
| Integrante 4 | Microservicios Incidentes y Problemas. |
| Integrante 5 | Frontend + script de datos ficticios. |
| Todos | Informe, diagramas, PPT y ensayo de la demo. |

---

## 13. Preguntas frecuentes y errores comunes

| Pregunta | Respuesta |
|---|---|
| ¿Cómo consulta Solicitudes al Catálogo si ambos están protegidos? | Reenvía el JWT del usuario en el header Authorization. La URL del Catálogo va en una variable de entorno tomada de los Outputs de CloudFormation. |
| ¿Quién decide el SLA? | El backend. El frontend solo envía `servicio_id`; si enviara el SLA, podría falsearse. |
| ¿Dónde se crean los topics SNS? | Todos en `itsm-base`. Las colas y suscripciones van en el servicio consumidor. |
| ¿Cómo se evita mezclar tenants en un consumidor? | El mensaje lleva `tenant_id` y el consumidor lo usa en cada escritura. Nunca se asume el tenant. |
| ¿Cómo se generan IDs consecutivos sin duplicados? | Con el ítem `CONTADOR#...` por tenant y un UpdateItem ADD atómico. |
| ¿Dónde se guarda el historial? | En la misma tabla del servicio, con SK `HIST#...`. No es un servicio aparte. |
| ¿Cómo se listan 10,000 registros? | Con Query paginado (Limit y LastEvaluatedKey). Nunca con Scan. |
| ¿Cómo se calculan los contadores del dashboard? | Query con Select COUNT por estado sobre el GSI1. |
| ¿Quién marca una solicitud como SLA vencido? | Se calcula al leer: `sla_vence_en` menor que la fecha actual. Evita tareas programadas. |
| ¿Qué token usa el authorizer? | El **ID token**. Trae `custom:tenant_id` y `cognito:groups`; el access token no trae el tenant. |
| ¿Cómo se restringe quién aprueba un cambio? | Con grupos de Cognito, validados dentro de la Lambda (`aprobador` o `admin`). |
| ¿Por qué el frontend recibe errores CORS? | Falta `cors: true` en algún endpoint, o la Lambda no devuelve `Access-Control-Allow-Origin` en sus respuestas (también en los errores). |
| ¿Y los permisos IAM? | Si usan AWS Academy / Learner Lab, normalmente no se pueden crear roles y hay que usar el `LabRole` existente. Confirmen con el docente si aplica a su curso. |
| ¿Cómo se prueba sin romper la demo? | Stage `dev`, usuarios de prueba en 2 tenants y Postman con el ID token. Prueba de aislamiento: pedir un ID del otro tenant debe dar 404. |
| ¿Qué pasa si SQS entrega un mensaje dos veces? | El consumidor debe ser idempotente: usa `evento_id` en una escritura condicional. |
| ¿Qué pasa si el consumidor falla? | SQS reintenta 3 veces y envía el mensaje a la DLQ. Muéstrenlo en la demo. |
| ¿Cómo se ven las notificaciones? | Correo suscrito a SNS (confirmación manual previa) y registros en CloudWatch Logs como evidencia. |

---

## 14. Lista de verificación final

- [ ] 5 microservicios con API Gateway + Lambda protegidos por Cognito.
- [ ] Una tabla DynamoDB por microservicio, con 30,000 registros (10,000 por tenant).
- [ ] Estructura JSON de cada tabla documentada en el informe.
- [ ] S3, SNS y SQS (con DLQ) funcionando y evidenciados; topics en itsm-base.
- [ ] Mensajes con `tenant_id` y consumidores idempotentes.
- [ ] Prueba de aislamiento entre tenants documentada (404 al pedir un ID de otro tenant).
- [ ] Repositorios de la organización de GitHub en visibilidad pública.
- [ ] CORS habilitado y URLs base configuradas en Amplify.
- [ ] Todo desplegado con Serverless Framework; frontend en Amplify.
- [ ] Diagrama de arquitectura completo (versión final).
- [ ] Informe, repositorios públicos, diseño de BD y PPT subidos a Canvas antes del 22-Nov, 23:59; demo con 2 tenants y todos presentes en la Semana 16.
