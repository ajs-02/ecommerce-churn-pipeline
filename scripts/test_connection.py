import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _public_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    secret = os.getenv("POSTGRES_PASSWORD")
    if secret:
        message = message.replace(secret, "***")
    return message


def main() -> int:
    host = os.getenv("POSTGRES_HOST")
    try:
        connection = psycopg2.connect(
            host=host,
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            port=os.getenv("POSTGRES_PORT"),
        )
        cursor = connection.cursor()
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        print(f"Successfully connected to PostgreSQL at {host}.")
        print(f"Database version: {db_version[0]}")
        cursor.close()
        connection.close()
        return 0
    except Exception as error:
        print(" Failed to connect to the database.")
        print(f"Error: {_public_error(error)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
