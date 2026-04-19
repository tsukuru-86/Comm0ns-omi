import hashlib
import json
import os
import uuid

from google.cloud import firestore
from google.oauth2 import service_account

service_account_info = None

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)


def _build_firestore_client():
    project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('FIREBASE_PROJECT_ID')
    if service_account_info:
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        return firestore.Client(project=project or service_account_info.get('project_id'), credentials=credentials)
    if project:
        return firestore.Client(project=project)
    return firestore.Client()


db = _build_firestore_client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
