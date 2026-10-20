"""Preserve the operation's original error when SQLite already aborted it."""
import sqlite3


def rollback_after_failure(connection: sqlite3.Connection) -> None:
    try:
        if connection.in_transaction:
            # Bypass writer fencing: abandoning a failed transaction is always
            # necessary, including after losing ownership or an I/O failure.
            sqlite3.Connection.execute(connection, 'ROLLBACK')
    except sqlite3.Error:
        # A storage error during cleanup must not replace the original cause.
        # The surrounding managed context still closes the connection.
        pass
