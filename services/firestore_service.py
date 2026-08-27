from functools import lru_cache
from typing import Any

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists

@lru_cache(maxsize=1)
def get_firestore_client() -> firestore.Client:
    """
    Create and reuse one Firestore client.

    Locally, this uses Application Default Credentials.
    On Cloud Run, it uses the Cloud Run service account.
    """
    return firestore.Client()


def list_documents(collection_name: str) -> list[dict[str, Any]]:
    """
    Return every document in a Firestore collection.
    """
    client = get_firestore_client()
    documents = client.collection(collection_name).stream()

    results = []

    for document in documents:
        data = document.to_dict()
        data["_document_id"] = document.id
        results.append(data)

    return results


def get_document(
    collection_name: str,
    document_id: str,
) -> dict[str, Any] | None:
    """
    Return one document, or None when it does not exist.
    """
    client = get_firestore_client()
    snapshot = (
        client.collection(collection_name)
        .document(document_id)
        .get()
    )

    if not snapshot.exists:
        return None

    data = snapshot.to_dict()
    data["_document_id"] = snapshot.id
    return data


def set_document(
    collection_name: str,
    document_id: str,
    data: dict[str, Any],
) -> None:
    """
    Create a document or replace an existing document.
    """
    client = get_firestore_client()

    (
        client.collection(collection_name)
        .document(document_id)
        .set(data)
    )


def update_document(
    collection_name: str,
    document_id: str,
    updates: dict[str, Any],
) -> None:
    """
    Update selected fields without replacing the whole document.
    """
    client = get_firestore_client()

    (
        client.collection(collection_name)
        .document(document_id)
        .update(updates)
    )

def create_document(
    collection_name: str,
    document_id: str,
    data: dict[str, Any],
) -> bool:
    """
    Create a document only when the ID does not already exist.

    Returns:
        True: the document was created.
        False: a document with the same ID already exists.
    """
    client = get_firestore_client()

    reference = (
        client.collection(collection_name)
        .document(document_id)
    )

    try:
        reference.create(data)
        return True

    except AlreadyExists:
        return False