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

def create_ticket_media_table():
    """Crea la tabla para almacenar medios (fotos/videos) de tickets."""
    logger.info("📦 Creando tabla 'ticket_media'...")
    
    sql = """
        CREATE TABLE IF NOT EXISTS public.ticket_media (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER REFERENCES public.tickets(id) ON DELETE CASCADE,
            media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video', 'document', 'audio')),
            storage_url TEXT,
            whatsapp_media_id TEXT,
            mime_type TEXT,
            file_size_bytes INTEGER,
            uploaded_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """
    
    if not using_pg():
        # SQLite no soporta REFERENCES con CASCADE, simplificar
        sql = """
            CREATE TABLE IF NOT EXISTS ticket_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video', 'document', 'audio')),
                storage_url TEXT,
                whatsapp_media_id TEXT,
                mime_type TEXT,
                file_size_bytes INTEGER,
                uploaded_by TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    
    execute(sql, commit=True)
    
    # Crear índice
    idx_sql = "CREATE INDEX IF NOT EXISTS idx_ticket_media_ticket_id ON public.ticket_media(ticket_id)"
    if not using_pg():
        idx_sql = idx_sql.replace("public.ticket_media", "ticket_media")
    
    try:
        execute(idx_sql, commit=True)
    except Exception as e:
        logger.warning(f"⚠️ Índice ya existe o error: {e}")
    
    logger.info("✅ Tabla 'ticket_media' creada")

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

def seed_base_data():
    """
    Crea datos base mínimos necesarios (org y hotel).
    Solo si no existen.
    """
    from gateway_app.services.db import fetchone, execute
    
    logger.info("🌱 Verificando datos base...")
    
    # Verificar si ya existe una org
    org = fetchone("SELECT id FROM public.orgs LIMIT 1")
    
    if not org:
        logger.info("📦 Creando organización base...")
        execute(
            "INSERT INTO public.orgs (id, name, created_at) VALUES (1, 'Hestia Operations', NOW())",
            commit=True
        )
        logger.info("✅ Organización creada")
    else:
        logger.info(f"✅ Organización ya existe (id={org['id']})")
    
    # Verificar si ya existe un hotel
    hotel = fetchone("SELECT id FROM public.hotels LIMIT 1")
    
    if not hotel:
        logger.info("🏨 Creando hotel base...")
        execute(
            "INSERT INTO public.hotels (id, org_id, name, created_at) VALUES (1, 1, 'Hotel Principal', NOW())",
            commit=True
        )
        logger.info("✅ Hotel creado")
    else:
        logger.info(f"✅ Hotel ya existe (id={hotel['id']})")

def seed_workers():
    """
    Crea workers de prueba directamente en la tabla users.
    IMPORTANTE: Reemplaza los números con tus números REALES de WhatsApp.
    """
    from gateway_app.services.db import fetchone, execute
    import hashlib
    
    logger.info("👥 Verificando workers...")
    
    # Verificar si ya hay workers
    check = fetchone("SELECT COUNT(*) as count FROM public.users WHERE area IN ('HOUSEKEEPING', 'MANTENCION')")
    if check and check['count'] > 0:
        logger.info(f"✅ Ya existen {check['count']} workers")
        return
    
    logger.info("📦 Creando workers de prueba...")
    
    # Password dummy para testing (hash de "test123")
    dummy_password_hash = hashlib.sha256("test123".encode()).hexdigest()
    
    workers_data = [
        {
            "username": "Viveros DA Test",
            "telefono": "56926296499",
            "email": "viveros.test@hestia.local",
            "area": "HOUSEKEEPING",
            "role": "mucama"  # ← AGREGAR ESTE CAMPO
        },
        {
            "username": "Adriana DA Tes", 
            "telefono": "56990763262",
            "email": "adriana.test@hestia.local",
            "area": "HOUSEKEEPING",
            "role": "mucama"  # ← AGREGAR ESTE CAMPO
        },
        {
            "username": "Solange DA Test",
            "telefono": "56989692965",
            "email": "solange.test@hestia.local",
            "area": "MANTENCION",
            "role": "mantencion"  # ← AGREGAR ESTE CAMPO
        },
        {
            "username": "Teresa DA Test",
            "telefono": "56957636794",
            "email": "teresa.test@hestia.local",
            "area": "HOUSEKEEPING",
            "role": "mucama"  # ← AGREGAR ESTE CAMPO
        }
    ]
    
    for worker in workers_data:
        try:
            sql = """
                INSERT INTO public.users 
                (username, telefono, email, area, role, activo, password_hash, initialized)
                VALUES (?, ?, ?, ?, ?, true, ?, true)
            """
            
            execute(sql, [
                worker["username"],
                worker["telefono"],
                worker["email"],
                worker["area"],
                worker["role"],  # ← AGREGAR AQUÍ
                dummy_password_hash
            ], commit=True)
            
            logger.info(f"✅ Worker creado: {worker['username']} ({worker['telefono']})")
            
        except Exception as e:
            # Si falla por duplicate key o constraint, solo advertir
            logger.warning(f"⚠️ No se pudo crear worker {worker['username']}: {e}")
            continue
    
    logger.info("🎉 Workers de prueba listos")
    
def run_migrations_updated():
    """
    Ejecuta todas las migraciones necesarias.
    Se llama al iniciar la app.
    """
    logger.info("=" * 60)
    logger.info("🔧 VERIFICANDO ESTADO DE BASE DE DATOS")
    logger.info("=" * 60)
    
    try:
        # Verificar si las tablas existen
        tickets_exists = table_exists("tickets")

        if tickets_exists:
            logger.info("✅ Tabla 'tickets' ya existe")
            
            # Verificar cuántos registros tiene
            table = "public.tickets" if using_pg() else "tickets"
            count_result = fetchone(f"SELECT COUNT(*) as count FROM {table}")
            count = count_result['count'] if count_result else 0
            
            logger.info(f"📊 La tabla tiene {count} registros")
        else:
            logger.info("📦 Tabla 'tickets' no existe, creando...")
            create_tickets_table()
            create_indices()
            create_trigger_updated_at()
        
        # Siempre verificar y crear datos base
        seed_base_data()
        seed_workers()
        
        logger.info("🎉 Migraciones completadas exitosamente")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.exception("❌ ERROR EN MIGRACIONES")
        logger.error("=" * 60)
        logger.warning("⚠️ La app continuará sin migraciones")

run_migrations = run_migrations_updated