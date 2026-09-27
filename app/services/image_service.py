"""
Image extraction service — extract images from PDF and DOCX files.
Uploads extracted images to MinIO and returns metadata for downstream
captioning + persistence.
"""

import io
import uuid
from typing import Any, Optional

from loguru import logger

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.services.embedding_storage import (
    chunk_content_hash,
    upsert_chunk_embedding,
)
from app.services.storage_service import storage_service

# Skip images smaller than this — they're almost always icons/decorators,
# not content. Tune via env later if needed.
MIN_IMAGE_BYTES = 2048


def _mime_from_ext(ext: str) -> str:
    """Map extension to MIME type."""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }.get(ext.lower(), "image/png")


class ImageInfo:
    """Metadata about an extracted image."""
    def __init__(
        self,
        minio_key: str,
        page_number: Optional[int],
        image_index: int,
        content_type: str,
        size_bytes: int,
        caption: Optional[str] = None,
        image_id: Optional[str] = None,
    ):
        self.minio_key = minio_key
        self.page_number = page_number
        self.image_index = image_index
        self.content_type = content_type
        self.size_bytes = size_bytes
        self.caption = caption
        # Set after the row is persisted to source_images. The compiler
        # references this in `image://<uuid>` markers inside wiki content_md.
        self.image_id = image_id


def extract_images_from_pdf(
    file_data: bytes,
    source_id: str,
) -> list[ImageInfo]:
    """
    Extract all images from a PDF file and upload to MinIO.
    Returns list of ImageInfo with MinIO keys.
    """
    import fitz  # PyMuPDF

    images: list[ImageInfo] = []
    try:
        doc = fitz.open(stream=file_data, filetype="pdf")
    except Exception as e:
        logger.warning(f"Failed to open PDF for image extraction: {e}")
        return images

    image_index = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_ref in image_list:
            try:
                xref = img_ref[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue

                img_bytes = base_image["image"]
                img_ext = base_image.get("ext", "png")

                if len(img_bytes) < MIN_IMAGE_BYTES:
                    continue

                content_type = _mime_from_ext(img_ext)
                object_name = f"sources/{source_id}/images/page{page_num + 1}_{image_index}.{img_ext}"
                storage_service.upload_file(
                    object_name=object_name,
                    data=img_bytes,
                    content_type=content_type,
                )

                images.append(ImageInfo(
                    minio_key=object_name,
                    page_number=page_num + 1,
                    image_index=image_index,
                    content_type=content_type,
                    size_bytes=len(img_bytes),
                ))
                image_index += 1

            except Exception as e:
                logger.warning(f"Failed to extract image {img_ref} from page {page_num}: {e}")
                continue

    doc.close()
    logger.info(f"Extracted {len(images)} images from PDF (source {source_id})")
    return images


def extract_images_from_docx(
    file_data: bytes,
    source_id: str,
) -> list[ImageInfo]:
    """
    Extract all images from a DOCX file and upload to MinIO.
    """
    from docx import Document

    images: list[ImageInfo] = []
    try:
        doc = Document(io.BytesIO(file_data))
    except Exception as e:
        logger.warning(f"Failed to open DOCX for image extraction: {e}")
        return images

    image_index = 0
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                img_blob = rel.target_part.blob
                content_type = rel.target_part.content_type or "image/png"
                ext = content_type.split("/")[-1]
                if ext == "svg+xml":
                    ext = "svg"

                if len(img_blob) < MIN_IMAGE_BYTES:
                    continue

                object_name = f"sources/{source_id}/images/docx_{image_index}.{ext}"
                storage_service.upload_file(
                    object_name=object_name,
                    data=img_blob,
                    content_type=content_type,
                )

                images.append(ImageInfo(
                    minio_key=object_name,
                    page_number=None,  # DOCX doesn't expose page numbers easily
                    image_index=image_index,
                    content_type=content_type,
                    size_bytes=len(img_blob),
                ))
                image_index += 1

            except Exception as e:
                logger.warning(f"Failed to extract DOCX image {image_index}: {e}")
                continue

    logger.info(f"Extracted {len(images)} images from DOCX (source {source_id})")
    return images


def extract_images_from_pptx(
    file_data: bytes,
    source_id: str,
) -> list[ImageInfo]:
    """
    Extract all images from a PPTX file and upload to MinIO.
    Preserves slide page numbers.
    """
    from pptx import Presentation

    images: list[ImageInfo] = []
    try:
        prs = Presentation(io.BytesIO(file_data))
    except Exception as e:
        logger.warning(f"Failed to open PPTX for image extraction: {e}")
        return images

    def _collect_image_shapes(shapes):
        items = []
        for s in shapes:
            if hasattr(s, "shapes"):  # GroupShape
                items.extend(_collect_image_shapes(s.shapes))
            elif hasattr(s, "image"):
                items.append(s)
        return items

    image_index = 0
    for slide_idx, slide in enumerate(prs.slides, 1):
        image_shapes = _collect_image_shapes(slide.shapes)
        for shape in image_shapes:
            try:
                img = shape.image
                img_bytes = img.blob
                if len(img_bytes) < MIN_IMAGE_BYTES:
                    continue

                ext = img.ext or "png"
                content_type = img.content_type or _mime_from_ext(ext)
                object_name = f"sources/{source_id}/images/slide{slide_idx}_{image_index}.{ext}"

                storage_service.upload_file(
                    object_name=object_name,
                    data=img_bytes,
                    content_type=content_type,
                )

                images.append(ImageInfo(
                    minio_key=object_name,
                    page_number=slide_idx,
                    image_index=image_index,
                    content_type=content_type,
                    size_bytes=len(img_bytes),
                ))
                image_index += 1
            except Exception as e:
                logger.warning(f"Failed to extract PPTX image {image_index} from slide {slide_idx}: {e}")
                continue

    logger.info(f"Extracted {len(images)} images from PPTX (source {source_id})")
    return images


def extract_images(
    file_data: bytes,
    file_name: str,
    source_id: str,
) -> list[ImageInfo]:
    """Auto-detect file type and extract images."""
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return extract_images_from_pdf(file_data, source_id)
    elif lower.endswith(".docx"):
        return extract_images_from_docx(file_data, source_id)
    elif lower.endswith(".pptx"):
        return extract_images_from_pptx(file_data, source_id)
    else:
        logger.debug(f"No image extraction for file type: {file_name}")
        return []


def create_image_chunk(
    image_info: ImageInfo,
    chunk_type: str,
    text: str,
) -> dict:
    """Create a structured dictionary for visual chunks (image_caption, image_ocr)."""
    prefix = f"[{chunk_type} | Trang {image_info.page_number or 1}]: "
    clean_text = text.strip() if text else ""
    full_text = clean_text if clean_text.startswith(f"[{chunk_type}") else f"{prefix}{clean_text}"
    return {
        "chunk_type": chunk_type,
        "text": full_text,
        "page_number": image_info.page_number or 1,
        "image_id": image_info.image_id,
        "minio_key": image_info.minio_key,
    }


async def index_image_chunks(
    session,
    source_id,
    chunks: list[dict],
    spec_id: Optional[str] = None,
) -> int:
    """Embed and index visual image chunks into source_chunk_embeddings_<dim> table."""
    if not chunks:
        return 0

    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(
            f"index_image_chunks: no active embedding model configured for source {source_id}"
        )
        return 0

    spec = get_spec(spec_id)
    provider = await registry.get_embedding(task="document", spec_id=spec_id)

    texts = [c["text"] for c in chunks]
    vectors = await provider.embed_batch(texts)

    # Offset chunk_index to 80000+ so they don't collide with verbatim text chunk indices
    BASE_IMAGE_CHUNK_INDEX = 80000
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chunk_idx = BASE_IMAGE_CHUNK_INDEX + idx
        await upsert_chunk_embedding(
            session=session,
            source_id=source_id,
            chunk_index=chunk_idx,
            spec=spec,
            vector=vector,
            text=chunk["text"],
            start_char=0,
            end_char=len(chunk["text"]),
            page_number=chunk.get("page_number", 1),
            content_hash=chunk_content_hash(chunk["text"]),
        )

    logger.info(f"index_image_chunks: indexed {len(chunks)} visual chunks for source {source_id}")
    return len(chunks)

