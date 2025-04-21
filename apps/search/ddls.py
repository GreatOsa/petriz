import multiprocessing
import logging
import sqlalchemy as sa

from helpers.fastapi.sqlalchemy import setup
from apps.search.models import Term, Topic, SearchRecord


logger = logging.getLogger(__name__)

# Constants for search configuration
SEARCH_CONFIG = {
    "language": "pg_catalog.english",
    "weights": {
        "name": "A",
        "definition": "B",
    },
}

SEARCH_DDLS = (
    # Drop existing triggers and functions for clean slate
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS terms_search_tsvector_update ON {Term.__tablename__};
    DROP TRIGGER IF EXISTS search_records_query_tsvector_update ON {SearchRecord.__tablename__};
    DROP FUNCTION IF EXISTS update_terms_search_tsvector();
    DROP FUNCTION IF EXISTS backfill_tsvectors();
    """),
    # Create backfill function with proper string escaping
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION backfill_tsvectors() RETURNS void AS 
    $$
    DECLARE
        terms_count integer;
        records_count integer;
    BEGIN
        -- Backfill terms
        UPDATE {Term.__tablename__} t
        SET search_tsvector = 
            CASE 
                WHEN t.name IS NULL AND t.definition IS NULL THEN NULL
                ELSE
                    setweight(to_tsvector('{SEARCH_CONFIG["language"]}', COALESCE(t.name, '')), 
                        '{SEARCH_CONFIG["weights"]["name"]}') ||
                    setweight(to_tsvector('{SEARCH_CONFIG["language"]}', COALESCE(t.definition, '')), 
                        '{SEARCH_CONFIG["weights"]["definition"]}')
            END
        WHERE (t.name IS NOT NULL OR t.definition IS NOT NULL)
            AND t.search_tsvector IS NULL;
        
        GET DIAGNOSTICS terms_count = ROW_COUNT;
        RAISE NOTICE 'Updated %% term records', terms_count;

        -- Backfill search records
        UPDATE {SearchRecord.__tablename__} sr
        SET query_tsvector = to_tsvector('{SEARCH_CONFIG["language"]}', query)
        WHERE query IS NOT NULL 
            AND query != ''
            AND query_tsvector IS NULL;
        
        GET DIAGNOSTICS records_count = ROW_COUNT;
        RAISE NOTICE 'Updated %% search records', records_count;
        
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Backfill failed: %%', SQLERRM;
    END;
    $$ LANGUAGE plpgsql;
    """),
    # Create terms trigger function
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_terms_search_tsvector() RETURNS trigger AS 
    $$
    BEGIN
        NEW.search_tsvector := 
            CASE 
                WHEN NEW.name IS NULL AND NEW.definition IS NULL THEN NULL
                ELSE
                    setweight(to_tsvector('{SEARCH_CONFIG["language"]}', COALESCE(NEW.name, '')), 
                        '{SEARCH_CONFIG["weights"]["name"]}') ||
                    setweight(to_tsvector('{SEARCH_CONFIG["language"]}', COALESCE(NEW.definition, '')), 
                        '{SEARCH_CONFIG["weights"]["definition"]}')
            END;
        RETURN NEW;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Failed to update tsvector: %%', SQLERRM;
        NEW.search_tsvector := NULL;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    # Create triggers
    sa.DDL(f"""
    CREATE TRIGGER terms_search_tsvector_update
        BEFORE INSERT OR UPDATE OF name, definition ON {Term.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_terms_search_tsvector();
    """),
    sa.DDL(f"""
    CREATE TRIGGER search_records_query_tsvector_update
        BEFORE INSERT OR UPDATE OF query ON {SearchRecord.__tablename__}
        FOR EACH ROW
        WHEN (NEW.query IS NOT NULL)
        EXECUTE FUNCTION tsvector_update_trigger(
            query_tsvector, '{SEARCH_CONFIG["language"]}', query
        );
    """),
    # Execute backfill
    sa.DDL("SELECT backfill_tsvectors();"),
)


def execute_search_ddls():
    """Execute search-related DDL statements once during application startup."""
    # Prevents multiple workers from executing DDLs concurrently which
    # may trigger deadlocks from the process trying to acquire AccessExclusiveLock
    # on the same database object(table) at the same time
    with multiprocessing.Lock(), setup.engine.begin() as conn:
        try:
            # Execute DDLs in transaction
            for ddl in SEARCH_DDLS:
                conn.execute(ddl)
            conn.execute(sa.text("COMMIT"))
            logger.info("Successfully executed search DDL statements")
        except Exception as exc:
            logger.error(f"Failed to execute search DDL statements: {exc}")
            raise
