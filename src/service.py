
import bentoml
from bentoml.metrics import Counter, Histogram
from starlette.responses import JSONResponse
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define metrics
GENERATE_REQUESTS = Counter(
    "generate_requests_total",
    "Total number of text generation requests",
)

GENERATION_LATENCY = Histogram(
    "generation_latency_seconds",
    "Time taken to generate responses"
)

@bentoml.service(
    resources={"cpu": "2000m", "memory": "4Gi"},
    traffic={"timeout": 120},
)
class LLMInference:
    def __init__(self):
        logger.info("Loading model...")
        self.model_name = "microsoft/DialoGPT-medium"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)

        # Set pad token
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        logger.info("Model loaded successfully")
    
    @bentoml.api
    def generate(self, prompt: str, max_length: int = 50) -> dict:
        start = time.time()
        GENERATE_REQUESTS.inc()  # Increment counter

        try:
            logger.info(f"Processing: {prompt}")
            
            # Encode input
            # Convert the input prompt (plus an end-of-sequence token) into a PyTorch tensor of token IDs
            # that represent the text numerically for the model to process (pointers to the model’s vocabulary table)
            input_ids = self.tokenizer.encode(prompt + self.tokenizer.eos_token, return_tensors="pt")
            
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    input_ids,
                    max_length=input_ids.shape[-1] + max_length,
                    num_return_sequences=1,
                    pad_token_id=self.tokenizer.eos_token_id,
                    do_sample=True,
                    temperature=0.8,
                    top_p=0.9
                )
            
            # Decode full response
            full_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract generated part (remove input prompt)
            generated_text = full_text[len(prompt):].strip()
            
            # If no generation, provide fallback
            if not generated_text:
                generated_text = "I'm a conversational AI model ready to help!"
            
            result = {
                "prompt": prompt,
                "response": generated_text,
                "model": self.model_name,
                "status": "success"
            }
            
            logger.info(f"Generated: {generated_text}")
            return result
            
        except Exception as e:
            logger.error(f"Generation error: {str(e)}")
            return {
                "prompt": prompt,
                "response": "Sorry, I encountered an error generating a response.",
                "model": self.model_name,
                "status": "error",
                "error": str(e)
            }
        
        finally:
            GENERATION_LATENCY.observe(time.time() - start)
    
    @bentoml.api(route="/health", input_spec=None, output_spec=None)
    def health(self, **kwargs) -> dict:
        return {"status": "healthy", "model": self.model_name}