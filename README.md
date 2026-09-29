# 🚀 HabiCapital P2P — Plataforma Transaccional P2P

> **"El sistema no puede perder un peso": Arquitectura de Partida Doble, Bloqueo Pesimista, Ciberseguridad Bancaria y Desarrollo Orientado a Especificación (SDD + TDD)**


## Información del Proyecto

* **Demo Video (5 min):** `https://youtube.com/watch?v=demo-habicapital`

* **Stack Principal:** Python 3.12+ (FastAPI), TypeScript (Next.js 14 App Router), PostgreSQL 16 (Supabase/Neon), Tailwind CSS.

  

---

  

## 📌 Contexto del Producto y Misión

HabiCapital está transformando la interacción financiera alrededor de la vivienda y los servicios digitales en Latinoamérica. Este proyecto resuelve el problema de mover dinero entre personas normales (*peer-to-peer*) sin fricción ni intermediarios pesados, garantizando al mismo tiempo **integridad financiera absoluta ($0 margen de error)** e **infraestructura de costo cero ($0 USD)**.


## 1. 🛠️ Las decisiones clave y por qué las tomé

### A. Arquitectura: Monolito Modular con Clean Architecture

Elegí un **Monolito Modular con Clean Architecture** en lugar de microservicios o un monolito acoplado tradicional.

* **Por qué:** Los microservicios introducen fallos de red parciales, latencia distribuida y la necesidad de transacciones compuestas (Saga Pattern), lo cual incrementa el riesgo de inconsistencia en un sistema P2P pequeño. Un monolito modular aísla los dominios (`identity`, `ledger`, `payment_requests`, `audit`) en capas estrictas (*Domain, Use Cases, Infrastructure, Adapters*), permitiendo velocidad de desarrollo con IA sin comprometer la separación de responsabilidades.

  

```text

[HTTP / DTOs] -> Adapters (FastAPI)

|

[Use Cases] ------> Application (Orquestación Transaccional)

|

[Domain Rules] ---> Domain Kernel (Python Puro, Sin ORM)

|

[SQL / Crypto] ----> Infrastructure (SQLAlchemy 2.0 + PostgreSQL)

```

  

### B. Identificador P2P: Alias Único e Inmutable + Enmascaramiento (*Name Masking*)

Elegí usar un **Alias único e inmutable** (`^[a-z0-9_]{3,20}$`) configurado al registrarse.

* **Por qué:** Protege la privacidad del usuario al evitar exponer números de teléfono o correos personales. Para prevenir ataques de cosecha de usuarios (*Account Harvesting / User Enumeration*), la búsqueda por alias exige coincidencia exacta (sin `LIKE %query%`) y retorna el nombre enmascarado (*Name Masking*: `"Juan Esteban Gómez"` $\rightarrow$ `"J*** E******* G****"`).

  

### C. Flujo de Transferencia en 2 Pasos (`Lookup` $\rightarrow$ `Execute`)

Dividí la transferencia P2P en dos interacciones API:

1. `POST /api/v1/transfers/lookup`: Devuelve el UUID del destinatario y su nombre enmascarado.

2. `POST /api/v1/transfers/execute`: Ejecuta la transferencia monetaria requiriendo el `recipient_id` y la cabecera `X-Idempotency-Key`.

* **Por qué:** Elimina transferencias erróneas por tipografía y da confirmación explícita al emisor antes de mover dinero real.


  

### D. Killer Feature: Sistema de Cobros Informales (Payment Requests)

#### **El Problema en la Vida Real**
En las relaciones cotidianas —dividirse la cuenta de una cena, saldar los servicios entre roommates o cobrar un trabajo informal— mover plata no es solo un problema técnico, es una interacción social. Casi siempre ocurre lo mismo: quien adelantó el dinero siente la "pena" o incomodidad de estar recordando la deuda, mientras que quienes deben pagar rara vez lo hacen por mala fe; simplemente lo olvidan entre las ocupaciones del día a día o no tienen saldo en ese instante exacto.
#### **Por qué se escogió esta Feature**

Elegí esta funcionalidad porque ataca de frente la fricción humana de las finanzas informales. En lugar de limitarse a transferir dinero, el sistema introduce empatía en la experiencia: elimina la conversación incómoda y convierte el cobro en un flujo transparente, respetuoso y de un solo clic.
#### **Impacto en la Experiencia del Usuario**

- **Para quien cobra:** Transfiere la carga de "recordar" al sistema. Puede enviar una solicitud clara y amigable en segundos, manteniendo visibilidad total sobre quién ha pagado y quién tiene un cobro pendiente, sin necesidad de escribir mensajes incomodantes.
    
- **Para quien paga (Resiliencia empática):** Entiende que la vida financiera real es cambiante. Si el pagador intenta saldar la deuda pero no cuenta con fondos suficientes en ese segundo, el sistema no castiga al usuario cancelando o destruyendo la solicitud. En su lugar, absorbe el fallo de forma transparente y mantiene el cobro disponible en espera, permitiéndole recargar saldo y ponerse al día cuando le sea posible, sin perder el hilo de la deuda ni generar frustración.


### E. Selección del Stack Tecnológico: Python (FastAPI) + TypeScript (Next.js)

#### 1. Alineación Estratégica y Experiencia Previa
Elegí este stack porque combina mi experiencia previa construyendo productos con **Next.js, FastAPI, Pydantic y SQLAlchemy**, con el ecosistema tecnológico que **HabiCapital** opera en su arquitectura del día a día (TypeScript en el Frontend y Python en el Backend). Esta coincidencia elimina curvas de aprendizaje y me permite enfocar el 100% de la capacidad de ingeniería en el rigor financiero, la seguridad y la consistencia transaccional.

#### 2. Justificación Técnica para un Entorno Financiero
Más allá de la velocidad de ejecución, la integración de estas tecnologías ofrece ventajas críticas para una plataforma bancaria:

* **Tipado Estricto End-to-End y Excelente DX:** TypeScript en la capa de presentación y Pydantic v2 en la capa de aplicación garantizan contratos de datos predecibles, eliminando errores de tipo en runtime antes de tocar el dominio.
* **Validación y Sanitización por Diseño:** FastAPI y Pydantic parsean, validan y filtran automáticamente cada payload de entrada contra el esquema DTO antes de invocar los casos de uso, blindando la API contra payloads malformados e inyecciones.
* **Control Transaccional Fino:** SQLAlchemy 2.0 proporciona el control granular necesario para gestionar transacciones ACID complejas, bloqueos pesimistas a nivel de fila (`SELECT ... FOR UPDATE`) y migraciones con Alembic sin margen de error.
* **Ecosistema AI-Native:** Son tecnologías maduras, fuertemente tipadas y masivamente adoptadas a nivel global. Esto maximiza la precisión de los modelos de IA (LLMs) durante el desarrollo y testing, alineándose de forma nativa con la cultura *AI-First* de HabiCapital.

---

### F. Metodología de Ingeniería: SDD (Spec-Driven) + TDD (Test-Driven)

#### 1. Spec-Driven Development (SDD): Especificación Formal como Fuente de Verdad
En una cultura *AI-Native* donde la generación de código se apoya en modelos de IA, la claridad de las especificaciones es el factor determinante entre un sistema robusto y un fallo en producción. La metodología **SDD** consistió en diseñar y auditar formalmente la arquitectura, el esquema DDL, los modelos de datos, las políticas de ciberseguridad y los contratos OpenAPI en **5 documentos `.md` de especificación técnica** antes de escribir la primera línea de código de producción. Esto elimina la ambigüedad, previene "alucinaciones" de la IA y asegura que el software se construya exactamente según los principios de Clean Architecture.

#### 2. Test-Driven Development (TDD): Blindaje Financiero Automático
Para garantizar el cumplimiento incondicional de la *Regla Suprema* (*"el sistema no puede perder un peso"*), la verificación no puede ser un paso posterior. Bajo **TDD estricto**:
1. **Fase RED (Fallo Controlado):** Se escriben primero las pruebas automatizadas en Pytest para todos los escenarios (casos felices, sobregiros por saldo insuficiente, ataques de reintentos por red, disputas de idempotencia y concurrencia de hilos simultáneos). Se ejecuta la suite y se confirma que falla por las razones correctas.
2. **Fase GREEN (Implementación Mínima):** Se implementa el código de producción estrictamente necesario para hacer pasar las pruebas con éxito.
3. **Fase REFACTOR (Optimización Segura):** Se refactoriza la estructura manteniendo la suite de pruebas en verde.

#### 3. Sinergia SDD + TDD con Inteligencia Artificial
La combinación de **SDD + TDD** establece un ciclo de retroalimentación cerrado (*Closed-Loop Feedback*) perfecto para la asistencia con IA:
* **El SDD actúa como el mapa y la restricción:** Le otorga a la IA la arquitectura exacta y los límites de dominio que no puede rebasar.
* **El TDD actúa como el juez objetivo:** Sirve como un marco de validación determinista que la IA utiliza para autoevaluar y corregir su propio código antes de dar por completada una tarea.

### G. Balance Estratégico: Seguridad Bancaria y Enfoque User-Centric

#### 1. Rigor Financiero e Invariantes de Seguridad (La Columna Vertebral)
Dado el contexto bancario y el cumplimiento estricto de la *Regla Suprema* (*"el sistema no puede perder un peso"*), la seguridad y la consistencia no son características opcionales ni capas añadidas a posteriori:
* **Integridad Transaccional ACID Estricta:** Bloqueos pesimistas a nivel de fila (`SELECT ... FOR UPDATE`), ordenamiento de UUIDs anti-deadlocks y Libro Mayor de partida doble (*Double-Entry Ledger*) garantizan que ninguna operación altere el balance sin una contrapartida exacta.
* **Arquitectura Resiliente a Filtraciones:** Cifrado a nivel de campo (*Field-Level Encryption* con AES-256-GCM), *Blind Indexing* con HMAC-SHA256 para búsquedas sin texto plano y contraseñas procesadas con Argon2id. Si la base de datos sufriera un volcado no autorizado (*data breach*), la información personal (PII) permanece matemáticamente ininteligible.
* **Auditoría Inmutable y No Repudio:** Registro persistente de eventos (`audit_logs`) que almacena hashes de payloads, direcciones IP y marcas de tiempo para garantizar la trazabilidad de cada intento operado en el sistema.

#### 2. Experiencia de Usuario (User-Centric &amp; UX Empática)
Inspirado en las interacciones cotidianas de las finanzas personales e informales (dividir cuentas de restaurante, pagos entre roommates, cobros a amigos), el producto elimina la burocracia bancaria tradicional para entregar una UX moderna, fluida y sin fricción:

* **P2P Sin Exposición de Datos Sensibles:** El uso de **Aliases únicos** cortos y fáciles de memorizar (`@alias`), combinado con la **búsqueda exacta y confirmación en 2 pasos con *Name Masking*** (`"¿Confirmas enviar $50.000 a J*** E******* G****?"`), le otorga al usuario certeza absoluta antes de mover su dinero, sin forzarlo a compartir números de cédula, correos o datos bancarios pesados.
* **Gestión Empática y No Destructiva de Errores:** En la *Killer Feature* de cobros (*Payment Requests*), si un usuario intenta responder un cobro pero no cuenta con fondos suficientes, el sistema aborta de forma segura la transacción financiera pero **mantiene el cobro en estado `PENDING`**, presentando un mensaje claro y no punitivo (*"Saldo insuficiente (\$X COP faltantes). Tu cobro sigue pendiente para cuando recargues saldo"*). Esto elimina la fricción social de tener que re-generar o solicitar un nuevo cobro.



---

  

## 2. Cómo sé que mi sistema no pierde un peso

  

### A. Qué puede salir mal (Matriz de Riesgos Financieros)

1. **Condiciones de Carrera (Race Conditions):** Dos solicitudes simultáneas en el mismo milisegundo intentando gastar el mismo saldo.

2. **Doble Débito / Clics Repetidos:** Reintentos de red o clics ansiosos del usuario duplicando una transferencia.

3. **Errores de Redondeo (Floating Point Arithmetic):** Pérdida de centavos por imprecisión IEEE 754 de números flotantes.

4. **Desbalance Contable:** Creación o destrucción mágica de dinero por inconsistencia en la base de datos.

  

### B. Cómo lo protejo (Mecanismos de Blindaje)

  

#### 1. Contabilidad de Partida Doble (*Double-Entry Ledger*)

El saldo de un usuario **jamás se almacena como un número estático editable** (`UPDATE accounts SET balance = X`). El saldo es un **resultado derivado** calculado dinámicamente mediante el historial inmutable de asientos contables:

  

$$\text{Saldo}_{\text{cuenta}} = \sum \text{Créditos Recibidos} - \sum \text{Débitos Enviados}$$

  

Cada operación inserta un registro en `ledger_entries` con una cuenta debitada y una acreditada. La suma global de débitos y créditos en el sistema es estrictamente cero:

  

$$\sum \text{Débitos} - \sum \text{Créditos} = 0$$

  

#### 2. Unidad Monetaria Entera (`BIGINT` - Zero-Decimal COP)

Todos los montos se manejan exclusivamente en números enteros de 64 bits (`BIGINT`), donde **1 unidad = $1 COP**. Se prohíbe el uso de `FLOAT` o `DOUBLE`.

  

#### 3. Bloqueo Pesimista en BD con Ordenamiento Anti-Deadlock

Para procesar una transferencia, se inicia una transacción relacional ACID y se aplica un bloqueo a nivel de fila (`SELECT ... FOR UPDATE`) sobre las cuentas involucradas.

* **Prevención de Deadlocks:** Las cuentas se ordenan alfabéticamente por su UUID antes de bloquearlas (`ORDER BY id ASC`). Esto garantiza que dos transacciones concurrentes entre los mismos usuarios siempre adquieran los cerrojos en el mismo orden, eliminando interbloqueos.

  

#### 4. Idempotencia Bancaria (`X-Idempotency-Key`)

El middleware intercepta peticiones mutativas (`POST`), valida el UUIDv4 de la cabecera y computa un hash SHA-256 del payload (`Method:Path:Body`). Si detecta un reintento de la misma llave, retorna la respuesta almacenada en caché (`X-Cache: HIT-IDEMPOTENCY`) sin reejecutar el asiento contable.

  

### C. Qué evidencia tengo de que funciona (TDD Suite & QA Gates)

  

1. **Prueba de Concurrencia Simultánea (`tests/test_concurrency.py`):**

* **Escenario:** El Usuario A ($50.000 COP de saldo) envía **10 transferencias simultáneas de $50.000 COP** al Usuario B en el mismo milisegundo mediante `asyncio.gather()`.

* **Evidencia:** **Exactamente 1 solicitud retorna HTTP 201 (Exitosa)** y **9 solicitudes retornan HTTP 400 (Saldo insuficiente)**. El saldo final del Usuario A es exactamente **$0 COP** (cero sobregiros) y el del Usuario B es **$50.000 COP**.

2. **Prueba de Auditoría Global (`tests/test_ledger_audit.py`):**

* **Escenario:** Consulta la suma total de débitos y créditos en `ledger_entries`.

* **Evidencia:** `assert total_debits == total_credits` pasa al 100% en cada ejecución de integración.

  

---

  

## 3. Qué dejé fuera y por qué

  

1. **Integración con Pasarelas de Pago Reales (PSE / Transfiya / Bancos):**

* **Por qué:** El requerimiento del reto especificaba que la carga de dinero debía ser simulada (`POST /api/v1/admin/topup`). Enfocar tiempo en integraciones bancarias externas habría desviado atención del núcleo financiero inmutable.

2. **KYC Biométrico Avanzado (Reconocimiento Facial / Validación de Cédula):**

* **Por qué:** Para un prototipo P2P, la autenticación robusta por JWT, Argon2id y alias único brinda la seguridad necesaria sin introducir fricción de registro excesiva.

3. **Expiración Automática de Cobros vía Celery / Redis:**

* **Por qué:** Mantener la restricción de **Costo Cero ($0 USD)** impone evitar dependencias pesadas como Redis o workers en segundo plano. Los cobros en `PENDING` permanecen así de forma indeterminada hasta ser resueltos manualmente.

4. **WebSockets / Server-Sent Events para Notificaciones Push:**

- **Por qué:** Se utilizó _Polling_ reactivo optimizado en TanStack Query v5 en el frontend, reduciendo el consumo de memoria en el free tier de hosting (Render 512MB RAM).

---

  

## 4. Qué haría distinto con más tiempo

  

1. **Firmas Criptográficas Poscuánticas en el Cliente (WASM):**

* Implementaría firmas de transacciones en el navegador utilizando **ML-DSA (Dilithium)** mediante WebAssembly, logrando no-repudio criptográfico directamente desde el dispositivo del usuario antes de tocar la API.

2. **Webhooks de Notificación en Tiempo Real:**

* Implementaría Server-Sent Events (SSE) ligeros sin Redis para notificar instantáneamente al pagador cuando recibe un cobro o al emisor cuando se completa una transferencia.

3. **Réplicas de Lectura en PostgreSQL:**

* Separaría las consultas de historial y extractos hacia una réplica de lectura, dejando la instancia primaria exclusivamente para el motor de escrituras y bloqueos pesimistas `SELECT ... FOR UPDATE`.

4. **Descubrimiento de Producto Profundo, Investigación Cualitativa y Modelado de Dominio (Product Discovery & Domain Artifacts):** 

- **Por qué:** En un producto comercial de escala es indispensable conversar directamente con usuarios reales que enfrentan la fricción de cobrar o saldar deudas informales, entrevistarlos y observarlos en su contexto real (*contextual inquiry*). Dejé fuera la construcción formal de artefactos de producto como *Persona Profiles*, Mapas de Empatía, *Context Canvas*, la descomposición de requerimientos en Historias de Usuario bajo el estándar **INVEST**, y la diagramación estructural en **UML** y esquemas **Entidad-Relación (E-R)** a nivel estratégico. Realizar este proceso vital para construir un **Product Vision** sostenible, extensible y mantenible a largo plazo.

5. **Resiliencia ante Conectividad Eventual (*Offline-First*) y Microoptimizaciones de Concurrencia / Multithreading:** 

- **Conectividad Eventual (Offline-First & Eventual Consistency en el Cliente):** Diseñaría mecanismos de sincronización para entornos de red inestables o intermitentes.
- **Multithreading y Microoptimizaciones de Rendimiento en Backend:** Maximizar el rendimiento del servidor bajo ráfagas intensas de tráfico aislamientos y delegaciones.
6. **Autofill para contactos y trasnferencias recurrente:** Buscando reducir la fricción al máximo y mejorar la experiencia del usuario
7. **Mejorar los mensajes de error:** Si bien los errores que se muestran no son output de consola sino español amigable, no son mensajes demasiado útiles que indiquen qu+e salió mal exactamete o como lidiar con ello. Así que podnría mensajes menos genéricos para que sean más útiles
8. **Crypto-Shredding:** La soberanía del usuario sobre sus datos es escencial. El sistea actual respeta bien muchos de estos principios, sin embargo actualmente no cuenta con un mecanismo para borrar la cuenta deñ usuario junto con sus datos (sin pereder la auditabilidad histórica).

---

  

## 5. Qué NO sé


1. **Normativa Regulatoria y Encaje Bancario de la SFC / SEDPEs en Colombia:**

* Entiendo los principios de ciberseguridad y contabilidad, pero no conozco las exigencias de regulacial detalleón legal para Sociedades Especializadas en Pagos (SEDPE) ante la Superintendencia Financiera de Colombia (reportes UIAF, reservas de liquidez).

  

---

  

## 6. Los supuestos que hice y por qué

  

1. **Unidad Monetaria 1:1 con COP:**

* **Supuesto:** 1 unidad entera = $1 Peso Colombiano.

* **Por qué:** Elimina la necesidad de manejar centavos o decimales, simplificando las consultas contables y eliminando errores de punto flotante.

2. **Inmutabilidad del Alias de Usuario:**

* **Supuesto:** El alias se elige en el registro y jamás se puede modificar.

* **Por qué:** Previene ataques de suplantación de identidad (*Impersonation*) y garantiza que las referencias históricas en las búsquedas sigan siendo consistentes.

3. **Vigencia Indefinida de Cobros Pendientes:**

* **Supuesto:** Un *Payment Request* no expira automáticamente.

* **Por qué:** Simplifica la máquina de estados y la arquitectura de infraestructura ($0 USD), dejando la responsabilidad de cancelación al creador del cobro.

4. **Inyección de Saldo Inicial vía Admin (`SYSTEM_OMNIBUS`):**

* **Supuesto:** El saldo entra al ecosistema P2P únicamente cuando el Administrador ejecuta un TopUp desde la cuenta ómnibus del sistema.

* **Por qué:** Garantiza la ecuación de conservación de la partida doble: el dinero no se crea de la nada, se debitan fondos de la cuenta del sistema para acreditarlos al usuario.

  

---

  

## 7. Cómo usé IA: Dinámica, Herramientas y Lecciones


### A. Herramientas y Dinámica

* **Herramientas:** Gemini y NotebookLM como Arquitecto de Soluciones y Partner de diseño usando re-prompting, y Codex para generación de código SDD/TDD.

* **Metodología:** **Spec-Driven Development (SDD)**. Antes de escribir una sola línea de código en FastAPI, utilicé Gemini Notebook para co-diseñar y auditar 5 documentos de especificación técnica `.md` en la carpeta `.spec/`.

* **Flujo TDD:** Le exigí a la IA que para cada módulo escribiera **primero las pruebas unitarias/integrales en Pytest (Fase Red)**. Solo cuando las pruebas fallaban correctamente, le ordenaba escribir la implementación en FastAPI/SQLAlchemy para ponerlas en verde (Fase Green).

  

### B. Qué le pedía yo vs. Qué decidía la IA

* **Yo decidía:** La visión de producto y del sistema, arquitectura de partida doble, las reglas innegociables de dominio, el énfasis en ciberseguridad, atención a UX sin fricción, y la estrategia de cero costo.

* **La IA ejecutaba:** La generación de specs, código y configuraciones.

  

### C. El error de la IA: Cuando casi me hace equivocar

* **Ejemplos:** En la fase inicial de diseño del módulo financiero, la IA consideró actualizar el saldo de los usuarios mediante una consulta directa de actualización, además, sugirió utilizar tokens JWT firmados con RSA-2048 y usar tipos de datos `FLOAT` para los montos.
  Además, en una primera simulación de SCRUM Master y Product Owner, la IA paso por alto múltiples aspectos vitales de la fase de diseño (como arquitectura, entidades, flujos, restricciones o seguridad de vanguardia).

* **La Corrección:** Rechacé la propuesta de la IA y le pedi rediseñar utilizando un **Libro Mayor de Partida Doble (`ledger_entries`)**, montos enteros **`BIGINT`** y firmas **HMAC-SHA256 / AES-256-GCM** para asegurar resistencia poscuántica y cero pérdidas.
  Además, utilicé re-prompting con otra IA para desarrollar hasta el más mínimo detalle de diseño antes de comenzar con la implementación.

  

---

  

## 8. Qué aprendí

  
* **Lo que fue nuevo para mí:** La aplicación práctica del enfoque **Spec-Driven Development (SDD)** conducido por IA. Descubrí que invertir tiempo en redactar especificaciones `.md` ultra-precisas antes de codificar elimina el 95% de las alucinaciones de la IA.

* **Lo que me sorprendió:** Sugerencias de la IA en el esquema de la DB e integraciones CI/CD

* **Lo que me llevo:** En sistemas financieros, la usabilidad y las pantallas se pueden pulir e iterar, pero **la integridad contable es binaria**: o el sistema es 100% consistente o no sirve. La confianza del usuario reposa en la certeza de que el sistema jamás perderá un peso.
  Incluso un reto sencillo de un sistema con 6 funcionalidades básicas y comunes, demuestra tener una enorme profundidad cuando se desea llevar a altos estándares de calidad y seguridad.


---

*Construido con pasión, rigor financiero y ciberseguridad para el equipo de tecnología de **HabiCapital**.*