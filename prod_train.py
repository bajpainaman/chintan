import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from PIL import Image
from torchvision import transforms
from torch.utils.data import Dataset
import requests
import os

# Model and Tokenizer Loading
model_name = "deepseek-ai/Janus-1.3B"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    trust_remote_code=True,
    torch_dtype=torch.float16  # Ensure compatibility with FlashAttention 2.0
)

# Apply LoRA for Efficient Fine-tuning
lora_config = LoraConfig(
    r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"], lora_dropout=0.05, bias="none"
)
model = get_peft_model(model, lora_config)

# Dataset Class
class ChintanDataset(Dataset):
    def __init__(self, data, tokenizer, transform=None):
        self.data = data
        self.tokenizer = tokenizer
        self.transform = transform or transforms.Compose([
            transforms.Resize((384, 384)),
            transforms.ToTensor()
        ])

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        try:
            image = Image.open(requests.get(item['image_url'], stream=True).raw).convert('RGB')
        except Exception:
            image = Image.new('RGB', (384, 384), color='white')  # Fallback for missing images
        
        image = self.transform(image)
        prompt = f"Caption: {item['caption']}\nCoT: {item['chain_of_thought']}\nSDXL Prompt: {item['sdxl_prompt']}"
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, padding='max_length', max_length=512)

        return {
            "input_ids": inputs['input_ids'].squeeze(),
            "attention_mask": inputs['attention_mask'].squeeze(),
            "labels": inputs['input_ids'].squeeze(),
            "image": image
        }

# Load Dataset
dataset = load_dataset("bombaygamercc/chintan33k", split="train")
train_dataset = ChintanDataset(dataset, tokenizer)

# Training Arguments
training_args = TrainingArguments(
    output_dir="./results",
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=32,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=3,  # Keep last 3 checkpoints
    logging_dir="./logs",
    logging_steps=100,
    learning_rate=3e-5,
    weight_decay=0.01,
    fp16=True,  # Enable mixed-precision training
    optim="adamw_torch_fused",
    dataloader_num_workers=4,
    load_best_model_at_end=True,  # Automatically restore best checkpoint
)

# AMP Trainer for Mixed Precision
class AMPTrainer(Trainer):
    def training_step(self, model, inputs):
        model.train()
        with torch.autocast(device_type='cuda', dtype=torch.float16):
            loss = super().compute_loss(model, inputs)
        return loss

# Initialize Trainer
trainer = AMPTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset
)

# Resume from Checkpoint if Available
checkpoint_dir = "./results/checkpoint-last"
if os.path.exists(checkpoint_dir):
    print("Resuming from the last checkpoint...")
    trainer.train(resume_from_checkpoint=checkpoint_dir)
else:
    print("Starting training from scratch...")
    trainer.train()

# Save Final Model
model.save_pretrained("./chintan_model")
tokenizer.save_pretrained("./chintan_model")
