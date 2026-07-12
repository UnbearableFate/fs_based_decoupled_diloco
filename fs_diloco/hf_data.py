"""Dataset loading and infinite batch iterators."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

import torch

from fs_diloco.protocol.canonical_json import canonical_digest


@dataclass
class Batch:
    input_ids: torch.Tensor
    labels: torch.Tensor
    num_tokens: int
    num_examples: int

    def to(self, device: torch.device) -> "Batch":
        return Batch(
            input_ids=self.input_ids.to(device),
            labels=self.labels.to(device),
            num_tokens=self.num_tokens,
            num_examples=self.num_examples,
        )


class SyntheticBatchSource(Iterator[Batch]):
    def __init__(
        self,
        *,
        vocab_size: int,
        block_size: int,
        micro_batch_size: int,
        seed: int,
        learner_index: int,
    ) -> None:
        self.vocab_size = vocab_size
        self.block_size = block_size
        self.micro_batch_size = micro_batch_size
        self.seed = seed
        self.learner_index = learner_index
        self.generator = torch.Generator()
        self.generator.manual_seed(seed + learner_index * 100_003)
        self.batch_index = 0

    def __iter__(self) -> "SyntheticBatchSource":
        return self

    def __next__(self) -> Batch:
        input_ids = torch.randint(
            low=0,
            high=self.vocab_size,
            size=(self.micro_batch_size, self.block_size),
            generator=self.generator,
            dtype=torch.long,
        )
        self.batch_index += 1
        return Batch(
            input_ids=input_ids,
            labels=input_ids.clone(),
            num_tokens=int(input_ids.numel()),
            num_examples=self.micro_batch_size,
        )

    @property
    def identity(self) -> str:
        return canonical_digest(
            {
                "kind": "synthetic",
                "vocab_size": self.vocab_size,
                "block_size": self.block_size,
                "micro_batch_size": self.micro_batch_size,
                "seed": self.seed,
                "learner_index": self.learner_index,
            }
        )

    def state_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-synthetic-batch-source-v1",
            "identity": self.identity,
            "batch_index": self.batch_index,
            "generator_state": self.generator.get_state().tolist(),
        }

    def load_state_dict(self, payload: Mapping[str, object]) -> None:
        if set(payload) != {"schema", "identity", "batch_index", "generator_state"}:
            raise ValueError("synthetic batch-source state fields differ")
        if (
            payload["schema"] != "duraloco-synthetic-batch-source-v1"
            or payload["identity"] != self.identity
            or type(payload["batch_index"]) is not int
            or payload["batch_index"] < 0
            or not isinstance(payload["generator_state"], list)
        ):
            raise ValueError("synthetic batch-source identity/state differs")
        state = torch.tensor(payload["generator_state"], dtype=torch.uint8)
        self.generator.set_state(state)
        self.batch_index = payload["batch_index"]


def synthetic_batches(
    *,
    vocab_size: int,
    block_size: int,
    micro_batch_size: int,
    seed: int,
    learner_index: int,
) -> Iterator[Batch]:
    return SyntheticBatchSource(
        vocab_size=vocab_size,
        block_size=block_size,
        micro_batch_size=micro_batch_size,
        seed=seed,
        learner_index=learner_index,
    )


def _chunks(tokens: list[int], block_size: int) -> list[list[int]]:
    usable = (len(tokens) // block_size) * block_size
    return [tokens[i : i + block_size] for i in range(0, usable, block_size)]


class WikiTextBatchSource(Iterator[Batch]):
    def __init__(
        self,
        blocks: list[list[int]],
        micro_batch_size: int,
        *,
        dataset_identity: str,
        tokenizer_identity: str,
    ) -> None:
        if not blocks:
            raise ValueError("tokenized dataset produced zero blocks")
        self.blocks = blocks
        self.micro_batch_size = micro_batch_size
        self.dataset_identity = dataset_identity
        self.tokenizer_identity = tokenizer_identity
        self.batch_index = 0

    def __iter__(self) -> "WikiTextBatchSource":
        return self

    def __next__(self) -> Batch:
        start = self.batch_index * self.micro_batch_size
        indices = [(start + offset) % len(self.blocks) for offset in range(self.micro_batch_size)]
        batch_blocks = [self.blocks[index] for index in indices]
        input_ids = torch.tensor(batch_blocks, dtype=torch.long)
        self.batch_index += 1
        return Batch(
            input_ids=input_ids,
            labels=input_ids.clone(),
            num_tokens=int(input_ids.numel()),
            num_examples=len(batch_blocks),
        )

    @property
    def identity(self) -> str:
        return canonical_digest(
            {
                "kind": "wikitext",
                "dataset_identity": self.dataset_identity,
                "tokenizer_identity": self.tokenizer_identity,
                "micro_batch_size": self.micro_batch_size,
                "block_count": len(self.blocks),
            }
        )

    def state_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-wikitext-batch-source-v1",
            "identity": self.identity,
            "dataset_identity": self.dataset_identity,
            "tokenizer_identity": self.tokenizer_identity,
            "batch_index": self.batch_index,
        }

    def load_state_dict(self, payload: Mapping[str, object]) -> None:
        required = {
            "schema",
            "identity",
            "dataset_identity",
            "tokenizer_identity",
            "batch_index",
        }
        if set(payload) != required or (
            payload["schema"] != "duraloco-wikitext-batch-source-v1"
            or payload["identity"] != self.identity
            or payload["dataset_identity"] != self.dataset_identity
            or payload["tokenizer_identity"] != self.tokenizer_identity
            or type(payload["batch_index"]) is not int
            or payload["batch_index"] < 0
        ):
            raise ValueError("WikiText batch-source identity/state differs")
        self.batch_index = payload["batch_index"]


def _batched_blocks(blocks: list[list[int]], micro_batch_size: int) -> Iterator[Batch]:
    return WikiTextBatchSource(
        blocks,
        micro_batch_size,
        dataset_identity=canonical_digest({"blocks": blocks}),
        tokenizer_identity="legacy-unspecified",
    )


def wikitext_batches(
    data_config: Any,
    tokenizer: Any,
    *,
    learner_index: int,
    num_learners: int,
    micro_batch_size: int,
    block_size: int,
) -> Iterator[Batch]:
    from datasets import load_dataset

    dataset_name = data_config.dataset_name
    if dataset_name == "wikitext" and os.environ.get("FS_DILOCO_HF_WIKITEXT_REPO"):
        dataset_name = os.environ["FS_DILOCO_HF_WIKITEXT_REPO"]
    try:
        dataset = load_dataset(
            dataset_name,
            data_config.dataset_config_name,
            split=data_config.train_split,
            cache_dir=data_config.cache_dir,
            streaming=bool(data_config.streaming),
        )
    except Exception as exc:
        if data_config.dataset_name != "wikitext" or "/" in str(dataset_name):
            raise
        try:
            dataset = load_dataset(
                "Salesforce/wikitext",
                data_config.dataset_config_name,
                split=data_config.train_split,
                cache_dir=data_config.cache_dir,
                streaming=bool(data_config.streaming),
            )
        except Exception:
            raise exc
    dataset = dataset.shard(num_shards=num_learners, index=learner_index, contiguous=True)
    texts = [row["text"] for row in dataset if row.get("text")]
    token_stream: list[int] = []
    for text in texts:
        token_stream.extend(tokenizer(text, add_special_tokens=False)["input_ids"])
        eos_id = getattr(tokenizer, "eos_token_id", None)
        if eos_id is not None:
            token_stream.append(eos_id)
    blocks = _chunks(token_stream, block_size)
    dataset_identity = canonical_digest(
        {
            "dataset_name": dataset_name,
            "dataset_config_name": data_config.dataset_config_name,
            "train_split": data_config.train_split,
            "streaming": bool(data_config.streaming),
            "learner_index": learner_index,
            "num_learners": num_learners,
            "blocks": blocks,
        }
    )
    tokenizer_identity = canonical_digest(
        {
            "class": type(tokenizer).__qualname__,
            "name_or_path": str(getattr(tokenizer, "name_or_path", "")),
            "vocab_size": int(getattr(tokenizer, "vocab_size", 0)),
            "eos_token_id": getattr(tokenizer, "eos_token_id", None),
        }
    )
    return WikiTextBatchSource(
        blocks,
        micro_batch_size,
        dataset_identity=dataset_identity,
        tokenizer_identity=tokenizer_identity,
    )


def build_batch_iterator(
    config: Any,
    tokenizer: Any,
    *,
    learner_index: int,
    num_learners: int,
) -> Iterator[Batch]:
    if config.data.dataset_name == "synthetic":
        vocab_size = int(getattr(tokenizer, "vocab_size", config.model.synthetic_vocab_size))
        return synthetic_batches(
            vocab_size=vocab_size,
            block_size=config.training.block_size,
            micro_batch_size=config.training.micro_batch_size,
            seed=config.training.seed,
            learner_index=learner_index,
        )
    return wikitext_batches(
        config.data,
        tokenizer,
        learner_index=learner_index,
        num_learners=num_learners,
        micro_batch_size=config.training.micro_batch_size,
        block_size=config.training.block_size,
    )
