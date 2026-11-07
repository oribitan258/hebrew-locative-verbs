"""Documented runtime fixes for the vendored Dicta code (the vendored files stay byte-identical).

Each fix replaces ONE module-level function of the vendored code at run time, is recorded in the
run manifest (``fixes``), and is covered by a test. Found and measured in the M3 pilot.

``mst_seq_len`` — CORRECTNESS bug in ``BertForSyntaxParsing.compute_mst_tree``:
    the sequence length of each batch row is taken as the index of its first padding position
    (``argmax`` of the padding mask). A row WITHOUT padding (the longest piece of every batch, or
    any piece parsed alone) gets length 0, so the cycle-repair loop never runs for it and its
    "tree" can contain cycles (observed in the pilot), and a piece's parse depends on what else is
    in its batch. Fix: rows without padding get the full sequence length. Everything else in the
    function is copied verbatim.

``lex_topk`` — PERFORMANCE only, OFF by default, adopted only if the user approves:
    ``lex_candidates`` sorts the full 128k-word vocabulary for every sub-word (``argsort``) and keeps
    the top 3. ``torch.topk(k=3)`` returns the same top-3 candidates (ties aside) far faster and with
    far less memory. Output equivalence is measured in the pilot before any adoption.
"""

from __future__ import annotations

from typing import List

import torch

from hebloc.parse.dicta_code import BertForJointParsing as J
from hebloc.parse.dicta_code import BertForSyntaxParsing as S

_ORIGINAL = {"mst_seq_len": S.compute_mst_tree, "lex_topk": J.lex_candidates}


def compute_mst_tree_fixed(attention_scores: torch.Tensor, extended_attention_mask: torch.LongTensor):
    # attention scores should be 3 dimensions - batch x seq x seq (if it is 2 - just unsqueeze)
    if attention_scores.ndim == 2: attention_scores = attention_scores.unsqueeze(0)
    if attention_scores.ndim != 3 or attention_scores.shape[1] != attention_scores.shape[2]:
        raise ValueError(f'Expected attention scores to be of shape batch x seq x seq, instead got {attention_scores.shape}')

    batch_size, seq_len, _ = attention_scores.shape
    # start by softmaxing so the scores are comparable
    attention_scores = attention_scores.softmax(dim=-1)

    batch_indices = torch.arange(batch_size, device=attention_scores.device)
    seq_indices = torch.arange(seq_len, device=attention_scores.device)

    seq_lens = torch.full((batch_size,), seq_len)

    if extended_attention_mask is not None:
        # ---- FIX (hebloc): rows without any padding keep the full length instead of argmax()=0
        padded = (extended_attention_mask != 0).int()
        seq_lens = torch.where(padded.amax(dim=2).squeeze(1) > 0,
                               torch.argmax(padded, dim=2).squeeze(1),
                               torch.full((batch_size,), seq_len, device=padded.device))
        # ---- end of fix
        # zero out any padding
        attention_scores[extended_attention_mask.squeeze(1) != 0] = 0

    # set the values for the CLS and sep to all by very low, so they never get chosen as a replacement arc
    attention_scores[:, 0, :] = 0
    attention_scores[batch_indices, seq_lens - 1, :] = 0
    attention_scores[batch_indices, :, seq_lens - 1] = 0 # can never predict sep
    # set the values for each token pointing to itself be 0
    attention_scores[:, seq_indices, seq_indices] = 0

    # find the root, and make him super high so we never have a conflict
    root_cands = torch.argsort(attention_scores[:, :, 0], dim=-1)
    attention_scores[batch_indices.unsqueeze(1), root_cands, 0] = 0
    attention_scores[batch_indices, root_cands[:, -1], 0] = 1.0

    # we start by getting the argmax for each score, and then computing the cycles and contracting them
    sorted_indices = torch.argsort(attention_scores, dim=-1, descending=True)
    indices = sorted_indices[:, :, 0].clone() # take the argmax

    attention_scores = attention_scores.tolist()
    seq_lens = seq_lens.tolist()
    sorted_indices = [[sub_l[:slen] for sub_l in l[:slen]] for l,slen in zip(sorted_indices.tolist(), seq_lens)]

    # go through each batch item and make sure our tree works
    for batch_idx in range(batch_size):
        has_cycle, cycle_nodes = S.detect_cycle(indices[batch_idx], seq_lens[batch_idx])
        contracted_arcs = set()
        while has_cycle:
            base_idx, head_idx = S.choose_contracting_arc(indices[batch_idx], sorted_indices[batch_idx], cycle_nodes, contracted_arcs, seq_lens[batch_idx], attention_scores[batch_idx])
            indices[batch_idx, base_idx] = head_idx
            contracted_arcs.add(base_idx)
            # find the next cycle
            has_cycle, cycle_nodes = S.detect_cycle(indices[batch_idx], seq_lens[batch_idx])

    return indices


def lex_candidates_topk(input_ids: List[List[int]], tokenizer, logits: torch.Tensor, topk: int = 3):
    """Same contract as the vendored ``lex_candidates``; ``torch.topk`` instead of a full argsort."""
    predictions = torch.topk(logits, topk, dim=-1).indices.tolist()
    batch_ret = []
    special_toks = tokenizer.all_special_tokens
    special_toks.remove(tokenizer.unk_token)
    special_toks.remove(tokenizer.mask_token)
    for batch_idx in range(len(input_ids)):
        ret = []
        batch_ret.append(ret)
        tokens = tokenizer.convert_ids_to_tokens(input_ids[batch_idx])
        for tok_idx in range(len(tokens)):
            token = tokens[tok_idx]
            if token in special_toks: continue
            if token.startswith('##'):
                ret[-1] = (ret[-1][0] + token[2:], ret[-1][1])
                continue
            ret.append((token, tokenizer.convert_ids_to_tokens(predictions[batch_idx][tok_idx])))
    return batch_ret


def apply(mst_seq_len: bool = True, lex_topk: bool = False) -> list[str]:
    """Set the fixes for this process (idempotent; False restores the original function)."""
    S.compute_mst_tree = compute_mst_tree_fixed if mst_seq_len else _ORIGINAL["mst_seq_len"]
    J.lex_candidates = lex_candidates_topk if lex_topk else _ORIGINAL["lex_topk"]
    return [name for name, on in (("mst_seq_len", mst_seq_len), ("lex_topk", lex_topk)) if on]
