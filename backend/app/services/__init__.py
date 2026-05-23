"""
Services - 业务服务模块
"""
from backend.app.services.pdf_service import (
    process_pdf, get_processing_result, load_result_json,
    delete_processing_result, extract_doi_from_pdf, parse_pdf_file
)
from backend.app.services.ner_service import (
    process_ner_for_result, get_ner_result, load_ner_entities,
    prepare_sentences_from_pdf, group_sentences
)
from backend.app.services.re_service import (
    process_re_for_ner, get_re_result, load_re_relations, get_re_by_ner_id
)
from backend.app.services.llm_service import LLMService, get_llm_service
from backend.app.services.storage_service import StorageService, get_storage_service
from backend.app.services.embedding_service import (
    EmbeddingService, get_embedding_service,
    text_to_embedding, texts_to_embeddings
)
from backend.app.services.milvus_service import (
    MilvusService, get_milvus_service, init_milvus_collections
)

__all__ = [
    # PDF
    "process_pdf", "get_processing_result", "load_result_json",
    "delete_processing_result", "extract_doi_from_pdf", "parse_pdf_file",
    # NER
    "process_ner_for_result", "get_ner_result", "load_ner_entities",
    "prepare_sentences_from_pdf", "group_sentences",
    # RE
    "process_re_for_ner", "get_re_result", "load_re_relations", "get_re_by_ner_id",
    # LLM
    "LLMService", "get_llm_service",
    # Storage
    "StorageService", "get_storage_service",
    # Embedding
    "EmbeddingService", "get_embedding_service",
    "text_to_embedding", "texts_to_embeddings",
    # Milvus
    "MilvusService", "get_milvus_service", "init_milvus_collections"
]