import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from typing import List
from collections import OrderedDict
import psycopg2

# Load environment variables for DB connection
load_dotenv()
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT")

# Establish database connection
chaint_db = psycopg2.connect(
    host=db_host, user=db_user, password=db_password, database=db_name, port=db_port
)

cursor = chaint_db.cursor()


# Function to add a user and folder to the database
def add_user_to_db(user_id, user_name, folder):
    try:
        # Generate current date and time in the specified format
        date_time = (
                datetime.now().date().strftime("%Y-%m-%d")
                + ", "
                + datetime.now().time().strftime("%H:%M:%S")
        )

        # SQL query to insert user data into the database
        query = """
            INSERT INTO folders (user_id, user_name, folder, date_time)
            VALUES (%s, %s, %s, %s)
        """
        # Execute the query with provided data
        cursor.execute(query, (user_id, user_name, folder, date_time))

        # Commit the transaction
        chaint_db.commit()
        print("User Data SAVED!!!")
    except Exception as e:
        print(f"Error saving user data: {e}")
        chaint_db.rollback()  # Rollback in case of an error


# Function to get the last saved folder for a user
def get_last_folder(user_id):
    folder = None
    try:
        # SQL query to get the last folder saved for a user by user_id
        query = """
            SELECT folder FROM folders
            WHERE user_id = %s
            ORDER BY date_time DESC
            LIMIT 1
        """
        # Execute the query, pass user_id as integer
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()

        if result:
            folder = result[0]  # Extract the folder from the result

    except Exception as e:
        print(f"An error occurred while fetching folder: {e}")

    return folder