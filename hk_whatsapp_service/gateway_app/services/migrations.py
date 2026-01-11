# gateway_app/services/migrations.py
"""
Migraciones automáticas de base de datos.
Se ejecutan al iniciar la app.
"""

import logging
from gateway_app.services.db import execute, fetchone, using_pg

logger = logging.getLogger(__name__)


def table_exists(table_name: str) -> bool:
    """Verifica si una tabla existe."""
    if using_pg():
        sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = ?
            )
        """
        result = fetchone(sql, [table_name])
        return result and list(result.values())[0]
    else:
        # SQLite
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = fetchone(sql, [table_name])
        return result is not None


def create_tickets_table():
    """Crea la tabla de tickets."""
    logger.info("📦 Creando tabla 'tickets'...")
    
    sql = """
        CREATE TABLE IF NOT EXISTS public.tickets (
            id SERIAL PRIMARY KEY,
            habitacion TEXT NOT NULL,
            detalle TEXT NOT NULL,
            prioridad TEXT NOT NULL CHECK (prioridad IN ('ALTA', 'MEDIA', 'BAJA')),
            origen TEXT NOT NULL CHECK (origen IN ('huesped', 'supervisor', 'trabajador')),
            estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'en_progreso', 'pausado', 'completado', 'cancelado')),
            
            asignado_a TEXT,
            asignado_a_nombre TEXT,
            
            creado_por TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            ended_at TIMESTAMPTZ,
            
            total_paused_seconds INTEGER DEFAULT 0,
            tiempo_sin_resolver_mins INTEGER
        )
    """
    
    if not using_pg():
        # Adaptar para SQLite
        sql = """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habitacion TEXT NOT NULL,
                detalle TEXT NOT NULL,
                prioridad TEXT NOT NULL CHECK (prioridad IN ('ALTA', 'MEDIA', 'BAJA')),
                origen TEXT NOT NULL CHECK (origen IN ('huesped', 'supervisor', 'trabajador')),
                estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'en_progreso', 'pausado', 'completado', 'cancelado')),
                
                asignado_a TEXT,
                asignado_a_nombre TEXT,
                
                creado_por TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP,
                
                total_paused_seconds INTEGER DEFAULT 0,
                tiempo_sin_resolver_mins INTEGER
            )
        """
    
    execute(sql, commit=True)
    logger.info("✅ Tabla 'tickets' creada")


def create_indices():
    """Crea índices para optimizar búsquedas."""
    logger.info("📑 Creando índices...")
    
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_tickets_estado ON public.tickets(estado)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_asignado_a ON public.tickets(asignado_a)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_prioridad ON public.tickets(prioridad)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON public.tickets(created_at DESC)",
    ]
    
    if not using_pg():
        # Adaptar para SQLite
        indices = [idx.replace("public.tickets", "tickets") for idx in indices]
    
    for idx_sql in indices:
        try:
            execute(idx_sql, commit=True)
        except Exception as e:
            logger.warning(f"⚠️ Índice ya existe o error: {e}")
    
    logger.info("✅ Índices creados")


def create_trigger_updated_at():
    """Crea trigger para actualizar updated_at automáticamente."""
    if not using_pg():
        logger.info("⏭️ Triggers solo para PostgreSQL, saltando...")
        return
    
    logger.info("⚡ Creando trigger 'update_updated_at'...")
    
    # Crear función
    sql_function = """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """
    
    # Crear trigger
    sql_trigger = """
        DROP TRIGGER IF EXISTS update_tickets_updated_at ON public.tickets;
        CREATE TRIGGER update_tickets_updated_at 
        BEFORE UPDATE ON public.tickets 
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """
    
    try:
        execute(sql_function, commit=True)
        execute(sql_trigger, commit=True)
        logger.info("✅ Trigger creado")
    except Exception as e:
        logger.warning(f"⚠️ Error creando trigger: {e}")


def run_migrations():
    """
    Ejecuta todas las migraciones necesarias.
    Se llama al iniciar la app.
    """
    logger.info("=" * 60)
    logger.info("🔧 VERIFICANDO ESTADO DE BASE DE DATOS")
    logger.info("=" * 60)
    
    try:
        # Verificar si la tabla existe
        tickets_exists = table_exists("tickets")
        
        if tickets_exists:
            logger.info("✅ Tabla 'tickets' ya existe")
            
            # Verificar cuántos registros tiene
            table = "public.tickets" if using_pg() else "tickets"
            count_result = fetchone(f"SELECT COUNT(*) as count FROM {table}")
            count = count_result['count'] if count_result else 0
            
            logger.info(f"📊 La tabla tiene {count} registros")
            logger.info("⏭️  Saltando creación de tablas (ya existen)")
            logger.info("=" * 60)
            return
        
        logger.info("📦 Tabla 'tickets' no existe, creando...")
        create_tickets_table()
        create_indices()
        create_trigger_updated_at()
        
        logger.info("🎉 Migraciones completadas exitosamente")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.exception("❌ ERROR EN MIGRACIONES")
        logger.error("=" * 60)
        # NO lanzar excepción, dejar que la app siga
        logger.warning("⚠️ La app continuará sin migraciones")