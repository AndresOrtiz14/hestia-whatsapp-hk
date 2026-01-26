# Contexto del Proyecto — Hestia

## Qué es Hestia
Hestia es un SaaS para hoteles urbanos (4–5 estrellas) que **automatiza y ordena la operación diaria**
principalmente en housekeeping, mantención y supervisión, usando WhatsApp como canal principal.

No somos un “chatbot”.
Somos un **sistema operativo conversacional** para operaciones hoteleras.

---

## El problema que resolvemos
En la operación hotelera real:
- Las solicitudes llegan desordenadas (WhatsApp, llamadas, recepción).
- El personal se interrumpe constantemente.
- Se crean tickets innecesarios.
- No hay trazabilidad ni métricas confiables.
- Los errores cuestan dinero y experiencia de huésped.

Hestia **reduce fricción operacional**, no conversa por conversar.

---

## Usuarios del sistema
Hestia tiene **tres roles principales**, cada uno con flujos distintos:

1. **Huésped**
   - Hace solicitudes simples (wifi, toallas, problemas).
   - No conoce la estructura interna del hotel.
   - Error caro: crear tickets innecesarios.

2. **Trabajador (Housekeeping / Mantención)**
   - Recibe tareas.
   - Opera por turnos.
   - Necesita instrucciones claras y mínimas.

3. **Supervisor**
   - Asigna, re-asigna y monitorea.
   - Necesita visibilidad y control, no ruido.

---

## Errores caros (NO negociables)
Un developer nuevo debe entender esto desde el día 1:

- ❌ Crear un ticket cuando no corresponde.
- ❌ Ignorar ventanas horarias (ej. noche).
- ❌ Romper reglas de turno.
- ❌ Clasificar mal una intención (FAQ ≠ ticket).
- ❌ Perder trazabilidad de una decisión del bot.

La **correctitud operacional** es más importante que la “inteligencia”.

---

## KPIs reales del sistema
No medimos éxito por features, sino por:
- Reducción de tickets falsos
- Tiempo medio de resolución
- Cumplimiento de ventanas horarias
- Carga operacional por trabajador
- Estabilidad del flujo (menos excepciones)

---

## Principio rector
> Antes de optimizar código, optimizamos **decisiones**.

Si no entiendes por qué una regla existe, **no la cambies** sin discutirla.
