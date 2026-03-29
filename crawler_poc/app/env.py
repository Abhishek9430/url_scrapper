from dotenv import find_dotenv, load_dotenv


# Load .env from project root (or parent paths) once per process.
load_dotenv(find_dotenv(), override=False)
