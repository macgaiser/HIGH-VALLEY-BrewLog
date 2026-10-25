"""Gemeinsame Test-Einrichtung.

DATA_DIR muss vor dem ersten Import von `app` gesetzt sein (der Datenbank-
pfad wird beim Import festgelegt) - die Tests laufen so in einem
Wegwerf-Ordner und fassen nie echte Daten an.
"""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="brewlog-tests-")
os.environ["APP_USERNAME"] = "tester"
os.environ["APP_PASSWORD"] = "test-passwort-123"
