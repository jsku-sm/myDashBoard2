"""Run locally once to generate a NEW Snorkl Fernet encryption key.
Do not replace the key of an existing data store: its records would become unreadable.
"""
from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode())
