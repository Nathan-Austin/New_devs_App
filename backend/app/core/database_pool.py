import asyncio
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            # Build the async connection string from the actual database_url setting.
            # This previously referenced settings.supabase_db_user/host/port/name,
            # which do not exist on Settings, so this always raised AttributeError
            # and every caller silently fell back to hardcoded mock data.
            database_url = settings.database_url
            if database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            # No explicit poolclass: QueuePool (the previous value here) is a sync
            # pool and is not compatible with an async engine.
            self.engine = create_async_engine(
                database_url,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session from pool as an async context manager.
        Must stay decorated with asynccontextmanager: callers use
        "async with db_pool.get_session() as session", which requires this
        call to return a context manager, not a bare coroutine."""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        async with self.session_factory() as session:
            yield session

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
