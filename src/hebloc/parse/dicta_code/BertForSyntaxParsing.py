import math, os, inspect
from transformers.utils import ModelOutput
import torch
from torch import nn
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
from transformers import BertPreTrainedModel, BertModel, BertTokenizerFast, AutoModel, AutoConfig
from transformers.models.auto.auto_factory import _BaseAutoModelClass
try:
    from transformers.modeling_utils import no_init_weights
except ImportError:
    from transformers.initialization import no_init_weights


ALL_FUNCTION_LABELS = ["nsubj", "nsubj:cop", "punct", "mark", "mark:q", "case", "case:gen", "case:acc", "fixed", "obl", "det", "amod", "acl:relcl", "nmod", "cc", "conj", "root", "compound:smixut", "cop", "compound:affix", "advmod", "nummod", "appos", "nsubj:pass", "nmod:poss", "xcomp", "obj", "aux", "parataxis", "advcl", "ccomp", "csubj", "acl", "obl:tmod", "csubj:pass", "dep", "dislocated", "nmod:tmod", "nmod:npmod", "flat", "obl:npmod", "goeswith", "reparandum", "orphan", "list", "discourse", "iobj", "vocative", "expl", "flat:name"]
ALL_POS = ['DET', 'NOUN', 'VERB', 'CCONJ', 'ADP', 'PRON', 'PUNCT', 'ADJ', 'ADV', 'SCONJ', 'NUM', 'PROPN', 'AUX', 'X', 'INTJ', 'SYM']

@dataclass
class SyntaxLogitsOutput(ModelOutput):
    dependency_logits: torch.FloatTensor = None
    function_logits: torch.FloatTensor = None
    dependency_head_indices: torch.LongTensor = None

    def detach(self):
        return SyntaxTaggingOutput(self.dependency_logits.detach(), self.function_logits.detach(), self.dependency_head_indices.detach())

@dataclass
class SyntaxTaggingOutput(ModelOutput):
    loss: Optional[torch.FloatTensor] = None
    logits: Optional[Union[torch.FloatTensor, SyntaxLogitsOutput]] = None
    hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    attentions: Optional[Tuple[torch.FloatTensor]] = None

@dataclass
class SyntaxLabels(ModelOutput):
    dependency_labels: Optional[torch.LongTensor] = None
    function_labels: Optional[torch.LongTensor] = None
    pos_labels: Optional[torch.LongTensor] = None

    def detach(self):
        return SyntaxLabels(self.dependency_labels.detach(), self.function_labels.detach(), self.pos_labels.detach() if self.pos_labels is not None else None)
    
    def to(self, device, non_blocking=False):
        return SyntaxLabels(self.dependency_labels.to(device, non_blocking=non_blocking), self.function_labels.to(device, non_blocking=non_blocking), self.pos_labels.to(device, non_blocking=non_blocking) if self.pos_labels is not None else None)

class BertSyntaxPartialInfoHead(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config

        # we want an embedding table of size 64 for each function label & unk + a single parameter embedding for unknown head
        FUNCTION_CLASS_EMBED_SIZE = 64
        TRANSFORM_SIZE = config.hidden_size * 2 + FUNCTION_CLASS_EMBED_SIZE
        self.function_class_embed = nn.Embedding(len(ALL_FUNCTION_LABELS) + 1, FUNCTION_CLASS_EMBED_SIZE)
        self.unk_function_class = len(ALL_FUNCTION_LABELS) # 0-based
        self.head_unk_embed = nn.Embedding(1, config.hidden_size)

        if False:
            TRANSFORM_SIZE += FUNCTION_CLASS_EMBED_SIZE
            self.pos_class_embed = nn.Embedding(len(ALL_POS) + 1, FUNCTION_CLASS_EMBED_SIZE)
            self.unk_pos_class = len(ALL_POS) # 0-based

        # Linear layer to transform the hidden states + activation
        self.transform = nn.Linear(TRANSFORM_SIZE, config.hidden_size)
        self.activation = nn.Tanh()

        # Auxiliary classifier to predict the input function labels from the transformed hidden states
        if False:
            self.aux_function_classifier = nn.Linear(config.hidden_size, len(ALL_FUNCTION_LABELS))
            self.aux_loss_weight = getattr(config, 'partial_info_aux_loss_weight', 0.6)
        
        # Storage for auxiliary losses from each layer (will be accumulated during forward passes)
        # Note: This won't work correctly in distributed training - we check and skip if distributed
        self.aux_losses = []
        self._partial_labels = None
        if torch.distributed.is_initialized():
            raise NotImplementedError("Partial info head not supported in distributed training")
    
    def clear_aux_losses(self):
        self.aux_losses = []

    def set_partial_labels(self, partial_labels: SyntaxLabels):
        self._partial_labels = partial_labels

    def get_total_aux_loss(self):
        if not self.aux_losses:
            return None
        total_loss = sum(self.aux_losses)
        return total_loss * self.aux_loss_weight

    def forward(
        self, 
        hidden_states: torch.Tensor,
    ) -> torch.Tensor:
        
        is_tuple, tuple_values = False, (None,)
        if isinstance(hidden_states, tuple):
            is_tuple = True
            hidden_states, tuple_values = hidden_states[0], hidden_states[1:]

        # lookup the function embeddings - turn the -1s into the unknown function label
        function_embeddings = self.function_class_embed(replace_tensor_value(self._partial_labels.function_labels.clamp_min(-1), -1, self.unk_function_class))
        # lookup the dependency embeddings - first just lookup the labels in the hidden_states - for now -1 gets clamped to 0, we don't care
        # after that, replace the -1s, with the actual value
        dependency_embedding = torch.gather(hidden_states, 1, self._partial_labels.dependency_labels.unsqueeze(-1).expand(-1, -1, self.config.hidden_size).clamp_min(0))
        dependency_embedding = torch.where((self._partial_labels.dependency_labels == -1).unsqueeze(-1), self.head_unk_embed.weight[0], dependency_embedding)

        # cat them all into a single embedding
        intermediate_states = torch.cat([hidden_states, function_embeddings, dependency_embedding], dim=-1)

        if False:
            pos_embeddings = self.pos_class_embed(replace_tensor_value(self._partial_labels.pos_labels.clamp_min(-1), -1, self.unk_pos_class))
            intermediate_states = torch.cat([intermediate_states, pos_embeddings], dim=-1)

        # run through transform and activation
        transformed = self.activation(self.transform(intermediate_states))

        # Auxiliary classifier: predict the input function labels from the transformed hidden states
        if self.training and self._partial_labels is not None and False:
            aux_logits = self.aux_function_classifier(transformed)
            # Compute auxiliary loss - only on positions where we have valid function labels (not -1)
            loss_fct = nn.CrossEntropyLoss(ignore_index=-1)
            aux_loss = loss_fct(aux_logits.view(-1, len(ALL_FUNCTION_LABELS)), self._partial_labels.function_labels.clamp_min(-1).view(-1))
            self.aux_losses.append(aux_loss)
        
        if is_tuple:
            return (transformed, *tuple_values)
        return transformed

class BertSyntaxValidClassifierHead(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config

        self.transform = nn.Linear(config.hidden_size, config.hidden_size)
        self.act = nn.Tanh()
        self.cls = nn.Linear(config.hidden_size, 2) # valid / invalid

    def forward(
        self, 
        hidden_states: torch.Tensor, 
        extended_attention_mask: Optional[torch.Tensor] = None,
        labels: Optional[torch.Tensor] = None,
        compute_mst: bool = None) -> Tuple[torch.Tensor, torch.Tensor]:
        # transform the hidden states
        transformed_states = self.act(self.transform(hidden_states[:, 0, :])) # batch x dim
        logits = self.cls(transformed_states) # batch x 2

        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, 2), labels.view(-1))

        return (loss, logits)
        
class BertSyntaxParsingHead(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config

        # the attention query & key values
        self.head_size = config.syntax_head_size# int(config.hidden_size / config.num_attention_heads * 2)
        self.label_count = getattr(config, 'syntax_attn_label_count', 1)
        self.query = nn.Linear(config.hidden_size, self.head_size * self.label_count)
        self.key = nn.Linear(config.hidden_size, self.head_size * self.label_count)
        # the function classifier gets two encoding values and predicts the labels
        self.func_label_idx = getattr(config, 'syntax_func_label_idx', 0)
        self.num_function_classes = len(ALL_FUNCTION_LABELS)
        if self.func_label_idx > -1:
            self.cls = nn.Linear(config.hidden_size * 2, self.num_function_classes)
        else: self.cls = None

    def forward(
            self, 
            hidden_states: torch.Tensor, 
            extended_attention_mask: Optional[torch.Tensor],
            labels: Optional[SyntaxLabels] = None,
            compute_mst: bool = False) -> Tuple[torch.Tensor, SyntaxLogitsOutput]:
        if compute_mst:
            assert self.label_count == 1, "Cannot compute MST with multiple attention labels - please set syntax_attn_label_count to 1"
        
        device = hidden_states.device

        # Take the dot product between "query" and "key" to get the raw attention scores.
        hidden_shape = (*hidden_states.shape[:-1], -1, self.head_size) # batch x seq x label_count x head_size
        query_layer = self.query(hidden_states).view(*hidden_shape).transpose(1, 2)
        key_layer = self.key(hidden_states).view(*hidden_shape).transpose(1, 2)
        attention_scores = torch.matmul(query_layer, key_layer.transpose(-1, -2)) / math.sqrt(self.head_size) # batch x label_count x seq x seq
        
        # add in the attention mask
        if extended_attention_mask is not None:
            attention_scores += extended_attention_mask# batch x label_count x seq x seq

        # At this point take the hidden_state of the word and of the dependency word, and predict the function
        # If labels are provided, use the labels.
        if self.training and labels is not None:
            # Note that the labels can have -100, so just set those to zero with a max
            dep_indices = labels.dependency_labels.clamp_min(0) # batch x seq x label_count
        # Otherwise - check if he wants the MST or just the argmax
        elif compute_mst:
            dep_indices = compute_mst_tree(attention_scores[:, self.func_label_idx, :, :], extended_attention_mask[:, self.func_label_idx, :, :]).unsqueeze(-1) # batch x seq x 1
        else: 
            dep_indices = torch.argmax(attention_scores, dim=-1).transpose(-1, -2) # batch x seq x label_count
            
        function_logits = None
        if self.cls:
            # After we retrieved the dependency indicies, create a tensor of teh batch indices, and and retrieve the vectors of the heads to calculate the function
            # Equivalent to:         
            # batch_indices = torch.arange(dep_indices.size(0)).view(-1, 1).expand(-1, dep_indices.size(1)).to(dep_indices.device)
            # hidden_states[batch_indices, dep_indices, :] # batch x seq x dim
            dep_vectors = torch.gather(hidden_states, 1, 
                            dep_indices[:, :, self.func_label_idx].unsqueeze(-1).expand(-1, -1, hidden_states.size(-1)))

            # concatenate that with the last hidden states, and send to the classifier output
            cls_inputs = torch.cat((hidden_states, dep_vectors), dim=-1)
            function_logits = self.cls(cls_inputs)

        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss()
            # step 1: dependency scores loss - this is applied to the attention scores
            loss = loss_fct(attention_scores.view(-1, hidden_states.size(-2)), labels.dependency_labels.view(-1))
            # step 2: function loss
            if self.cls:
                loss += loss_fct(function_logits.view(-1, self.num_function_classes), labels.function_labels.view(-1))
        
        return (loss, SyntaxLogitsOutput(attention_scores, function_logits, dep_indices))

def can_func_take_parameter(fn, param_name):
    signature = inspect.signature(fn)
    # Exclude 'self' from parameters
    parameters = [p.name for p in signature.parameters.values() if p.name != 'self']
    return 'kwargs' in parameters or param_name in parameters

class BertLayerWrapper(nn.Module):
    def __init__(self, layer_idx: int, bert_layer: nn.Module, partial_info: nn.Module):
        super().__init__()
        self.layer_idx = layer_idx
        self.bert_layer = bert_layer
        self.partial_info = partial_info

    def forward(self, **kwargs):
        hidden_states = self.bert_layer(**kwargs)
        hidden_states = self.partial_info(hidden_states)
        return hidden_states

def wrap_bert_layer_with_partial_info(layer_idx: int, bert_layer: nn.Module, partial_info: nn.Module):
    if layer_idx != 8: return
    orig_forward = bert_layer.forward
    def new_forward(*args, **kwargs):
        hidden_states = orig_forward(*args, **kwargs)
        # Read partial_labels from the module instead of kwargs
        hidden_states = partial_info(hidden_states)
        return hidden_states
    bert_layer.forward = new_forward

# PreTrainedModel.get_extended_attention_mask was removed in transformers 5
def make_extended_attention_mask(attention_mask: torch.Tensor, dtype: torch.dtype) -> torch.Tensor:
    return (1.0 - attention_mask[:, None, None, :].to(dtype)) * torch.finfo(dtype).min

class BaseForSyntaxParsing(BertPreTrainedModel):
    base_model_prefix = ""
    def __init__(self, config, syntax_head_size=128, bert_cls=BertModel, is_partial_info_model=False, is_cls_model=False, syntax_attn_label_count=1, syntax_func_label_idx=0):
        super().__init__(config)
        # conversions
        setattr(config, "hidden_dropout_prob", getattr(config, "hidden_dropout_prob", 0.1))
        setattr(config, "initializer_range", getattr(config, "classifier_init_range", getattr(config, 'decoder_init_range', 0.02)))
        
        if not hasattr(config, 'syntax_head_size'):
            config.syntax_head_size = syntax_head_size
        if not hasattr(config, 'syntax_attn_label_count'):
            config.syntax_attn_label_count = syntax_attn_label_count
        if not hasattr(config, 'syntax_func_label_idx'):
            config.syntax_func_label_idx = syntax_func_label_idx
        if not hasattr(config, 'is_partial_info_model'):
            config.is_partial_info_model = is_partial_info_model
        if not hasattr(config, 'is_cls_model'):
            config.is_cls_model = is_cls_model
            # if is_cls_model:
            #    assert config.is_partial_info_model, "CLS model requires partial info model to be set to True"

        self.bert = bert_cls(config, **({} if not can_func_take_parameter(bert_cls.__init__, 'add_pooling_layer') else {'add_pooling_layer': False}))
        self.send_token_type_ids = can_func_take_parameter(self.bert.forward, 'token_type_ids')
        self.dropout = nn.Dropout(getattr(config, "hidden_dropout_prob", 0.1))
        if config.is_partial_info_model:
            self.partial_info = BertSyntaxPartialInfoHead(config)
            for layer_idx, layer in enumerate(self.bert.encoder.layer):
                wrap_bert_layer_with_partial_info(layer_idx, layer, self.partial_info)
            # self.bert.encoder.layer = nn.ModuleList([BertLayerWrapper(layer_idx, layer, self.partial_info) for layer_idx, layer in enumerate(self.bert.encoder.layer)])
        if config.is_cls_model:
            self.syntax = BertSyntaxValidClassifierHead(config)
        else:
            self.syntax = BertSyntaxParsingHead(config)
        
        # Initialize weights and apply final processing
        self.post_init()

    def forward(
        self,
        input_ids: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        token_type_ids: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.Tensor] = None,
        partial_labels: Optional[torch.Tensor] = None,
        labels: Optional[Union[SyntaxLabels, torch.Tensor]] = None,
        head_mask: Optional[torch.Tensor] = None,
        inputs_embeds: Optional[torch.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        compute_syntax_mst: Optional[bool] = None,
    ):
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        if not self.config.is_partial_info_model and partial_labels:
            raise ValueError('Cannot pass partial label when model not initialized with partial info')

        kwargs = dict(token_type_ids=token_type_ids, head_mask=head_mask) if self.send_token_type_ids else {}
        if self.config.is_partial_info_model:
            # Store partial_labels on the module (avoids passing through kwargs which newer BERT doesn't support)
            self.partial_info.set_partial_labels(partial_labels)
            # Clear auxiliary losses before forward pass
            self.partial_info.clear_aux_losses()

        bert_outputs = self.bert(
            input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            **kwargs
        )
        
        extended_attention_mask = None
        if attention_mask is not None:
            extended_attention_mask = make_extended_attention_mask(attention_mask, bert_outputs[0].dtype)
        
        hidden_states = self.dropout(bert_outputs[0])

        # if self.config.is_partial_info_model:
        #     partial_labels = partial_labels or SyntaxLabels(dependency_labels=torch.full_like(input_ids, -1), function_labels=torch.full_like(input_ids, -1))
        #     hidden_states = self.partial_info(hidden_states, partial_labels)

        # apply the syntax head
        loss, logits = self.syntax(hidden_states, extended_attention_mask, labels, compute_syntax_mst)
        
        # Add auxiliary loss from partial info head (weighted lightly)
        if self.config.is_partial_info_model and self.training:
            aux_loss = self.partial_info.get_total_aux_loss()
            if aux_loss is not None and loss is not None:
                loss = loss + aux_loss

        if not return_dict:
            if self.config.is_cls_model:
                return (loss, logits) + bert_outputs[2:]
            return (loss,(logits.dependency_logits, logits.function_logits)) + bert_outputs[2:]
        
        return SyntaxTaggingOutput(
            loss=loss,
            logits=logits,
            hidden_states=bert_outputs.hidden_states,
            attentions=bert_outputs.attentions,
        )

    def get_input_embeddings(self):
        return self.bert.embeddings.word_embeddings

    def set_input_embeddings(self, value):
        self.bert.embeddings.word_embeddings = value

    def predict(self, sentences: Union[str, List[str]], tokenizer: BertTokenizerFast, compute_mst=True):
        if self.config.is_cls_model:
            raise ValueError('Cannot use predict function with classification model')
        if isinstance(sentences, str):
            sentences = [sentences]
            
        # predict the logits for the sentence
        inputs = tokenizer(sentences, padding='longest', truncation=True, return_tensors='pt')
        inputs = {k:v.to(self.device) for k,v in inputs.items()}
        logits = self.forward(**inputs, return_dict=True, compute_syntax_mst=compute_mst).logits
        return parse_logits(inputs['input_ids'].tolist(), sentences, tokenizer, logits, self.syntax.func_label_idx)

class AutoForSyntaxParsing(_BaseAutoModelClass):
    @classmethod
    def from_pretrained(cls, pretrained_model_name_or_path: Optional[Union[str, os.PathLike]], *args, **kwargs):
        auto_cfg = AutoConfig.from_pretrained(pretrained_model_name_or_path, trust_remote_code=True)
        custom_kwargs = dict(syntax_head_size=128, is_partial_info_model=False, is_cls_model=False, syntax_attn_label_count=1, syntax_func_label_idx=0)
        custom_kwargs = {k:kwargs.pop(k, getattr(auto_cfg, k, v)) for k,v in custom_kwargs.items()}
        base_cls = BaseForSyntaxParsing
        with no_init_weights():
            bert_cls = AutoModel.from_config(auto_cfg, *args, **kwargs).__class__
            if 'Syntax' in bert_cls.__name__:
                base_cls = bert_cls
                
        return base_cls.from_pretrained(pretrained_model_name_or_path, *args, **kwargs, **custom_kwargs, bert_cls=bert_cls, key_mapping={"^model": "bert"})
    

def parse_logits(input_ids: List[List[int]], sentences: List[str], tokenizer: BertTokenizerFast, logits: SyntaxLogitsOutput, func_label_idx: int = 0):
    outputs = []        

    special_toks = tokenizer.all_special_tokens
    special_toks.remove(tokenizer.unk_token)
    special_toks.remove(tokenizer.mask_token)
    for i in range(len(sentences)):
        # dependency_head_indices is seq x label_count - the tree is built from the function label's column
        deps = logits.dependency_head_indices[i][:, func_label_idx].tolist()
        funcs = logits.function_logits.argmax(-1)[i].tolist()
        toks = [tok for tok in tokenizer.convert_ids_to_tokens(input_ids[i]) if tok not in special_toks]
        
        # first, go through the tokens and create a mapping between each dependency index and the index without wordpieces
        # wordpieces. At the same time, append the wordpieces in
        idx_mapping = {-1:-1} # default root 
        real_idx = -1
        for i in range(len(toks)):
            if not toks[i].startswith('##'):
                real_idx += 1
            idx_mapping[i] = real_idx
            
        # build our tree, keeping tracking of the root idx
        tree = []
        root_idx = 0
        for i in range(len(toks)):
            if toks[i].startswith('##'):
                tree[-1]['word'] += toks[i][2:]
                continue 
            
            dep_idx = deps[i + 1] - 1 # increase 1 for cls, decrease 1 for cls
            if dep_idx == len(toks): dep_idx = i - 1 # if he predicts sep, then just point to the previous word
            
            dep_head = 'root' if dep_idx == -1 else toks[dep_idx]
            dep_func = ALL_FUNCTION_LABELS[funcs[i + 1]]

            if dep_head == 'root': root_idx = len(tree)
            tree.append(dict(word=toks[i], dep_head_idx=idx_mapping[dep_idx], dep_func=dep_func))
        # append the head word
        for d in tree:
            d['dep_head'] = tree[d['dep_head_idx']]['word']
        
        outputs.append(dict(tree=tree, root_idx=root_idx))
    return outputs


def compute_mst_tree(attention_scores: torch.Tensor, extended_attention_mask: torch.LongTensor):
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
        seq_lens = torch.argmax((extended_attention_mask != 0).int(), dim=2).squeeze(1)     
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
        # We have one root - detect the cycles and contract them. A cycle can never contain the root so really
        # for every cycle, we look at all the nodes, and find the highest arc out of the cycle for any values. Replace that and tada
        has_cycle, cycle_nodes = detect_cycle(indices[batch_idx], seq_lens[batch_idx])
        contracted_arcs = set()
        while has_cycle:
            base_idx, head_idx = choose_contracting_arc(indices[batch_idx], sorted_indices[batch_idx], cycle_nodes, contracted_arcs, seq_lens[batch_idx], attention_scores[batch_idx])
            indices[batch_idx, base_idx] = head_idx
            contracted_arcs.add(base_idx)
            # find the next cycle
            has_cycle, cycle_nodes = detect_cycle(indices[batch_idx], seq_lens[batch_idx])

    return indices

def detect_cycle(indices: torch.LongTensor, seq_len: int):
    # Simple cycle detection algorithm
    # Returns a boolean indicating if a cycle is detected and the nodes involved in the cycle
    visited = set()
    for node in range(1, seq_len - 1): # ignore the CLS/SEP tokens
        if node in visited:
            continue
        current_path = set()
        while node not in visited:
            visited.add(node)
            current_path.add(node)
            node = indices[node].item()
            if node == 0: break # roots never point to anything
            if node in current_path:
                return True, current_path  # Cycle detected
    return False, None

def choose_contracting_arc(indices: torch.LongTensor, sorted_indices: List[List[int]], cycle_nodes: set, contracted_arcs: set, seq_len: int, scores: List[List[float]]):
    # Chooses the highest-scoring, non-cycling arc from a graph. Iterates through 'cycle_nodes' to find
    # the best arc based on 'scores', avoiding cycles and zero node connections.
    # For each node, we only look at the next highest scoring non-cycling arc 
    best_base_idx, best_head_idx = -1, -1
    score = 0
    
    # convert the indices to a list once, to avoid multiple conversions (saves a few seconds)
    currents = indices.tolist()
    for base_node in cycle_nodes:
        if base_node in contracted_arcs: continue
        # we don't want to take anything that has a higher score than the current value - we can end up in an endless loop
        # Since the indices are sorted, as soon as we find our current item, we can move on to the next. 
        current = currents[base_node]
        found_current = False
        
        for head_node in sorted_indices[base_node]:
            if head_node == current:
                found_current = True
                continue
            if head_node in contracted_arcs: continue
            if not found_current or head_node in cycle_nodes or head_node == 0: 
                continue
            
            current_score = scores[base_node][head_node]
            if current_score > score:
                best_base_idx, best_head_idx, score = base_node, head_node, current_score
            break
    
    if best_base_idx == -1:
        raise ValueError('Stuck in endless loop trying to compute syntax mst. Please try again setting compute_syntax_mst=False')

    return best_base_idx, best_head_idx

def replace_tensor_value(tensor, orig_value, replacement_value):
    return torch.where(tensor == orig_value, replacement_value, tensor)
# name referenced by the auto_map in dicta-il/dictabert-syntax config.json
BertForSyntaxParsing = BaseForSyntaxParsing
