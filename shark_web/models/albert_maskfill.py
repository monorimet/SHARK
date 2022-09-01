from transformers import AutoModelForMaskedLM, AutoTokenizer
import torch
from shark.shark_inference import SharkInference
from shark.shark_importer import SharkImporter
import numpy as np

MAX_SEQUENCE_LENGTH = 512
BATCH_SIZE = 1


class AlbertModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.model = AutoModelForMaskedLM.from_pretrained("albert-base-v2")
        self.model.eval()

    def forward(self, input_ids, attention_mask):
        return self.model(
            input_ids=input_ids, attention_mask=attention_mask
        ).logits


################################## Preprocessing inputs and model ############

tokenizer = AutoTokenizer.from_pretrained("albert-base-v2")


def preprocess_data(text):
    # Preparing Data
    encoded_inputs = tokenizer(
        text,
        padding="max_length",
        truncation=True,
        max_length=MAX_SEQUENCE_LENGTH,
        return_tensors="pt",
    )
    inputs = (encoded_inputs["input_ids"], encoded_inputs["attention_mask"])
    return inputs


def top5_possibilities(text, inputs, token_logits):
    mask_id = torch.where(inputs[0] == tokenizer.mask_token_id)[1]
    mask_token_logits = token_logits[0, mask_id, :]
    percentage = torch.nn.functional.softmax(mask_token_logits, dim=1)[0]
    top_5_tokens = torch.topk(mask_token_logits, 5, dim=1).indices[0].tolist()
    top5 = {}
    for token in top_5_tokens:
        label = text.replace(tokenizer.mask_token, tokenizer.decode(token))
        top5[label] = percentage[token].item()
    return top5


##############################################################################


def albert_maskfill_inf(masked_text):
    inputs = preprocess_data(masked_text)
    mlir_importer = SharkImporter(
        AlbertModule(),
        inputs,
        frontend="torch",
    )
    minilm_mlir, func_name = mlir_importer.import_mlir(
        is_dynamic=False, tracing_required=True
    )
    shark_module = SharkInference(
        minilm_mlir, func_name, mlir_dialect="linalg"
    )
    shark_module.compile()
    token_logits = torch.tensor(shark_module.forward(inputs))
    return top5_possibilities(masked_text, inputs, token_logits)
