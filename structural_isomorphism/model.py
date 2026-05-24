"""
Model loading and encoding utilities.
"""

import logging
from pathlib import Path
from typing import List, Union, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Default model identifiers
DEFAULT_LOCAL_MODEL = Path(__file__).parent.parent / "models" / "structural-v1"
DEFAULT_HF_MODEL = "structural-isomorphism/structural-v1"
DEFAULT_BASE_MODEL = "shibing624/text2vec-base-chinese"


def load_model(
    model_path: Optional[str] = None,
    device: Optional[str] = None,
):
    """
    Load a SentenceTransformer model for structural encoding.

    Priority:
    1. Explicit model_path if provided
    2. Local model directory (models/structural-v1/)
    3. HuggingFace Hub model
    4. Base model (no fine-tuning) as fallback

    Args:
        model_path: Explicit path or HuggingFace model ID.
        device: Device to load model on ('cpu', 'cuda', 'mps'). Auto-detected if None.

    Returns:
        SentenceTransformer model instance.
    """
    from sentence_transformers import SentenceTransformer

    candidates = []

    if model_path:
        candidates.append(("explicit", model_path))
    else:
        candidates.append(("local", str(DEFAULT_LOCAL_MODEL)))
        candidates.append(("huggingface", DEFAULT_HF_MODEL))
        candidates.append(("base", DEFAULT_BASE_MODEL))

    for source, path in candidates:
        try:
            if source == "local" and not Path(path).exists():
                continue

            logger.info(f"Loading model from {source}: {path}")
            kwargs = {}
            if device:
                kwargs["device"] = device

            model = SentenceTransformer(path, **kwargs)
            logger.info(f"Model loaded successfully from {source}")

            if source == "base":
                logger.warning(
                    "Using base model without fine-tuning. "
                    "Results will be based on surface similarity, not structural similarity. "
                    "Download the fine-tuned model for best results."
                )

            return model

        except Exception as e:
            logger.debug(f"Failed to load from {source} ({path}): {e}")
            continue

    raise RuntimeError(
        "Could not load any model. Please install sentence-transformers "
        "and ensure you have internet access or a local model at "
        f"{DEFAULT_LOCAL_MODEL}"
    )


def encode_texts(
    model,
    texts: Union[str, List[str]],
    batch_size: int = 32,
    show_progress: bool = False,
    normalize: bool = True,
) -> np.ndarray:
    """
    Encode text(s) into structural embeddings.

    Args:
        model: SentenceTransformer model.
        texts: Single string or list of strings to encode.
        batch_size: Batch size for encoding.
        show_progress: Whether to show a progress bar.
        normalize: Whether to L2-normalize embeddings.

    Returns:
        numpy array of shape (n_texts, embedding_dim).
    """
    if isinstance(texts, str):
        texts = [texts]

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
    )

    return embeddings
