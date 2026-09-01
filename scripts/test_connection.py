import os
import psycopg2
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

try:
    connection = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT")
    )
    cursor = connection.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print(" Successfully connected to Heroku PostgreSQL!")
    print(f"Database version: {db_version[0]}")
    cursor.close()
    connection.close()
except Exception as error:
    print(" Failed to connect to the database.")
    print(f"Error: {error}")