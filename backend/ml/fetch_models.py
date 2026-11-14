"""Build-time helper: fetch and pin the wke-ml model weights."""

import os

from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MINILM_REV = os.environ["MINILM_REV"]
DISTILBART_REV = os.environ["DISTILBART_REV"]

SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", revision=MINILM_REV)

# distilbart-cnn-6-6 ships flax/rust weights upstream that are unused;
# ignore_patterns skips them.
# Conversion keeps native fp16 dtype instead of upcasting to fp32. It would double
# the size on disk; TorchSummarizer casts to fp32 at runtime.
snapshot_dir = snapshot_download(
    "sshleifer/distilbart-cnn-6-6",
    revision=DISTILBART_REV,
    ignore_patterns=["*.msgpack", "*.ot"],
)
tokenizer = AutoTokenizer.from_pretrained(snapshot_dir)
model = AutoModelForSeq2SeqLM.from_pretrained(snapshot_dir, use_safetensors=False, dtype="auto")
model.save_pretrained(snapshot_dir, safe_serialization=True)
tokenizer.save_pretrained(snapshot_dir)

bin_path = os.path.join(snapshot_dir, "pytorch_model.bin")
if os.path.exists(bin_path):
    real_path = os.path.realpath(bin_path)
    os.remove(bin_path)
    if os.path.exists(real_path) and real_path != bin_path:
        os.remove(real_path)
