import sys
from upload_data import get_db_engine, public_error
from sqlalchemy import text


def main() -> int:
    engine = None
    try:
        engine = get_db_engine()
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar()
        print("Successfully connected to configured PostgreSQL target.")
        print(f"Database version: {version}")
        return 0
    except Exception as error:
        print(f"Failed to connect to the database. {public_error(error)}")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
