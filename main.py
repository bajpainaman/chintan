import torch
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from datasets import load_dataset
import json

# Load the BLIP-2 model and processor
device = "cuda" if torch.cuda.is_available() else "cpu"
processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
model = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b").to(device)

# Load the COCO2017 dataset from Hugging Face
dataset = load_dataset("phiyodr/coco2017", split="train")

# Output file to save labeled data
OUTPUT_LABELS = "coco_multimodal_labels.json"
labeled_data = {}

# Generate CoT reasoning for each image
for example in dataset:
    image = example["image"]  # PIL Image
    image_id = example["image_id"]

    # Preprocess the image
    inputs = processor(images=image, text="Describe this image step by step.", return_tensors="pt").to(device)

    # Generate Chain-of-Thought reasoning
    with torch.no_grad():
        generated_ids = model.generate(**inputs)
        chain_of_thought = processor.decode(generated_ids[0], skip_special_tokens=True)

    # Save the generated label
    labeled_data[image_id] = {
        "image": f"Image ID: {image_id}",
        "chain_of_thought": chain_of_thought,
    }

    print(f"Labeled Image ID {image_id}: {chain_of_thought}")

# Save to JSON
with open(OUTPUT_LABELS, "w") as f:
    json.dump(labeled_data, f, indent=4)

print(f"Labels saved to {OUTPUT_LABELS}")
