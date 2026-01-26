# Hestia — WhatsApp Operational Bot for Hotels

Hestia es un **SaaS de operación hotelera** que organiza y automatiza solicitudes de huéspedes,
housekeeping y supervisión usando **WhatsApp como interfaz principal**.

No es un chatbot genérico.  
Es un **sistema operacional conversacional**, con reglas duras, estado y trazabilidad.

---

## 🚩 Problema que resolvemos
En hoteles reales:
- Las solicitudes llegan desordenadas (WhatsApp, llamadas, recepción).
- El personal se interrumpe constantemente.
- Se crean tickets innecesarios.
- No hay trazabilidad ni métricas confiables.
- Los errores impactan directamente la experiencia del huésped y los costos.

Hestia reduce fricción operacional, **no “chatea” por chatear**.

---

## 👥 Usuarios del sistema
Hestia maneja flujos distintos para cada rol:

- **Huésped**  
  Solicitudes simples, FAQs, problemas puntuales.

- **Trabajador (Housekeeping / Mantención)**  
  Recibe tareas, opera por turnos, requiere instrucciones claras.

- **Supervisor**  
  Asigna, reasigna y monitorea; necesita control y visibilidad.

Cada rol tiene reglas, estados y permisos distintos.

---

## ⚠️ Principios no negociables
Antes de tocar código, entiende esto:

- ❌ No todo mensaje crea un ticket  
- ❌ Las ventanas horarias se respetan  
- ❌ El estado importa (no es stateless)  
- ❌ La trazabilidad es obligatoria  
- ❌ La correctitud es más importante que la “inteligencia”

Un bug aquí es **operacional**, no solo técnico.

---

## 🏗️ Arquitectura (alto nivel)

WhatsApp
↓
Webhook
↓
Orquestador
↓
Reglas de negocio
↓
Persistencia (DB)
↓
Respuesta / Acción

El sistema es **event-driven**, con **estado conversacional persistente**
y decisiones auditables.

---

## 📂 Estructura del repositorio (simplificada)

gateway_app/
├─ routes/ # Webhook / entry points
├─ flows/ # Flujos por rol (housekeeping, supervision)
├─ services/ # DB, WhatsApp client, dominio
├─ state/ # Estado conversacional
└─ outgoing/ # UI conversacional (mensajes)


---

## 🚀 Onboarding de Developers (OBLIGATORIO)
Si eres nuevo en el proyecto, **NO empieces leyendo código al azar**.

### Orden correcto:
1. 📄 [`docs/00_contexto_hestia.md`](docs/00_contexto_hestia.md)  
   Entiende el problema real y los errores caros.

2. 🏗️ [`docs/01_architectura.md`](docs/01_architectura.md)  
   Entiende cómo piensa el sistema.

3. 🧭 [`docs/02_code_tour.md`](docs/02_code_tour.md)  
   Aprende por dónde leer el código (y qué ignorar al inicio).

👉 Solo después de eso, toma un issue.

---

## 🧠 Modelo mental clave
> Este bot es una **máquina de estados conversacional con IA acotada**,  
> no un agente autónomo.

Si una decisión no es explicable, es un bug.

---

## 🧪 Testing y cambios
- Cambios pequeños y trazables
- Un flujo completo > muchas líneas
- Todo PR debe explicar **qué decisión cambia**

No refactors grandes sin contexto.

---

## 🛠️ Stack técnico
- Backend: Python
- Mensajería: WhatsApp (Webhook)
- Persistencia: Postgres (Supabase)
- Orquestación: State machine / LangGraph-style
- Infra: Render / Cloud

---

## 📈 Qué medimos
El éxito no se mide por features, sino por:
- Reducción de tickets falsos
- Tiempo medio de resolución
- Estabilidad del flujo
- Carga operacional por rol

---

## 🤝 Contribución
Este proyecto requiere **criterio**, no solo código.

Si no estás seguro de una regla de negocio:
- pregunta
- documenta
- discútelo

Antes de optimizar, **entiende**.

---

## 📌 Licencia
Privado — uso interno del equipo Hestia.
