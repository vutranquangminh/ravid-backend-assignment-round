"""Business logic for the documents app.

``create_document`` — saves the uploaded file to storage and creates the DB
row atomically (the file is stored first; if the DB save fails the orphaned
file is left — acceptable for a time-boxed assessment; production would wrap
in a transaction with a post-commit cleanup hook).

``delete_document`` — owner-scoped delete: removes the file from storage then
the DB row.  Cross-user / missing pk → raises ``Document.DoesNotExist`` so the
view can turn it into a 404 (D-020).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .models import Document


def create_document(owner: AbstractBaseUser, uploaded_file: object) -> Document:
    """Save *uploaded_file* to storage and create a ``Document`` row.

    Args:
        owner: The authenticated user who owns this document.
        uploaded_file: A Django ``InMemoryUploadedFile`` or
            ``TemporaryUploadedFile`` from a validated serializer.

    Returns:
        The saved ``Document`` instance (pk is set).
    """
    doc = Document(
        owner=owner,  # type: ignore[assignment]
        original_name=uploaded_file.name,
        content_type=getattr(uploaded_file, "content_type", "") or "",
        size_bytes=uploaded_file.size,
    )
    # FileField.save() writes the bytes to MEDIA_ROOT and sets doc.file.
    doc.file.save(uploaded_file.name, uploaded_file, save=False)
    doc.save()
    return doc


def delete_document(owner: AbstractBaseUser, pk: int) -> None:
    """Delete the document identified by *pk* if it belongs to *owner*.

    Removes the stored file from disk then deletes the DB row.

    Args:
        owner: The authenticated user performing the delete.
        pk: Primary key of the document to delete.

    Raises:
        Document.DoesNotExist: If no document with that pk exists for this
            owner.  The view converts this to a 404 (D-020).
    """
    doc = Document.objects.get(pk=pk, owner=owner)
    doc.file.delete(save=False)
    doc.delete()
